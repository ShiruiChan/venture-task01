"""Коннектор к системе 1С-Рарус (backend.rarus-spp.ru).

Особенности API, выявленные при обследовании:

* авторизация - POST /login, ``application/x-www-form-urlencoded``; в ответе
  ``access_token`` (PASETO v2) и ``expire_at`` в миллисекундах;
* виджеты принимают только ``period=day`` и ``period=week``; произвольного
  интервала нет, поэтому история собирается пошагово, по суткам;
* разрез по подразделениям даёт только виджет ``objects-rating`` —
  ``series[].label`` содержит название объекта, ``total_current`` — число вошедших;
* ``series[].id`` у этого клиента всегда нулевой GUID, поэтому идентификатором
  объекта служит нормализованное название.
"""
from __future__ import annotations

import asyncio
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from ..config import RarusConfig
from ..models import DailyCount, SourceObject
from .base import SourceError

ZERO_GUID = "00000000-0000-0000-0000-000000000000"


def day_to_ms(day: date) -> int:
    """Полночь UTC указанных суток в миллисекундах — формат параметра ``date``."""
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)


def ms_to_datetime(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def normalize_name(name: str) -> str:
    return " ".join(name.split()).strip()


def _to_int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


class RarusSource:
    code = "rarus"
    title = "1С-Рарус"

    def __init__(self, config: RarusConfig, client: Optional[httpx.AsyncClient] = None):
        self.config = config
        self._client = client
        self._own_client = client is None
        self._token: Optional[str] = None
        self._token_expire_ms: int = 0
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "RarusSource":
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
            self._client = httpx.AsyncClient(base_url=self.config.base_url, timeout=self.config.timeout)
        return self._client

    # --- авторизация -----------------------------------------------------

    async def _authorize(self) -> str:
        if not self.config.enabled:
            raise SourceError("Не заданы учётные данные 1С-Рарус (RARUS_USER / RARUS_PASSWORD)")
        response = await self.client.post(
            "/login",
            data={"user": self.config.user, "password": self.config.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        payload = self._payload(response, "авторизация")
        token = payload.get("access_token")
        if not token:
            raise SourceError("Ответ авторизации 1С-Рарус не содержит access_token")
        self._token = token
        # запас в минуту, чтобы не попасть в момент истечения токена
        self._token_expire_ms = int(payload.get("expire_at") or 0) - 60_000
        return token

    async def _get_token(self) -> str:
        async with self._lock:
            if self._token and time.time() * 1000 < self._token_expire_ms:
                return self._token
            return await self._authorize()

    # --- низкоуровневые запросы -----------------------------------------

    @staticmethod
    def _payload(response: httpx.Response, what: str) -> dict[str, Any]:
        if response.status_code >= 400:
            raise SourceError(f"1С-Рарус: {what} — HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise SourceError(f"1С-Рарус: {what} — некорректный JSON") from exc
        if not body.get("success"):
            error = body.get("error") or {}
            raise SourceError(f"1С-Рарус: {what} — {body.get('message')} ({error.get('reason', '')})".strip())
        return body.get("data") or {}

    async def widget(self, name: str, period: str = "day", day: Optional[date] = None) -> dict[str, Any]:
        """Сырой ответ виджета. Токен обновляется автоматически, в т.ч. при 401."""
        target = day or date.today()
        params = {"period": period, "date": day_to_ms(target)}
        for attempt in (1, 2):
            token = await self._get_token()
            response = await self.client.get(
                f"/api/v1/widgets/{name}/fetch",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code in (401, 403) and attempt == 1:
                self._token = None
                continue
            try:
                return self._payload(response, f"виджет {name}")
            except SourceError:
                if attempt == 1:
                    self._token = None
                    continue
                raise
        raise SourceError(f"1С-Рарус: виджет {name} недоступен")

    # --- интерфейс VisitorSource ----------------------------------------

    async def list_objects(self) -> list[SourceObject]:
        data = await self.widget("objects-rating", "day", date.today())
        return [
            SourceObject(external_id=normalize_name(s.get("label", "")), name=normalize_name(s.get("label", "")), raw=s)
            for s in data.get("series") or []
            if s.get("label")
        ]

    async def fetch_daily(self, day_from: date, day_to: date) -> list[DailyCount]:
        if day_from > day_to:
            day_from, day_to = day_to, day_from
        result: list[DailyCount] = []
        day = day_from
        while day <= day_to:
            result.extend(await self.fetch_day(day))
            day += timedelta(days=1)
        return result

    async def fetch_day(self, day: date) -> list[DailyCount]:
        data = await self.widget("objects-rating", "day", day)
        counts: list[DailyCount] = []
        for series in data.get("series") or []:
            label = normalize_name(series.get("label", ""))
            if not label:
                continue
            external_id = series.get("id") or ZERO_GUID
            if external_id == ZERO_GUID:
                external_id = label
            counts.append(
                DailyCount(
                    external_id=external_id,
                    name=label,
                    day=day,
                    entered=_to_int(series.get("total_current")),
                    raw=series,
                )
            )
        return counts

    # --- дополнительные виджеты для дашборда -----------------------------

    async def fetch_today_totals(self, day: Optional[date] = None) -> dict[str, float]:
        """Виджет «Вошло/вышло сегодня» — сводные показатели клиента."""
        data = await self.widget("today", "day", day)
        return {
            normalize_name(s.get("label", "")): float(s.get("total_current") or 0)
            for s in data.get("series") or []
        }

    async def fetch_hourly(self, day: Optional[date] = None) -> list[dict[str, Any]]:
        """Виджет «Посещаемость по часам» для выбранных суток."""
        data = await self.widget("attendance-by-hour", "day", day)
        return self._series_points(data)

    async def fetch_by_day_of_week(self, day: Optional[date] = None) -> list[dict[str, Any]]:
        """Виджет «Посещаемость по дням недели»."""
        data = await self.widget("attendance-by-day-of-week", "week", day)
        return self._series_points(data)

    @staticmethod
    def _series_points(data: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for series in data.get("series") or []:
            points = [
                {"ts": int(p[0]), "at": ms_to_datetime(int(p[0])).isoformat(), "value": _to_int(p[1])}
                for p in series.get("points") or []
                if isinstance(p, (list, tuple)) and len(p) >= 2
            ]
            out.append(
                {
                    "label": normalize_name(series.get("label", "")),
                    "total": _to_int(series.get("total_current")),
                    "points": points,
                }
            )
        return out
