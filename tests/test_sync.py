import asyncio
from datetime import date

from app import db, sync
from app.config import settings
from app.models import SOURCE_LASER, DailyCount

DAY = date(2026, 8, 31)


class FakeCounters:
    """Опрос счётчиков, часть которых могла не ответить."""

    def __init__(self, errors: list[str]):
        self.errors = errors

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def fetch_daily(self, day_from, day_to):
        return [DailyCount("2690", "Планета Электро, Якутск", DAY, 220, 216)]


def run_laser(monkeypatch, errors: list[str]) -> dict:
    monkeypatch.setattr(settings.laser, "mode", "guestance")
    monkeypatch.setattr(sync, "GuestanceSource", lambda config: FakeCounters(errors))
    return asyncio.run(sync.sync_laser(DAY, DAY))


def test_all_counters_answered_is_ok(temp_db, monkeypatch):
    result = run_laser(monkeypatch, [])
    assert (result["status"], result["rows"], result["message"]) == ("ok", 1, "")
    assert db.recent_runs(1, temp_db)[0]["status"] == "ok"


def test_one_counter_down_is_partial_not_ok(temp_db, monkeypatch):
    result = run_laser(monkeypatch, ["guest.advrouter.asuscomm.com:8009: /id.xml — nodename nor servname"])
    # данные за сутки собраны, но не со всех точек — прогон помечен отдельно
    assert (result["status"], result["rows"]) == ("partial", 1)
    assert "счётчик недоступен" in result["message"]
    run = db.recent_runs(1, temp_db)[0]
    assert run["status"] == "partial" and "guest.advrouter" in run["message"]


def test_source_failure_stays_an_error(temp_db, monkeypatch):
    class Dead(FakeCounters):
        async def fetch_daily(self, day_from, day_to):
            raise RuntimeError("Ни один счётчик не ответил")

    monkeypatch.setattr(settings.laser, "mode", "guestance")
    monkeypatch.setattr(sync, "GuestanceSource", lambda config: Dead([]))
    result = asyncio.run(sync.sync_laser(DAY, DAY))
    assert result["status"] == "error" and result["rows"] == 0
    assert db.recent_runs(1, temp_db)[0]["status"] == "error"
    assert not db.fetch_counts(DAY, DAY)
