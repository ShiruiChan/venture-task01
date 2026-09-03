"""Коннектор к счётчикам «Лазер».

Боевых доступов к API пока нет, поэтому два режима (``LASER_MODE``): ``http`` -
реальный API, разбор терпим к именованию полей (правки - в ``_parse_daily`` и
``_parse_objects``); ``fixture`` - демо из ``data/laser_fixture.json`` либо
детерминированная генерация, чтобы сквозной сценарий был проверяемым.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import httpx

from ..config import LaserConfig
from ..models import DailyCount, SourceObject
from .base import SourceError

_ENTERED_KEYS = ("entered", "enter", "in", "count", "visitors", "total", "value", "enters")
_EXITED_KEYS = ("exited", "exit", "out", "outs")
_ID_KEYS = ("object_id", "objectId", "external_id", "id", "device_id", "counter_id")
_NAME_KEYS = ("name", "object_name", "objectName", "title", "label", "object")
_DATE_KEYS = ("date", "day", "dt", "datetime", "timestamp", "ts")


def _first(item: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000.0 if float(value) > 1e11 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc).date()
    text = str(value).strip()
    if text.isdigit():
        return _to_date(int(text))
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


class LaserSource:
    code = "laser"
    title = "Лазер"

    def __init__(
        self,
        config: LaserConfig,
        client: Optional[httpx.AsyncClient] = None,
        fallback_objects: Optional[list[SourceObject]] = None,
    ):
        self.config = config
        self._client = client
        self._own_client = client is None
        self._token: Optional[str] = None
        # используются fixture-режимом, когда файла с выгрузкой нет
        self.fallback_objects = fallback_objects or []

    async def __aenter__(self) -> "LaserSource":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._own_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def is_fixture(self) -> bool:
        return self.config.mode != "http"

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.config.base_url, timeout=self.config.timeout)
        return self._client

    async def list_objects(self) -> list[SourceObject]:
        if self.is_fixture:
            return self._fixture_objects()
        body = await self._request(self.config.objects_path, {})
        return self._parse_objects(body)

    async def fetch_daily(self, day_from: date, day_to: date) -> list[DailyCount]:
        if day_from > day_to:
            day_from, day_to = day_to, day_from
        if self.is_fixture:
            return self._fixture_daily(day_from, day_to)
        body = await self._request(
            self.config.daily_path,
            {"date_from": day_from.isoformat(), "date_to": day_to.isoformat()},
        )
        return [c for c in self._parse_daily(body) if day_from <= c.day <= day_to]

    async def _auth_headers(self) -> dict[str, str]:
        mode = self.config.auth_mode
        if mode == "bearer" and self.config.token:
            return {"Authorization": f"Bearer {self.config.token}"}
        if mode == "basic" and self.config.user:
            raw = f"{self.config.user}:{self.config.password}".encode("utf-8")
            return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
        if mode == "login":
            if self._token is None:
                self._token = await self._login()
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def _login(self) -> str:
        response = await self.client.post(
            self.config.login_path,
            data={"user": self.config.user, "password": self.config.password},
        )
        if response.status_code >= 400:
            raise SourceError(f"Лазер: авторизация - HTTP {response.status_code}")
        body = response.json()
        token = body.get("access_token") or (body.get("data") or {}).get("access_token") or body.get("token")
        if not token:
            raise SourceError("Лазер: ответ авторизации не содержит токен")
        return token

    async def _request(self, path: str, params: dict[str, Any]) -> Any:
        if not self.config.base_url:
            raise SourceError("Не задан LASER_BASE_URL для режима http")
        for attempt in (1, 2):
            headers = await self._auth_headers()
            response = await self.client.get(path, params=params, headers=headers)
            if response.status_code in (401, 403) and attempt == 1 and self.config.auth_mode == "login":
                self._token = None
                continue
            if response.status_code >= 400:
                raise SourceError(f"Лазер: {path} - HTTP {response.status_code}")
            try:
                return response.json()
            except ValueError as exc:
                raise SourceError(f"Лазер: {path} - некорректный JSON") from exc
        raise SourceError(f"Лазер: {path} - не удалось получить данные")

    @staticmethod
    def _rows(body: Any) -> list[dict[str, Any]]:
        """Достаёт список записей из типичных обёрток ответа."""
        if isinstance(body, list):
            return [r for r in body if isinstance(r, dict)]
        if isinstance(body, dict):
            for key in ("data", "items", "rows", "result", "records", "series"):
                value = body.get(key)
                if isinstance(value, list):
                    return [r for r in value if isinstance(r, dict)]
                if isinstance(value, dict):
                    return LaserSource._rows(value)
        return []

    @staticmethod
    def _parse_objects(body: Any) -> list[SourceObject]:
        objects: list[SourceObject] = []
        for row in LaserSource._rows(body):
            name = _first(row, _NAME_KEYS)
            ident = _first(row, _ID_KEYS)
            if name is None and ident is None:
                continue
            objects.append(
                SourceObject(external_id=str(ident if ident is not None else name), name=str(name or ident), raw=row)
            )
        return objects

    @staticmethod
    def _parse_daily(body: Any) -> list[DailyCount]:
        counts: list[DailyCount] = []
        for row in LaserSource._rows(body):
            day = _to_date(_first(row, _DATE_KEYS))
            entered = _to_int(_first(row, _ENTERED_KEYS))
            if day is None or entered is None:
                continue
            name = _first(row, _NAME_KEYS)
            ident = _first(row, _ID_KEYS)
            if ident is None and name is None:
                continue
            counts.append(
                DailyCount(
                    external_id=str(ident if ident is not None else name),
                    name=str(name or ident),
                    day=day,
                    entered=entered,
                    exited=_to_int(_first(row, _EXITED_KEYS)),
                    raw=row,
                )
            )
        return counts

    def _fixture_body(self) -> Optional[dict[str, Any]]:
        path = self.config.fixture_path
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise SourceError(f"Лазер: не читается файл выгрузки {path}: {exc}") from exc

    def _fixture_objects(self) -> list[SourceObject]:
        body = self._fixture_body()
        if body:
            objects = self._parse_objects(body.get("objects") or body)
            if objects:
                return objects
        return list(self.fallback_objects)

    def _fixture_daily(self, day_from: date, day_to: date) -> list[DailyCount]:
        body = self._fixture_body()
        if body is not None:
            rows = body.get("daily") if isinstance(body, dict) else body
            counts = [c for c in self._parse_daily(rows) if day_from <= c.day <= day_to]
            if counts:
                return counts
        return self._generate(day_from, day_to)

    def _generate(self, day_from: date, day_to: date) -> list[DailyCount]:
        """Детерминированная генерация от базы 1С-Рарус из ``fallback_objects``, расхождение ±12 %."""
        counts: list[DailyCount] = []
        for obj in self.fallback_objects:
            per_day = obj.raw.get("daily") or {}
            base = int(obj.raw.get("entered") or 0)
            day = day_from
            while day <= day_to:
                seed = hashlib.sha256(f"{obj.external_id}|{day.isoformat()}".encode("utf-8")).digest()
                if seed[0] % 14 == 0:  # эмуляция пропуска выгрузки
                    day += timedelta(days=1)
                    continue
                deviation = ((seed[1] / 255.0) - 0.5) * 0.24  # ±12 %
                daily_base = int(per_day.get(day.isoformat()) or base or (100 + seed[2] % 400))
                entered = max(0, int(round(daily_base * (1 + deviation))))
                counts.append(
                    DailyCount(
                        external_id=obj.external_id,
                        name=obj.name,
                        day=day,
                        entered=entered,
                        exited=max(0, entered - seed[3] % 12),
                        raw={"generated": True},
                    )
                )
                day += timedelta(days=1)
        return counts
