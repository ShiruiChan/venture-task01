import json
from datetime import date

import httpx
import pytest

from app.config import LaserConfig, RarusConfig
from app.sources import LaserSource, RarusSource
from app.sources.base import SourceError
from app.sources.rarus import day_to_ms

RARUS_LOGIN = {
    "success": True,
    "message": "OK",
    "data": {"access_token": "token-1", "expire_at": 9_999_999_999_999},
}


def rarus_transport(calls: list[httpx.Request], rating_total: str = "412"):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/login":
            return httpx.Response(200, json=RARUS_LOGIN)
        if request.url.path.endswith("/objects-rating/fetch"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "message": "OK",
                    "data": {
                        "label": "Рейтинг объектов",
                        "series": [
                            {
                                "label": "Планета Электро, Якутск, Бестужева-Марлинского 64-1",
                                "id": "00000000-0000-0000-0000-000000000000",
                                "total_current": rating_total,
                                "growth": "-0.59",
                                "points": None,
                            }
                        ],
                    },
                },
            )
        return httpx.Response(200, json={"success": False, "message": "нет виджета", "error": {"reason": "unknown"}})

    return httpx.MockTransport(handler)


def make_rarus(calls: list[httpx.Request], **kw) -> RarusSource:
    client = httpx.AsyncClient(transport=rarus_transport(calls, **kw), base_url="https://rarus.test")
    return RarusSource(RarusConfig(base_url="https://rarus.test", user="u", password="p"), client=client)


async def test_rarus_fetch_day_parses_series():
    calls: list[httpx.Request] = []
    async with make_rarus(calls) as source:
        counts = await source.fetch_day(date(2026, 8, 30))
    assert len(counts) == 1
    assert counts[0].entered == 412
    # нулевой GUID заменяется названием объекта — иначе все объекты слились бы в один
    assert counts[0].external_id == "Планета Электро, Якутск, Бестужева-Марлинского 64-1"
    widget = next(c for c in calls if "objects-rating" in c.url.path)
    assert widget.url.params["period"] == "day"
    assert int(widget.url.params["date"]) == day_to_ms(date(2026, 8, 30))


async def test_rarus_reuses_token_across_days():
    calls: list[httpx.Request] = []
    async with make_rarus(calls) as source:
        counts = await source.fetch_daily(date(2026, 8, 28), date(2026, 8, 30))
    assert len(counts) == 3
    assert sum(1 for c in calls if c.url.path == "/login") == 1


async def test_rarus_reports_api_error():
    async with make_rarus([]) as source:
        with pytest.raises(SourceError):
            await source.widget("no-such-widget")


async def test_rarus_requires_credentials():
    async with RarusSource(RarusConfig(base_url="https://rarus.test", user="", password="")) as source:
        with pytest.raises(SourceError):
            await source.list_objects()


async def test_laser_http_parses_alternative_field_names():
    payload = {
        "items": [
            {"objectId": 7, "object_name": "ТЦ Планета", "day": "2026-08-30", "in": 455, "out": 450},
            {"objectId": 7, "object_name": "ТЦ Планета", "day": 1788048000000, "in": "500"},
        ]
    }
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    client = httpx.AsyncClient(transport=transport, base_url="https://laser.test")
    config = LaserConfig(mode="http", base_url="https://laser.test", auth_mode="bearer", token="t")
    async with LaserSource(config, client=client) as source:
        counts = await source.fetch_daily(date(2026, 8, 29), date(2026, 8, 31))
    assert [c.entered for c in counts] == [455, 500]
    assert [c.day for c in counts] == [date(2026, 8, 30), date(2026, 8, 30)]
    assert counts[0].exited == 450 and counts[1].exited is None


async def test_laser_http_filters_outside_period():
    payload = [{"id": 1, "name": "О", "date": "2026-07-01", "entered": 10}]
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    client = httpx.AsyncClient(transport=transport, base_url="https://laser.test")
    async with LaserSource(LaserConfig(mode="http", base_url="https://laser.test"), client=client) as source:
        assert await source.fetch_daily(date(2026, 8, 1), date(2026, 8, 2)) == []


async def test_laser_fixture_file_is_used(tmp_path):
    path = tmp_path / "fixture.json"
    path.write_text(
        json.dumps({"daily": [{"id": "o1", "name": "Объект", "date": "2026-08-30", "entered": 321}]}),
        encoding="utf-8",
    )
    async with LaserSource(LaserConfig(mode="fixture", fixture_path=path)) as source:
        counts = await source.fetch_daily(date(2026, 8, 30), date(2026, 8, 30))
    assert [c.entered for c in counts] == [321]


async def test_laser_generation_is_deterministic_and_near_baseline(tmp_path):
    from app.models import SourceObject

    config = LaserConfig(mode="fixture", fixture_path=tmp_path / "absent.json")
    baseline = SourceObject("o1", "Объект", raw={"daily": {"2026-08-30": 1000}, "entered": 1000})
    async with LaserSource(config, fallback_objects=[baseline]) as source:
        first = await source.fetch_daily(date(2026, 8, 30), date(2026, 8, 30))
        second = await source.fetch_daily(date(2026, 8, 30), date(2026, 8, 30))
    assert first == second
    if first:  # в отдельные сутки эмулируется пропуск выгрузки
        assert 850 <= first[0].entered <= 1150
