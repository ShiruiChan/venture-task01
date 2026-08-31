"""HTTP-слой: серверный дашборд (Jinja2 + HTMX) и JSON-API."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analytics, charts, db, sync
from .config import BASE_DIR, settings
from .models import SOURCE_LASER, SOURCE_RARUS, SOURCE_TITLES, STATUS_TITLES
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
        )
        scheduler.start()
        log.info("Автосбор включён: каждые %s мин", settings.sync_interval_minutes)
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


app = FastAPI(title="Посещаемость подразделений БМ", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
templates.env.globals.update(
    STATUS_TITLES=STATUS_TITLES,
    SOURCE_TITLES=SOURCE_TITLES,
    PRESETS=PRESETS,
    settings=settings,
)


def _fmt(value: Optional[float], digits: int = 0, plus: bool = False) -> str:
    if value is None:
        return "—"
    text = f"{value:+,.{digits}f}" if plus else f"{value:,.{digits}f}"
    return text.replace(",", " ")


templates.env.filters["num"] = _fmt
templates.env.filters["pct"] = lambda v: "—" if v is None else f"{v:+.1f} %".replace(".", ",")


# --- страницы ------


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, period: PeriodParams = Depends()):
    rows = analytics.build_comparison(period.day_from, period.day_to, period.division_id)
    summary = analytics.summarize_divisions(rows)
    totals = analytics.daily_totals(rows)
    issues = analytics.discrepancies(rows)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "period": period,
            "divisions": db.list_divisions(),
            "overall": analytics.overall(rows),
            "summary": summary,
            "issues": issues[:50],
            "issues_total": len(issues),
            "chart": charts.line_chart(
                totals,
                [("rarus", SOURCE_TITLES[SOURCE_RARUS], "s-rarus"), ("laser", SOURCE_TITLES[SOURCE_LASER], "s-laser")],
            ),
            "delta_chart": charts.bar_chart(summary, "mean_abs_pct", "division_name"),
            "runs": db.recent_runs(5),
            "data_range": db.data_range(),
        },
    )


@app.get("/division/{division}", response_class=HTMLResponse)
async def division_detail(request: Request, division: int, period: PeriodParams = Depends()):
    # имя пути отличается от query-параметра division_id: FastAPI не допускает совпадения
    division_id = division
    rows = analytics.build_comparison(period.day_from, period.day_to, division_id, include_empty_days=True)
    totals = analytics.daily_totals(rows)
    division = next((d for d in db.list_divisions() if d.id == division_id), None)
    th = settings.thresholds
    return templates.TemplateResponse(
        request,
        "division.html",
        {
            "period": period,
            "division": division,
            "divisions": db.list_divisions(),
            "rows": [
                {
                    "day": r.day,
                    "rarus": r.rarus,
                    "laser": r.laser,
                    "delta": r.delta,
                    "delta_pct": r.delta_pct,
                    "status": r.status(th.warn_pct, th.critical_pct, th.min_abs),
                }
                for r in sorted(rows, key=lambda r: r.day, reverse=True)
            ],
            "overall": analytics.overall(rows),
            "chart": charts.line_chart(
                totals,
                [("rarus", SOURCE_TITLES[SOURCE_RARUS], "s-rarus"), ("laser", SOURCE_TITLES[SOURCE_LASER], "s-laser")],
            ),
        },
    )


@app.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request):
    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            "links": db.list_source_links(),
            "divisions": db.list_divisions(),
            "runs": db.recent_runs(30),
            "laser_mode": settings.laser.mode,
            "rarus_ready": settings.rarus.enabled,
        },
    )


@app.post("/sync")
async def trigger_sync(
    request: Request,
    days: int = Form(14),
    redirect_to: str = Form("/"),
):
    day_from, day_to = sync.default_range(max(1, min(days, 400)))
    await sync.sync_all(day_from, day_to)
    return RedirectResponse(redirect_to, status_code=303)


@app.post("/mapping")
async def update_mapping(
    source: str = Form(...),
    external_id: str = Form(...),
    division_id: int = Form(...),
):
    with db.connect() as conn:
        db.remap_source_object(conn, source, external_id, division_id)
    return RedirectResponse("/sources", status_code=303)


# --- JSON API ------


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


@app.post("/api/sync")
async def api_sync(days: int = Query(14)):
    day_from, day_to = sync.default_range(max(1, min(days, 400)))
    return await sync.sync_all(day_from, day_to)


@app.get("/api/rarus/hourly")
async def api_rarus_hourly(day: Optional[str] = Query(None)):
    """Прямой прокси виджета «Посещаемость по часам» — детализация внутри суток."""
    target = date.fromisoformat(day) if day else date.today()
    try:
        async with RarusSource(settings.rarus) as source:
            return {"date": target.isoformat(), "series": await source.fetch_hourly(target)}
    except SourceError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/api/runs")
async def api_runs(limit: int = Query(20, le=200)):
    return db.recent_runs(limit)
