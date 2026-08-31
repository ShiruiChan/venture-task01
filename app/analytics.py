"""Сравнение источников и агрегаты за период."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Optional

from . import db
from .config import Thresholds, settings
from .models import SOURCE_LASER, SOURCE_RARUS, ComparisonRow


def daterange(day_from: date, day_to: date) -> list[date]:
    days = (day_to - day_from).days
    return [day_from + timedelta(days=i) for i in range(days + 1)]


def build_comparison(
    day_from: date,
    day_to: date,
    division_id: Optional[int] = None,
    include_empty_days: bool = False,
) -> list[ComparisonRow]:
    """Строки «подразделение × сутки» с показателями обоих источников."""
    raw = db.fetch_counts(day_from, day_to, division_id)
    by_key: dict[tuple[int, str], dict[str, Any]] = {}
    names: dict[int, str] = {}
    for row in raw:
        key = (row["division_id"], row["day"])
        names[row["division_id"]] = row["division_name"]
        bucket = by_key.setdefault(key, {})
        bucket[row["source"]] = row["entered"]

    if include_empty_days:
        for division in db.list_divisions():
            if division_id is not None and division.id != division_id:
                continue
            names[division.id] = division.name
            for day in daterange(day_from, day_to):
                by_key.setdefault((division.id, day.isoformat()), {})

    rows = [
        ComparisonRow(
            division_id=div_id,
            division_name=names.get(div_id, str(div_id)),
            day=date.fromisoformat(day),
            rarus=values.get(SOURCE_RARUS),
            laser=values.get(SOURCE_LASER),
        )
        for (div_id, day), values in by_key.items()
    ]
    rows.sort(key=lambda r: (r.division_name, r.day))
    return rows


def summarize_divisions(rows: list[ComparisonRow], thresholds: Optional[Thresholds] = None) -> list[dict[str, Any]]:
    """Итоги по каждому подразделению за период."""
    th = thresholds or settings.thresholds
    grouped: dict[int, list[ComparisonRow]] = defaultdict(list)
    for row in rows:
        grouped[row.division_id].append(row)

    result: list[dict[str, Any]] = []
    for division_id, division_rows in grouped.items():
        statuses = [r.status(th.warn_pct, th.critical_pct, th.min_abs) for r in division_rows]
        rarus_values = [r.rarus for r in division_rows if r.rarus is not None]
        laser_values = [r.laser for r in division_rows if r.laser is not None]
        both = _comparable(division_rows, statuses)

        rarus_total = sum(rarus_values) if rarus_values else None
        laser_total = sum(laser_values) if laser_values else None
        matched_rarus = sum(r.rarus or 0 for r in both)
        matched_laser = sum(r.laser or 0 for r in both)

        delta = laser_total - rarus_total if rarus_total is not None and laser_total is not None else None
        delta_pct = (delta / max(abs(rarus_total), 1) * 100.0) if delta is not None else None
        # средний модуль дневного расхождения — не даёт плюсам и минусам гасить друг друга
        mape = (
            sum(abs(r.delta_pct or 0.0) for r in both) / len(both) if both else None
        )

        result.append(
            {
                "division_id": division_id,
                "division_name": division_rows[0].division_name,
                "days": len(division_rows),
                "days_matched": len(both),
                "rarus_total": rarus_total,
                "laser_total": laser_total,
                "matched_rarus_total": matched_rarus,
                "matched_laser_total": matched_laser,
                "delta": delta,
                "delta_pct": delta_pct,
                "mean_abs_pct": mape,
                "max_day_pct": max((abs(r.delta_pct or 0.0) for r in both), default=None),
                "critical_days": statuses.count("critical"),
                "warn_days": statuses.count("warn"),
                "missing_days": statuses.count("missing_rarus") + statuses.count("missing_laser"),
                "idle_days": statuses.count("idle_laser"),
                "status": worst_status(statuses),
            }
        )
    result.sort(key=lambda item: (-(item["mean_abs_pct"] or 0.0), item["division_name"]))
    return result


_STATUS_ORDER = ["no_data", "ok", "idle_laser", "missing_laser", "missing_rarus", "warn", "critical"]


def _comparable(rows: list[ComparisonRow], statuses: list[str]) -> list[ComparisonRow]:
    """Сутки, которые можно сравнивать: оба источника на месте и счётчик не молчал."""
    return [
        row
        for row, status in zip(rows, statuses)
        if row.rarus is not None and row.laser is not None and status != "idle_laser"
    ]


def worst_status(statuses: list[str]) -> str:
    if not statuses:
        return "no_data"
    return max(statuses, key=lambda s: _STATUS_ORDER.index(s) if s in _STATUS_ORDER else 0)


def daily_totals(rows: list[ComparisonRow]) -> list[dict[str, Any]]:
    """Суммарная динамика по дням для графика."""
    by_day: dict[date, dict[str, Optional[int]]] = defaultdict(lambda: {"rarus": None, "laser": None})
    for row in rows:
        bucket = by_day[row.day]
        if row.rarus is not None:
            bucket["rarus"] = (bucket["rarus"] or 0) + row.rarus
        if row.laser is not None:
            bucket["laser"] = (bucket["laser"] or 0) + row.laser
    out = []
    for day in sorted(by_day):
        values = by_day[day]
        rarus, laser = values["rarus"], values["laser"]
        out.append(
            {
                "day": day.isoformat(),
                "rarus": rarus,
                "laser": laser,
                "delta": (laser - rarus) if rarus is not None and laser is not None else None,
            }
        )
    return out


def overall(rows: list[ComparisonRow], thresholds: Optional[Thresholds] = None) -> dict[str, Any]:
    """Сводка по периоду целиком."""
    th = thresholds or settings.thresholds
    statuses = [r.status(th.warn_pct, th.critical_pct, th.min_abs) for r in rows]
    both = _comparable(rows, statuses)
    rarus_total = sum(r.rarus for r in rows if r.rarus is not None)
    laser_total = sum(r.laser for r in rows if r.laser is not None)
    matched_rarus = sum(r.rarus or 0 for r in both)
    delta = laser_total - rarus_total
    return {
        "rarus_total": rarus_total,
        "laser_total": laser_total,
        "delta": delta,
        "delta_pct": delta / max(abs(rarus_total), 1) * 100.0 if rarus_total else 0.0,
        "mean_abs_pct": (sum(abs(r.delta_pct or 0.0) for r in both) / len(both)) if both else 0.0,
        "matched_rarus_total": matched_rarus,
        "rows": len(rows),
        "divisions": len({r.division_id for r in rows}),
        "critical": statuses.count("critical"),
        "warn": statuses.count("warn"),
        "missing": statuses.count("missing_rarus") + statuses.count("missing_laser"),
        "idle": statuses.count("idle_laser"),
        "ok": statuses.count("ok"),
    }


def discrepancies(rows: list[ComparisonRow], thresholds: Optional[Thresholds] = None) -> list[dict[str, Any]]:
    """Список проблемных суток, отсортированный по величине расхождения."""
    th = thresholds or settings.thresholds
    items = []
    for row in rows:
        status = row.status(th.warn_pct, th.critical_pct, th.min_abs)
        if status == "ok" or status == "no_data":
            continue
        items.append(
            {
                "division_id": row.division_id,
                "division_name": row.division_name,
                "day": row.day.isoformat(),
                "rarus": row.rarus,
                "laser": row.laser,
                "delta": row.delta,
                "delta_pct": row.delta_pct,
                "status": status,
            }
        )
    items.sort(key=lambda item: (abs(item["delta_pct"] or 10_000), abs(item["delta"] or 0)), reverse=True)
    return items
