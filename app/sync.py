"""Сбор данных из источников и запись в хранилище."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from . import db
from .config import settings
from .models import SOURCE_LASER, SOURCE_RARUS, SourceObject
from .sources import GuestanceSource, LaserSource, RarusSource

log = logging.getLogger("attendance.sync")


def default_range(lookback_days: Optional[int] = None) -> tuple[date, date]:
    days = lookback_days if lookback_days is not None else settings.sync_lookback_days
    today = date.today()
    return today - timedelta(days=max(days - 1, 0)), today


async def sync_rarus(day_from: date, day_to: date) -> dict[str, Any]:
    run_id = db.start_run(SOURCE_RARUS, day_from, day_to)
    try:
        async with RarusSource(settings.rarus) as source:
            counts = await source.fetch_daily(day_from, day_to)
        saved = db.save_counts(SOURCE_RARUS, counts)
        db.finish_run(run_id, "ok", saved)
        return {"source": SOURCE_RARUS, "status": "ok", "rows": saved}
    except Exception as exc:  # сбор не должен ронять сервис
        log.exception("Сбой сбора 1С-Рарус")
        db.finish_run(run_id, "error", 0, str(exc))
        return {"source": SOURCE_RARUS, "status": "error", "rows": 0, "message": str(exc)}


def _rarus_baseline(day_from: date, day_to: date) -> list[SourceObject]:
    """Ориентиры для демо-режима «Лазера»: уже собранные значения 1С-Рарус."""
    rows = db.fetch_counts(day_from, day_to)
    per_object: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["source"] != SOURCE_RARUS:
            continue
        bucket = per_object.setdefault(
            row["division_name"], {"daily": {}, "entered": 0, "n": 0}
        )
        bucket["daily"][row["day"]] = row["entered"]
        bucket["entered"] += row["entered"]
        bucket["n"] += 1
    objects = []
    for name, bucket in per_object.items():
        average = int(bucket["entered"] / bucket["n"]) if bucket["n"] else 0
        objects.append(SourceObject(external_id=name, name=name, raw={"daily": bucket["daily"], "entered": average}))
    return objects


async def sync_laser(day_from: date, day_to: date) -> dict[str, Any]:
    run_id = db.start_run(SOURCE_LASER, day_from, day_to)
    mode = settings.laser.mode
    try:
        if mode == "guestance":
            source: Any = GuestanceSource(settings.laser)
        else:
            fallback = _rarus_baseline(day_from, day_to) if mode != "http" else []
            source = LaserSource(settings.laser, fallback_objects=fallback)
        async with source:
            counts = await source.fetch_daily(day_from, day_to)
        saved = db.save_counts(SOURCE_LASER, counts)
        notes = []
        if mode == "fixture":
            notes.append("демо-данные (доступы к счётчикам не заданы)")
        unreachable = list(getattr(source, "errors", []))
        for message in unreachable:
            notes.append(f"счётчик недоступен - {message}")
        note = "; ".join(notes)
        # часть счётчиков молчит: данные собраны не полностью, и это не «ok»
        status = "partial" if unreachable else "ok"
        db.finish_run(run_id, status, saved, note)
        return {"source": SOURCE_LASER, "status": status, "rows": saved, "message": note}
    except Exception as exc:
        log.exception("Сбой сбора Лазер")
        db.finish_run(run_id, "error", 0, str(exc))
        return {"source": SOURCE_LASER, "status": "error", "rows": 0, "message": str(exc)}


async def sync_all(day_from: Optional[date] = None, day_to: Optional[date] = None) -> list[dict[str, Any]]:
    """Полный цикл сбора. 1С-Рарус первым: его данные служат опорой демо-режима счётчиков."""
    if day_from is None or day_to is None:
        day_from, day_to = default_range()
    db.init_db()
    results = [await sync_rarus(day_from, day_to)]
    results.append(await sync_laser(day_from, day_to))
    return results
