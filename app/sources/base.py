"""Единый интерфейс источника данных о посещаемости.

Любой новый источник (Лазер, 1С-Рарус, ручная выгрузка) реализует этот протокол,
после чего автоматически попадает в сбор, хранение и сравнение.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from ..models import DailyCount, SourceObject


class SourceError(RuntimeError):
    """Ошибка обращения к внешнему источнику."""


@runtime_checkable
class VisitorSource(Protocol):
    #: короткий код источника, совпадает со значением в БД (rarus / laser)
    code: str
    #: человекочитаемое название
    title: str

    async def list_objects(self) -> list[SourceObject]:
        """Список подразделений, доступных в источнике."""

    async def fetch_daily(self, day_from: date, day_to: date) -> list[DailyCount]:
        """Посуточная посещаемость по всем подразделениям за интервал включительно."""
