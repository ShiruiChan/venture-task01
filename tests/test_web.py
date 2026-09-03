from datetime import date, timedelta

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.models import SOURCE_LASER, SOURCE_RARUS, DailyCount
from app.web import app, resolve_period


@pytest.fixture()
def client(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "autosync", False)
    today = date.today()
    for offset in range(3):
        day = today - timedelta(days=offset)
        db.save_counts(SOURCE_RARUS, [DailyCount("o", "Планета Электро, Якутск, Ленина 1", day, 400)], temp_db)
        db.save_counts(SOURCE_LASER, [DailyCount("o", "Планета Электро, Якутск, Ленина 1", day, 500)], temp_db)
    with TestClient(app) as c:
        yield c


def test_resolve_period_presets():
    today = date.today()
    assert resolve_period("today") == (today, today, "today")
    assert resolve_period("week")[0] == today - timedelta(days=6)
    assert resolve_period("month")[0] == today - timedelta(days=29)
    # перевёрнутый пользователем интервал нормализуется
    assert resolve_period("custom", "2026-08-30", "2026-08-01")[:2] == (date(2026, 8, 1), date(2026, 8, 30))
    # мусор в датах не роняет страницу, а откатывается к неделе
    assert resolve_period("custom", "не-дата", "тоже")[2] == "week"


def test_root_returns_service_info(client):
    """Сервер отдельный: в корне паспорт сервиса, а не HTML-дашборд."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["service"] == "attendance-api"


@pytest.mark.parametrize("path", ["/sources", "/division/1", "/static/app.css", "/app/"])
def test_no_webapp_routes(client, path):
    """Страниц и статики у сервера больше нет - этим занимается фронт."""
    assert client.get(path).status_code == 404


def test_cors_enabled_for_separate_frontend():
    assert any(m.cls is CORSMiddleware for m in app.user_middleware)


def test_api_comparison(client):
    body = client.get("/api/comparison", params={"preset": "week"}).json()
    assert body["overall"]["divisions"] == 1
    assert body["overall"]["delta"] == 300
    assert all(row["status"] == "critical" for row in body["rows"])


def test_api_discrepancies_sorted(client):
    items = client.get("/api/discrepancies", params={"preset": "week"}).json()
    assert items and items[0]["status"] == "critical"


def test_health(client):
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["data_to"] == date.today().isoformat()


def test_api_meta(client):
    meta = client.get("/api/meta").json()
    assert meta["presets"]["week"] == "7 дней"
    assert meta["sources"][SOURCE_RARUS] == "1С-Рарус"
    assert meta["thresholds"]["warn_pct"] == settings.thresholds.warn_pct


def test_api_sources_lists_links(client):
    body = client.get("/api/sources").json()
    assert body["links"] and body["links"][0]["external_id"] == "o"
    assert body["divisions"][0]["name"].startswith("Планета Электро")


def test_api_mapping_remaps_object(client):
    division_id = db.list_divisions()[0].id
    response = client.post(
        "/api/mapping",
        json={"source": SOURCE_LASER, "external_id": "o", "division_id": division_id},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
