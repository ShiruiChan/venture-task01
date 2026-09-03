from datetime import date

import httpx
import pytest

from app.config import CounterAddress, LaserConfig
from app.sources import GuestanceSource
from app.sources.base import SourceError
from app.sources.guestance import daily_counts, parse_journal, parse_moment

# формат живого счётчика: EVENT_INNOW = 10 с полями «вошло, присутствие, вышло»
JOURNAL = (
    "20/02/19 12:31,10,5,4,3\r\n"
    "20/02/19 12:32,10,7,6,2\r\n"
    "20/02/19 12:33,11,40,0,0\r\n"  # EVENT_INOUT - в посещаемость не идёт
    "20/02/19 12:34,5,0,0,0\r\n"  # вход в настройки счётчика
    "\r\n"
    "21/02/19 09:05,10,1,1,1\r\n"
    "20/02/00 10:00,10,9,9,9\r\n"  # время в счётчике не установлено
)


def counter_transport(journal: str = JOURNAL, serial: str = "1234567", encoding: str = "cp1251"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/id.xml":
            return httpx.Response(200, content=f"<id><serial>{serial}</serial></id>".encode(encoding))
        if request.url.path == "/journal.cgi":
            return httpx.Response(200, content=journal.encode(encoding))
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def make_source(transport: httpx.MockTransport, **kw) -> GuestanceSource:
    config = LaserConfig(mode="guestance", counters=(CounterAddress("192.168.0.70", "ТЦ Планета"),), **kw)
    return GuestanceSource(config, client=httpx.AsyncClient(transport=transport))


def test_parse_moment_reads_counter_format():
    # основной формат счётчика - ДД/ММ/ГГ
    assert parse_moment("20/02/19 12:31") == __import__("datetime").datetime(2019, 2, 20, 12, 31)
    # четырёхзначное начало трактуется как ГГГГ/ММ/ДД
    assert parse_moment("2019/02/20 12:31:45").day == 20
    # нулевой год: время в счётчике не установлено
    assert parse_moment("20/02/00 12:31") is None
    assert parse_moment("не дата") is None


def test_parse_journal_skips_broken_lines():
    rows = parse_journal(JOURNAL)
    assert [r.event for r in rows] == [10, 10, 11, 5, 10]
    assert rows[0].value(2) == 5 and rows[0].value(99) is None


def test_daily_counts_sums_passages_by_day():
    counts = daily_counts(parse_journal(JOURNAL), "1234567", "ТЦ Планета")
    assert [(c.day, c.entered, c.exited) for c in counts] == [
        (date(2019, 2, 20), 12, 5),
        (date(2019, 2, 21), 1, 1),
    ]


def test_daily_counts_honours_event_filter():
    counts = daily_counts(parse_journal(JOURNAL), "1", "О", count_events=(11,))
    assert [(c.entered, c.exited) for c in counts] == [(40, 0)]


async def test_fetch_daily_reads_serial_then_journal():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return counter_transport().handler(request)

    async with make_source(httpx.MockTransport(handler)) as source:
        counts = await source.fetch_daily(date(2019, 2, 20), date(2019, 2, 21))

    assert [r.url.path for r in requests] == ["/id.xml", "/journal.cgi"]
    # d - номера суток от 1970-01-01: 20 и 21 февраля 2019 года
    assert dict(requests[1].url.params) == {"t": "a", "f": "c", "d": "17947-17948"}
    # гостевая учётная запись счётчика по умолчанию - guest:guest
    assert requests[0].headers["authorization"] == "Basic Z3Vlc3Q6Z3Vlc3Q="
    assert [(c.external_id, c.name, c.entered) for c in counts] == [
        ("1234567", "ТЦ Планета", 12),
        ("1234567", "ТЦ Планета", 1),
    ]


async def test_fetch_daily_filters_period_and_decodes_cp1251():
    journal = (
        "20/02/19 12:31,10,5,4,3\r\n"
        "20/02/19 12:40,1,,,Включение питания\r\n"
        "01/07/19 12:31,10,8,8,8\r\n"
    )
    async with make_source(counter_transport(journal)) as source:
        counts = await source.fetch_daily(date(2019, 2, 1), date(2019, 2, 28))
    # счётчик отдаёт сутки целиком, лишние дни отсекаются на нашей стороне
    assert [c.day for c in counts] == [date(2019, 2, 20)]
    # строка журнала пришла в CP1251 и разобрана без потерь
    rows = parse_journal(journal)
    assert rows[1].fields[4] == "Включение питания"


async def test_one_day_period_asks_for_a_single_day_number():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return counter_transport().handler(request)

    async with make_source(httpx.MockTransport(handler)) as source:
        await source.fetch_daily(date(2019, 2, 20), date(2019, 2, 20))
    assert dict(requests[1].url.params)["d"] == "17947"


async def test_journal_path_without_placeholder_is_left_as_is():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return counter_transport().handler(request)

    # прошивке, у которой нет фильтра по датам, оставляем выгрузку целиком
    async with make_source(httpx.MockTransport(handler), journal_path="/journal.cgi?t=a&f=c&d=a") as source:
        await source.fetch_daily(date(2019, 2, 20), date(2019, 2, 21))
    assert dict(requests[1].url.params)["d"] == "a"


async def test_counter_names_override_address_label():
    async with make_source(counter_transport(), counter_names={"1234567": "Планета Электро, Якутск"}) as source:
        objects = await source.list_objects()
    assert [(o.external_id, o.name) for o in objects] == [("1234567", "Планета Электро, Якутск")]


async def test_dead_counter_does_not_break_the_rest():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "10.0.0.1":
            return httpx.Response(500)
        return counter_transport().handler(request)

    config = LaserConfig(
        mode="guestance",
        counters=(CounterAddress("10.0.0.1", "Мёртвый"), CounterAddress("10.0.0.2", "Живой")),
    )
    async with GuestanceSource(config, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))) as source:
        counts = await source.fetch_daily(date(2019, 2, 20), date(2019, 2, 21))
    assert [c.name for c in counts] == ["Живой", "Живой"]
    assert source.errors and "10.0.0.1" in source.errors[0]


async def test_all_counters_down_is_an_error():
    transport = httpx.MockTransport(lambda r: httpx.Response(503))
    async with make_source(transport) as source:
        with pytest.raises(SourceError, match="Ни один счётчик не ответил"):
            await source.fetch_daily(date(2019, 2, 20), date(2019, 2, 21))


async def test_requires_counters_or_journal_dir():
    async with GuestanceSource(LaserConfig(mode="guestance")) as source:
        with pytest.raises(SourceError, match="LASER_COUNTERS"):
            await source.list_objects()


async def test_journal_dir_works_without_access_to_counters(tmp_path):
    (tmp_path / "1234567_journal.csv").write_bytes(JOURNAL.encode("cp1251"))
    config = LaserConfig(
        mode="guestance",
        journal_dir=tmp_path,
        counter_names={"1234567": "Планета Электро, Якутск"},
    )
    async with GuestanceSource(config) as source:
        counts = await source.fetch_daily(date(2019, 2, 20), date(2019, 2, 21))
    assert [(c.name, c.entered) for c in counts] == [
        ("Планета Электро, Якутск", 12),
        ("Планета Электро, Якутск", 1),
    ]


async def test_empty_journal_dir_is_an_error(tmp_path):
    async with GuestanceSource(LaserConfig(mode="guestance", journal_dir=tmp_path)) as source:
        with pytest.raises(SourceError, match="нет файлов журналов"):
            await source.fetch_daily(date(2019, 2, 20), date(2019, 2, 21))
