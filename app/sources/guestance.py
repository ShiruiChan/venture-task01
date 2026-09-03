"""Счётчики «Посещаемость» (TIGRA electronic): центрального API нет, каждое
устройство опрашивается по HTTP под гостевой учёткой (заводская guest:guest).

GET /id.xml - серийник; GET /journal.cgi?t=a&f=c&d=<дни> - журнал, CSV в CP1251.
``d`` - номер суток от 1970-01-01 либо диапазон; ``d=a`` («весь журнал») прошивка
обрезает. Нулевой год в дате - время в счётчике не установлено, строка отбрасывается.
Посещаемость - событие 10 (EVENT_INNOW) с полями «вошло, присутствие, вышло»
(порядок из прошивки, js_160424.js), поэтому выходы - поле 4, а не 3; на других
прошивках проход может идти событием 11 (EVENT_INOUT), отсюда настройки полей.

Протокол: https://tigra-electronic.com/articles/guestance-multithread-communication.html
"""
from __future__ import annotations

import asyncio
import base64
import csv
import io
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

import httpx

from ..config import CounterAddress, LaserConfig
from ..models import DailyCount, SourceObject
from .base import SourceError

log = logging.getLogger("attendance.guestance")

# коды событий из руководства по эксплуатации
EVENT_ON = 1
EVENT_OFF = 2
EVENT_TIME = 3
EVENT_PASSWORD = 4
EVENT_LOGIN = 5
EVENT_CARD_CHANGE = 6
EVENT_UPDATE_LOAD = 7
EVENT_UPDATE_COMPLETE = 8
EVENT_UPDATE_FAIL = 9
EVENT_INNOW = 10
EVENT_INOUT = 11
EVENT_EMITTER_SHOW = 12
EVENT_EMITTER_HIDE = 13
EVENT_EMAIL = 23
EVENT_CARD = 25

_SERIAL_RE = re.compile(r"<serial>\s*(\d+)\s*</serial>", re.IGNORECASE)
_MOMENT_RE = re.compile(r"^\s*(\d{1,4})/(\d{1,2})/(\d{1,4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$")
_FILE_SERIAL_RE = re.compile(r"(\d+)")


_EPOCH = date(1970, 1, 1)


def _days_param(day_from: Optional[date], day_to: Optional[date]) -> str:
    """Значение параметра ``d``: номер суток, диапазон или ``a`` (весь журнал)."""
    if day_from is None or day_to is None:
        return "a"
    first, last = sorted(((day_from - _EPOCH).days, (day_to - _EPOCH).days))
    return str(first) if first == last else f"{first}-{last}"


def _reason(exc: BaseException) -> str:
    """Текст исключения; у таймаутов httpx он пустой - тогда имя класса."""
    return str(exc) or type(exc).__name__


@dataclass(frozen=True)
class JournalRow:
    moment: datetime
    event: int
    fields: tuple[str, ...]

    def value(self, column: int) -> Optional[int]:
        """Целое значение поля строки; ``None``, если поля нет или оно не число."""
        if column < 0 or column >= len(self.fields):
            return None
        text = self.fields[column].strip()
        try:
            return int(text)
        except ValueError:
            return None


def parse_moment(text: str) -> Optional[datetime]:
    """``ДД/ММ/ГГ ЧЧ:ММ`` (терпимо и к ``ГГГГ/ММ/ДД``); нулевой год - время не установлено, None."""
    match = _MOMENT_RE.match(text)
    if not match:
        return None
    first, second, third, hour, minute, second_of_minute = match.groups()
    if len(first) == 4:  # ГГГГ/ММ/ДД
        year, month, day = int(first), int(second), int(third)
    else:  # ДД/ММ/ГГ - основной формат счётчика
        day, month, year = int(first), int(second), int(third)
        if year == 0:
            return None
        if year < 100:
            year += 2000
    try:
        return datetime(year, month, day, int(hour), int(minute), int(second_of_minute or 0))
    except ValueError:
        return None


def parse_journal(text: str) -> list[JournalRow]:
    """Разбирает CSV-журнал счётчика, молча пропуская нераспознанные строки."""
    rows: list[JournalRow] = []
    for parts in csv.reader(io.StringIO(text)):
        if len(parts) < 2:
            continue
        moment = parse_moment(parts[0])
        if moment is None:
            continue
        try:
            event = int(parts[1].strip())
        except ValueError:
            continue
        rows.append(JournalRow(moment=moment, event=event, fields=tuple(parts)))
    return rows


def daily_counts(
    rows: Iterable[JournalRow],
    external_id: str,
    name: str,
    *,
    count_events: Iterable[int] = (EVENT_INNOW,),
    entered_column: int = 2,
    exited_column: int = 4,
) -> list[DailyCount]:
    """Суммирует события прохода по суткам."""
    wanted = set(count_events)
    per_day: dict[date, list[int]] = {}
    for row in rows:
        if row.event not in wanted:
            continue
        bucket = per_day.setdefault(row.moment.date(), [0, 0, 0])
        bucket[0] += row.value(entered_column) or 0
        bucket[1] += row.value(exited_column) or 0
        bucket[2] += 1
    return [
        DailyCount(
            external_id=external_id,
            name=name,
            day=day,
            entered=entered,
            exited=exited,
            raw={"source": "guestance", "events": events},
        )
        for day, (entered, exited, events) in sorted(per_day.items())
    ]


