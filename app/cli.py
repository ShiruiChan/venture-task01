"""Командный интерфейс: сбор данных, выгрузка отчёта, запуск веб-сервиса."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import date, timedelta

from . import analytics, db, sync
from .config import settings
from .models import STATUS_TITLES


def _period(args: argparse.Namespace) -> tuple[date, date]:
    if args.date_from and args.date_to:
        return date.fromisoformat(args.date_from), date.fromisoformat(args.date_to)
    today = date.today()
    return today - timedelta(days=max(args.days - 1, 0)), today


def cmd_sync(args: argparse.Namespace) -> int:
    day_from, day_to = _period(args)
    print(f"Сбор за {day_from} — {day_to}")
    results = asyncio.run(sync.sync_all(day_from, day_to))
    failed = False
    marks = {"ok": "ok", "partial": "часть"}
    for result in results:
        mark = marks.get(result["status"], "сбой").ljust(5)
        print(f"  [{mark}] {result['source']}: {result['rows']} строк")
        for note in filter(None, result.get("message", "").split("; ")):
            print(f"          {note}")
        failed |= result["status"] not in ("ok", "partial")
    return 1 if failed else 0


def cmd_report(args: argparse.Namespace) -> int:
    day_from, day_to = _period(args)
    rows = analytics.build_comparison(day_from, day_to, args.division_id)
    if args.format == "json":
        json.dump(
            {
                "period": {"from": day_from.isoformat(), "to": day_to.isoformat()},
                "overall": analytics.overall(rows),
                "divisions": analytics.summarize_divisions(rows),
                "discrepancies": analytics.discrepancies(rows),
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        print()
        return 0
    if args.format == "csv":
        th = settings.thresholds
        writer = csv.writer(sys.stdout)
        writer.writerow(["подразделение", "дата", "1С-Рарус", "Лазер", "дельта", "дельта_%", "статус"])
        for row in rows:
            writer.writerow(
                [
                    row.division_name,
                    row.day.isoformat(),
                    row.rarus if row.rarus is not None else "",
                    row.laser if row.laser is not None else "",
                    row.delta if row.delta is not None else "",
                    f"{row.delta_pct:.2f}" if row.delta_pct is not None else "",
                    STATUS_TITLES[row.status(th.warn_pct, th.critical_pct, th.min_abs)],
                ]
            )
        return 0

    overall = analytics.overall(rows)
    print(f"Период {day_from} — {day_to}: подразделений {overall['divisions']}, записей {overall['rows']}")
    print(
        f"1С-Рарус {overall['rarus_total']}, Лазер {overall['laser_total']}, "
        f"расхождение {overall['delta']:+} ({overall['delta_pct']:+.1f} %), "
        f"среднее по дням {overall['mean_abs_pct']:.1f} %"
    )
    print(
        f"Проблемных суток: критично {overall['critical']}, внимание {overall['warn']}, "
        f"счётчик молчал {overall['idle']}, нет данных {overall['missing']}"
    )
    print()
    header = f"{'Подразделение':<52}{'Рарус':>10}{'Лазер':>10}{'Δ':>9}{'Δ %':>9}{'Ср|Δ|%':>9}"
    print(header)
    print("-" * len(header))
    for item in analytics.summarize_divisions(rows):
        print(
            f"{item['division_name'][:50]:<52}"
            f"{item['rarus_total'] or 0:>10}{item['laser_total'] or 0:>10}"
            f"{item['delta'] if item['delta'] is not None else 0:>+9}"
            f"{(item['delta_pct'] or 0):>+9.1f}{(item['mean_abs_pct'] or 0):>9.1f}"
        )
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("app.web:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="attendance", description="Сверка посещаемости подразделений БМ")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_period(p: argparse.ArgumentParser) -> None:
        p.add_argument("--days", type=int, default=settings.sync_lookback_days, help="глубина в днях от сегодня")
        p.add_argument("--date-from", dest="date_from", help="начало периода, ГГГГ-ММ-ДД")
        p.add_argument("--date-to", dest="date_to", help="конец периода, ГГГГ-ММ-ДД")

    p_sync = sub.add_parser("sync", help="собрать данные из источников")
    add_period(p_sync)
    p_sync.set_defaults(func=cmd_sync)

    p_report = sub.add_parser("report", help="отчёт по расхождениям")
    add_period(p_report)
    p_report.add_argument("--format", choices=("text", "json", "csv"), default="text")
    p_report.add_argument("--division-id", type=int, dest="division_id")
    p_report.set_defaults(func=cmd_report)

    p_serve = sub.add_parser("serve", help="запустить веб-сервис")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db.init_db()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
