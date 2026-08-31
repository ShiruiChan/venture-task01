from datetime import date

from app import analytics, db
from app.models import SOURCE_LASER, SOURCE_RARUS, ComparisonRow, DailyCount


def test_status_thresholds():
    row = ComparisonRow(1, "X", date(2026, 8, 1), rarus=1000, laser=1000)
    assert row.status(5, 15, 5) == "ok"
    assert ComparisonRow(1, "X", date(2026, 8, 1), 1000, 1080).status(5, 15, 5) == "warn"
    assert ComparisonRow(1, "X", date(2026, 8, 1), 1000, 1200).status(5, 15, 5) == "critical"
    # мелкая абсолютная разница не считается расхождением, даже если процент велик
    assert ComparisonRow(1, "X", date(2026, 8, 1), 10, 13).status(5, 15, 5) == "ok"
    assert ComparisonRow(1, "X", date(2026, 8, 1), None, 100).status(5, 15, 5) == "missing_rarus"
    assert ComparisonRow(1, "X", date(2026, 8, 1), 100, None).status(5, 15, 5) == "missing_laser"
    # счётчик прислал сутки, но не насчитал ни одного прохода
    assert ComparisonRow(1, "X", date(2026, 8, 1), 700, 0).status(5, 15, 5) == "idle_laser"
    # закрытый день: ноль у обоих — это не молчание счётчика
    assert ComparisonRow(1, "X", date(2026, 8, 1), 0, 0).status(5, 15, 5) == "ok"


def test_delta_pct_sign():
    assert ComparisonRow(1, "X", date(2026, 8, 1), 200, 180).delta == -20
    assert ComparisonRow(1, "X", date(2026, 8, 1), 200, 180).delta_pct == -10.0


def test_build_comparison_joins_sources(temp_db):
    day = date(2026, 8, 30)
    db.save_counts(SOURCE_RARUS, [DailyCount("obj-1", "Объект 1", day, 412)], temp_db)
    db.save_counts(SOURCE_LASER, [DailyCount("obj-1", "Объект 1", day, 455)], temp_db)

    rows = analytics.build_comparison(day, day)
    assert len(rows) == 1
    assert (rows[0].rarus, rows[0].laser, rows[0].delta) == (412, 455, 43)


def test_missing_source_is_reported(temp_db):
    day = date(2026, 8, 30)
    db.save_counts(SOURCE_RARUS, [DailyCount("obj-1", "Объект 1", day, 412)], temp_db)
    rows = analytics.build_comparison(day, day)
    assert rows[0].status(5, 15, 5) == "missing_laser"
    assert analytics.overall(rows)["missing"] == 1


def test_summarize_and_mean_abs_pct(temp_db):
    d1, d2 = date(2026, 8, 29), date(2026, 8, 30)
    db.save_counts(SOURCE_RARUS, [DailyCount("o", "Объект", d1, 100), DailyCount("o", "Объект", d2, 100)], temp_db)
    db.save_counts(SOURCE_LASER, [DailyCount("o", "Объект", d1, 120), DailyCount("o", "Объект", d2, 80)], temp_db)

    summary = analytics.summarize_divisions(analytics.build_comparison(d1, d2))[0]
    assert summary["rarus_total"] == 200 and summary["laser_total"] == 200
    assert summary["delta"] == 0  # суммы сходятся...
    assert summary["mean_abs_pct"] == 20.0  # ...но суточные расхождения по 20 %
    assert summary["status"] == "critical"


def test_daily_totals_keeps_gaps(temp_db):
    d1, d2 = date(2026, 8, 29), date(2026, 8, 30)
    db.save_counts(SOURCE_RARUS, [DailyCount("o", "Объект", d1, 10), DailyCount("o", "Объект", d2, 20)], temp_db)
    db.save_counts(SOURCE_LASER, [DailyCount("o", "Объект", d2, 25)], temp_db)
    totals = analytics.daily_totals(analytics.build_comparison(d1, d2))
    assert totals[0]["laser"] is None and totals[0]["delta"] is None
    assert totals[1]["delta"] == 5


def test_idle_counter_days_do_not_spoil_the_average(temp_db):
    d1, d2 = date(2026, 8, 27), date(2026, 8, 28)
    db.save_counts(SOURCE_RARUS, [DailyCount("o", "Объект", d1, 673), DailyCount("o", "Объект", d2, 678)], temp_db)
    # 27-го счётчик молчал, 28-го разошёлся с Рарусом на 10 %
    db.save_counts(SOURCE_LASER, [DailyCount("o", "Объект", d1, 0), DailyCount("o", "Объект", d2, 610)], temp_db)

    rows = analytics.build_comparison(d1, d2)
    over = analytics.overall(rows)
    assert (over["idle"], over["critical"], over["warn"]) == (1, 0, 1)
    # в среднее идут только сопоставимые сутки, иначе молчание дало бы ~55 %
    assert round(over["mean_abs_pct"], 1) == 10.0

    summary = analytics.summarize_divisions(rows)[0]
    assert summary["idle_days"] == 1 and summary["days_matched"] == 1
    assert round(summary["mean_abs_pct"], 1) == 10.0
    # суммы по источникам остаются как есть — они честно показывают провал
    assert summary["laser_total"] == 610 and summary["rarus_total"] == 1351