class GuestanceSource:
    """Опрос счётчиков «Посещаемость» и приведение журналов к посуточным значениям."""

    code = "laser"
    title = "Посещаемость"

    def __init__(self, config: LaserConfig, client: Optional[httpx.AsyncClient] = None):
        self.config = config
        self._client = client
        self._own_client = client is None
        #: адреса счётчиков, которые не ответили при последнем сборе
        self.errors: list[str] = []

    async def __aenter__(self) -> "GuestanceSource":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._own_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client

    def division_name(self, serial: str, label: str = "") -> str:
        """Название подразделения для счётчика: карта серийников, затем подпись адреса."""
        return self.config.counter_names.get(serial) or label or f"Счётчик {serial}"

    async def list_objects(self) -> list[SourceObject]:
        today = date.today()  # журнал нужен только ради серийника - берём одни сутки
        return [
            SourceObject(external_id=serial, name=self.division_name(serial, label), raw={"host": host})
            for serial, label, host, _ in await self._collect(today, today)
        ]

    async def fetch_daily(self, day_from: date, day_to: date) -> list[DailyCount]:
        if day_from > day_to:
            day_from, day_to = day_to, day_from
        counts: list[DailyCount] = []
        for serial, label, _host, journal in await self._collect(day_from, day_to):
            counts.extend(
                daily_counts(
                    parse_journal(journal),
                    external_id=serial,
                    name=self.division_name(serial, label),
                    count_events=self.config.count_events,
                    entered_column=self.config.entered_column,
                    exited_column=self.config.exited_column,
                )
            )
        return [c for c in counts if day_from <= c.day <= day_to]

    async def _collect(
        self, day_from: Optional[date] = None, day_to: Optional[date] = None
    ) -> list[tuple[str, str, str, str]]:
        """Журналы всех счётчиков: ``(серийник, подпись, адрес, текст журнала)``."""
        if self.config.journal_dir is not None:
            return self._read_dir(self.config.journal_dir)
        if not self.config.counters:
            raise SourceError("Не задан LASER_COUNTERS: неизвестно, какие счётчики опрашивать")
        days = _days_param(day_from, day_to)
        results = await asyncio.gather(
            *(self._read_counter(addr, days) for addr in self.config.counters), return_exceptions=True
        )
        collected: list[tuple[str, str, str, str]] = []
        self.errors = []
        for addr, result in zip(self.config.counters, results):
            if isinstance(result, BaseException):
                # не warning: адрес и так уезжает в errors и в примечание прогона
                log.info("Счётчик %s недоступен: %s", addr.host, result)
                self.errors.append(f"{addr.host}: {result}")
                continue
            collected.append(result)
        if not collected:
            raise SourceError("Ни один счётчик не ответил - " + "; ".join(self.errors))
        return collected

    def _read_dir(self, directory: Path) -> list[tuple[str, str, str, str]]:
        """Журналы из каталога с файлами ``<серийник>_journal.csv``."""
        if not directory.is_dir():
            raise SourceError(f"Каталог журналов не найден: {directory}")
        labels = {addr.host: addr.label for addr in self.config.counters}
        collected: list[tuple[str, str, str, str]] = []
        for path in sorted(directory.glob("*.csv")):
            match = _FILE_SERIAL_RE.match(path.stem)
            serial = match.group(1) if match else path.stem
            text = path.read_bytes().decode(self.config.journal_encoding, errors="replace")
            collected.append((serial, labels.get(serial, ""), str(path), text))
        if not collected:
            raise SourceError(f"В каталоге {directory} нет файлов журналов (*.csv)")
        return collected

    async def _read_counter(self, addr: CounterAddress, days: str = "a") -> tuple[str, str, str, str]:
        serial = _SERIAL_RE.search(await self._get(addr, self.config.id_path))
        if not serial:
            raise SourceError("ответ /id.xml без серийного номера")
        journal_path = self.config.journal_path.replace("{days}", days)
        return serial.group(1), addr.label, addr.host, await self._get(addr, journal_path)

    async def _get(self, addr: CounterAddress, path: str) -> str:
        host = addr.host if "://" in addr.host else f"http://{addr.host}"
        raw = f"{self.config.counter_user}:{self.config.counter_password}".encode("utf-8")
        headers = {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
        try:
            response = await self.client.get(host + path, headers=headers, timeout=self.config.timeout)
        except httpx.HTTPError as exc:
            raise SourceError(f"{path} - {_reason(exc)}") from exc
        if response.status_code >= 400:
            raise SourceError(f"{path} - HTTP {response.status_code}")
        return response.content.decode(self.config.journal_encoding, errors="replace")
