"""JSON-API; дашборд (Nuxt) живёт отдельным процессом и ходит сюда по сети."""
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import analytics, db, sync
from .config import settings
from .models import SOURCE_TITLES, STATUS_TITLES
from .sources import RarusSource
from .sources.base import SourceError

log = logging.getLogger("attendance.web")

PRESETS = {
    "today": "Сегодня",
    "yesterday": "Вчера",
    "week": "7 дней",
    "month": "30 дней",
    "custom": "Период",
}


def resolve_period(
    preset: str = "week",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> tuple[date, date, str]:
    today = date.today()
    if preset == "custom" and date_from and date_to:
        try:
            start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
            return (start, end, "custom") if start <= end else (end, start, "custom")
        except ValueError:
            preset = "week"
    if preset == "today":
        return today, today, preset
    if preset == "yesterday":
        return today - timedelta(days=1), today - timedelta(days=1), preset
    if preset == "month":
        return today - timedelta(days=29), today, preset
    return today - timedelta(days=6), today, "week"


class PeriodParams:
    def __init__(
        self,
        preset: str = Query("week"),
        date_from: Optional[str] = Query(None),
        date_to: Optional[str] = Query(None),
        division_id: Optional[int] = Query(None),
    ):
        self.day_from, self.day_to, self.preset = resolve_period(preset, date_from, date_to)
        self.division_id = division_id

    def query(self, **overrides: Any) -> str:
        params = {
            "preset": self.preset,
            "date_from": self.day_from.isoformat(),
            "date_to": self.day_to.isoformat(),
        }
        if self.division_id is not None:
            params["division_id"] = str(self.division_id)
        params.update({k: v for k, v in overrides.items() if v is not None})
        return "&".join(f"{k}={v}" for k, v in params.items())


class MappingIn(BaseModel):
    """Переназначение объекта источника на другое подразделение."""

    source: str
    external_id: str
    division_id: int = Field(gt=0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    scheduler = None
    if settings.autosync:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            sync.sync_all,
            "interval",
            minutes=settings.sync_interval_minutes,
            id="sync_all",
            max_instances=1,
            coalesce=True,
            # без next_run_time interval-триггер ждёт целый интервал до первого сбора
            next_run_time=datetime.now(),
        )
        scheduler.start()
        log.info("Автосбор включён: сразу и далее каждые %s мин", settings.sync_interval_minutes)
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


app = FastAPI(title="Посещаемость подразделений БМ - API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Корень отдаёт паспорт сервиса, а не страницу: UI живёт отдельно."""
    return {
        "service": "attendance-api",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
        "api": "/api",
    }


@app.get("/health")
async def health():
    first, last = db.data_range()
    return {
        "status": "ok",
        "data_from": first,
        "data_to": last,
        "laser_mode": settings.laser.mode,
        "rarus_configured": settings.rarus.enabled,
    }


@app.get("/api/meta")
async def api_meta():
    """Справочники и пороги для фронта."""
    th = settings.thresholds
    return {
        "presets": PRESETS,
        "sources": SOURCE_TITLES,
        "statuses": STATUS_TITLES,
        "thresholds": {"warn_pct": th.warn_pct, "critical_pct": th.critical_pct, "min_abs": th.min_abs},
        "laser_mode": settings.laser.mode,
        "rarus_configured": settings.rarus.enabled,
    }


@app.get("/api/divisions")
async def api_divisions():
    return [d.__dict__ for d in db.list_divisions()]


@app.get("/api/comparison")
async def api_comparison(period: PeriodParams = Depends()):
    th = settings.thresholds
    rows = analytics.build_comparison(period.day_from, period.day_to, period.division_id)
    return {
        "date_from": period.day_from.isoformat(),
        "date_to": period.day_to.isoformat(),
        "overall": analytics.overall(rows),
        "divisions": analytics.summarize_divisions(rows),
        "rows": [
            {
                "division_id": r.division_id,
                "division_name": r.division_name,
                "day": r.day.isoformat(),
                "rarus": r.rarus,
                "laser": r.laser,
                "delta": r.delta,
                "delta_pct": r.delta_pct,
                "status": r.status(th.warn_pct, th.critical_pct, th.min_abs),
            }
            for r in rows
        ],
    }


@app.get("/api/discrepancies")
async def api_discrepancies(period: PeriodParams = Depends()):
    rows = analytics.build_comparison(period.day_from, period.day_to, period.division_id)
    return analytics.discrepancies(rows)


@app.get("/api/sources")
async def api_sources():
    """Сопоставление «объект источника - подразделение» и история запусков."""
    return {
        "links": db.list_source_links(),
        "divisions": [d.__dict__ for d in db.list_divisions()],
        "runs": db.recent_runs(30),
        "laser_mode": settings.laser.mode,
        "rarus_ready": settings.rarus.enabled,
    }


@app.post("/api/mapping")
async def api_mapping(body: MappingIn):
    with db.connect() as conn:
        db.remap_source_object(conn, body.source, body.external_id, body.division_id)
    return {"status": "ok", "links": db.list_source_links()}


@app.post("/api/sync")
async def api_sync(days: int = Query(14)):
    day_from, day_to = sync.default_range(max(1, min(days, 400)))
    return await sync.sync_all(day_from, day_to)


@app.get("/api/rarus/hourly")
async def api_rarus_hourly(day: Optional[str] = Query(None)):
    """Прямой прокси виджета «Посещаемость по часам» - детализация внутри суток."""
    target = date.fromisoformat(day) if day else date.today()
    try:
        async with RarusSource(settings.rarus) as source:
            return {"date": target.isoformat(), "series": await source.fetch_hourly(target)}
    except SourceError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/api/runs")
async def api_runs(limit: int = Query(20, le=200)):
    return db.recent_runs(limit)
