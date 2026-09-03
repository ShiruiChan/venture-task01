"""Общие структуры данных сервиса."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

SOURCE_RARUS = "rarus"
SOURCE_LASER = "laser"
SOURCE_TITLES = {SOURCE_RARUS: "1С-Рарус", SOURCE_LASER: "Лазер"}


@dataclass(frozen=True)
class SourceObject:
    """Подразделение в терминах конкретного источника."""

    external_id: str
    name: str
    raw: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class DailyCount:
    """Посещаемость одного подразделения за одни сутки по одному источнику."""

    external_id: str
    name: str
    day: date
    entered: int
    exited: Optional[int] = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass
class Division:
    id: int
    name: str
    city: str = ""
    address: str = ""


@dataclass
class ComparisonRow:
    """Строка сравнения источников за конкретные сутки."""

    division_id: int
    division_name: str
    day: date
    rarus: Optional[int]
    laser: Optional[int]

    @property
    def delta(self) -> Optional[int]:
        if self.rarus is None or self.laser is None:
            return None
        return self.laser - self.rarus

    @property
    def delta_pct(self) -> Optional[float]:
        """Расхождение в процентах от базы (1С-Рарус)."""
        if self.rarus is None or self.laser is None:
            return None
        base = max(abs(self.rarus), 1)
        return (self.laser - self.rarus) / base * 100.0

    def status(self, warn_pct: float, critical_pct: float, min_abs: float) -> str:
        """ok | warn | critical | idle_laser | missing_rarus | missing_laser | no_data"""
        if self.rarus is None and self.laser is None:
            return "no_data"
        if self.rarus is None:
            return "missing_rarus"
        if self.laser is None:
            return "missing_laser"
        delta = abs(self.delta or 0)
        pct = abs(self.delta_pct or 0.0)
        if delta < min_abs:
            return "ok"
        # ноль при живом Рарусе - молчание счётчика, а не расхождение
        if self.laser == 0:
            return "idle_laser"
        if pct >= critical_pct:
            return "critical"
        if pct >= warn_pct:
            return "warn"
        return "ok"


STATUS_TITLES = {
    "ok": "В норме",
    "warn": "Расхождение",
    "critical": "Критично",
    "idle_laser": "Счётчик не считал",
    "missing_rarus": "Нет данных 1С-Рарус",
    "missing_laser": "Нет данных Лазер",
    "no_data": "Нет данных",
}
