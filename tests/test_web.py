from datetime import date, timedelta

import pytest
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


def test_dashboard_renders_divisions(client):
    response = client.get("/?preset=week")
    assert response.status_code == 200
    assert "Планета Электро" in response.text
    assert "Расхождение" in response.text


def test_api_comparison(client):
    body = client.get("/api/comparison", params={"preset": "week"}).json()
    assert body["overall"]["divisions"] == 1
    assert body["overall"]["delta"] == 300
    assert all(row["status"] == "critical" for row in body["rows"])


def test_api_discrepancies_sorted(client):
    items = client.get("/api/discrepancies", params={"preset": "week"}).json()
    assert items and items[0]["status"] == "critical"


def test_division_page_and_health(client):
    division_id = db.list_divisions()[0].id
    assert client.get(f"/division/{division_id}?preset=week").status_code == 200
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["data_to"] == date.today().isoformat()


def test_sources_page(client):
    response = client.get("/sources")
    assert response.status_code == 200
    assert "Сопоставление объектов" in response.text
