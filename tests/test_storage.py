from datetime import date

from app import db
from app.models import SOURCE_LASER, SOURCE_RARUS, DailyCount


def test_save_is_idempotent(temp_db):
    day = date(2026, 8, 30)
    db.save_counts(SOURCE_RARUS, [DailyCount("o", "Объект", day, 100)], temp_db)
    db.save_counts(SOURCE_RARUS, [DailyCount("o", "Объект", day, 412)], temp_db)
    rows = db.fetch_counts(day, day, db_path=temp_db)
    assert len(rows) == 1 and rows[0]["entered"] == 412


def test_split_name():
    assert db.split_name("Планета Электро, Якутск, Бестужева-Марлинского 64-1") == (
        "Якутск",
        "Бестужева-Марлинского 64-1",
    )
    assert db.split_name("Объект") == ("", "")


def test_remap_merges_sources_into_one_division(temp_db):
    day = date(2026, 8, 30)
    db.save_counts(SOURCE_RARUS, [DailyCount("r-1", "Планета Электро, Якутск", day, 400)], temp_db)
    db.save_counts(SOURCE_LASER, [DailyCount("l-9", "ТЦ Планета (Якутск)", day, 420)], temp_db)
    assert len(db.list_divisions()) == 2

    target = next(d.id for d in db.list_divisions() if d.name.startswith("Планета Электро"))
    with db.connect(temp_db) as conn:
        db.remap_source_object(conn, SOURCE_LASER, "l-9", target)

    rows = db.fetch_counts(day, day, division_id=target, db_path=temp_db)
    assert {r["source"] for r in rows} == {SOURCE_RARUS, SOURCE_LASER}


def test_run_journal(temp_db):
    run_id = db.start_run(SOURCE_RARUS, date(2026, 8, 1), date(2026, 8, 2), temp_db)
    db.finish_run(run_id, "ok", 14, "", temp_db)
    run = db.recent_runs(1, temp_db)[0]
    assert run["status"] == "ok" and run["rows"] == 14
