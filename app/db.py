from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from .config import settings
from .models import DailyCount, Division

SCHEMA = """
CREATE TABLE IF NOT EXISTS divisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    city        TEXT NOT NULL DEFAULT '',
    address     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_links (
    source        TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    division_id   INTEGER NOT NULL REFERENCES divisions(id) ON DELETE CASCADE,
    external_name TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    PRIMARY KEY (source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_source_links_division ON source_links(division_id);

CREATE TABLE IF NOT EXISTS daily_counts (
    division_id INTEGER NOT NULL REFERENCES divisions(id) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    day         TEXT NOT NULL,
    entered     INTEGER NOT NULL DEFAULT 0,
    exited      INTEGER,
    raw         TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (division_id, source, day)
);
CREATE INDEX IF NOT EXISTS idx_daily_counts_day ON daily_counts(day);

CREATE TABLE IF NOT EXISTS sync_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    day_from    TEXT NOT NULL,
    day_to      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,
    rows        INTEGER NOT NULL DEFAULT 0,
    message     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sync_runs_started ON sync_runs(started_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path or settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def split_name(name: str) -> tuple[str, str]:
    """«Планета Электро, Якутск, Бестужева-Марлинского 64-1» → (город, адрес)."""
    parts = [p.strip() for p in name.split(",")]
    if len(parts) >= 3:
        return parts[1], ", ".join(parts[2:])
    if len(parts) == 2:
        return parts[1], ""
    return "", ""


def upsert_division(conn: sqlite3.Connection, name: str) -> int:
    city, address = split_name(name)
    row = conn.execute("SELECT id FROM divisions WHERE name = ?", (name,)).fetchone()
    if row:
        return int(row["id"])
    cursor = conn.execute(
        "INSERT INTO divisions (name, city, address, created_at) VALUES (?, ?, ?, ?)",
        (name, city, address, _now()),
    )
    return int(cursor.lastrowid)


def link_source_object(conn: sqlite3.Connection, source: str, external_id: str, name: str) -> int:
    """Возвращает id подразделения для объекта источника, создавая связь при первой встрече."""
    row = conn.execute(
        "SELECT division_id FROM source_links WHERE source = ? AND external_id = ?",
        (source, external_id),
    ).fetchone()
    if row:
        return int(row["division_id"])
    division_id = upsert_division(conn, name)
    conn.execute(
        "INSERT INTO source_links (source, external_id, division_id, external_name, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (source, external_id, division_id, name, _now()),
    )
    return division_id


def remap_source_object(conn: sqlite3.Connection, source: str, external_id: str, division_id: int) -> None:
    """Переносит объект источника на другое подразделение вместе с собранными показателями."""
    row = conn.execute(
        "SELECT division_id FROM source_links WHERE source = ? AND external_id = ?",
        (source, external_id),
    ).fetchone()
    if row is None or int(row["division_id"]) == division_id:
        return
    old_division_id = int(row["division_id"])
    # OR REPLACE: при конфликте за те же сутки побеждает переносимая строка
    conn.execute(
        "UPDATE OR REPLACE daily_counts SET division_id = ? WHERE source = ? AND division_id = ?",
        (division_id, source, old_division_id),
    )
    conn.execute(
        "UPDATE source_links SET division_id = ? WHERE source = ? AND external_id = ?",
        (division_id, source, external_id),
    )
    # осиротевшее подразделение удаляем, иначе висит пустой строкой в фильтрах дашборда
    orphan = conn.execute(
        "SELECT 1 FROM source_links WHERE division_id = ? "
        "UNION ALL SELECT 1 FROM daily_counts WHERE division_id = ? LIMIT 1",
        (old_division_id, old_division_id),
    ).fetchone()
    if orphan is None:
        conn.execute("DELETE FROM divisions WHERE id = ?", (old_division_id,))


def list_divisions(conn: Optional[sqlite3.Connection] = None) -> list[Division]:
    def _query(c: sqlite3.Connection) -> list[Division]:
        rows = c.execute("SELECT id, name, city, address FROM divisions ORDER BY name").fetchall()
        return [Division(id=r["id"], name=r["name"], city=r["city"], address=r["address"]) for r in rows]

    if conn is not None:
        return _query(conn)
    with connect() as c:
        return _query(c)


def list_source_links(conn: Optional[sqlite3.Connection] = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT sl.source, sl.external_id, sl.external_name, sl.division_id, d.name AS division_name "
        "FROM source_links sl JOIN divisions d ON d.id = sl.division_id "
        "ORDER BY d.name, sl.source"
    )
    if conn is not None:
        return [dict(r) for r in conn.execute(sql).fetchall()]
    with connect() as c:
        return [dict(r) for r in c.execute(sql).fetchall()]


def save_counts(source: str, counts: Iterable[DailyCount], db_path: Optional[Path] = None) -> int:
    """Сохраняет посуточные значения источника, создавая недостающие подразделения."""
    saved = 0
    with connect(db_path) as conn:
        for count in counts:
            division_id = link_source_object(conn, source, count.external_id, count.name)
            conn.execute(
                "INSERT INTO daily_counts (division_id, source, day, entered, exited, raw, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(division_id, source, day) DO UPDATE SET"
                "   entered = excluded.entered, exited = excluded.exited,"
                "   raw = excluded.raw, updated_at = excluded.updated_at",
                (
                    division_id,
                    source,
                    count.day.isoformat(),
                    int(count.entered),
                    count.exited,
                    json.dumps(count.raw, ensure_ascii=False) if count.raw else None,
                    _now(),
                ),
            )
            saved += 1
    return saved


def fetch_counts(
    day_from: date,
    day_to: date,
    division_id: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT dc.division_id, d.name AS division_name, dc.source, dc.day, dc.entered, dc.exited "
        "FROM daily_counts dc JOIN divisions d ON d.id = dc.division_id "
        "WHERE dc.day BETWEEN ? AND ?"
    )
    params: list[Any] = [day_from.isoformat(), day_to.isoformat()]
    if division_id is not None:
        sql += " AND dc.division_id = ?"
        params.append(division_id)
    sql += " ORDER BY d.name, dc.day, dc.source"
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def data_range(db_path: Optional[Path] = None) -> tuple[Optional[str], Optional[str]]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT MIN(day) AS a, MAX(day) AS b FROM daily_counts").fetchone()
    return (row["a"], row["b"]) if row else (None, None)


def start_run(source: str, day_from: date, day_to: date, db_path: Optional[Path] = None) -> int:
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO sync_runs (source, day_from, day_to, started_at, status) VALUES (?, ?, ?, ?, 'running')",
            (source, day_from.isoformat(), day_to.isoformat(), _now()),
        )
        return int(cursor.lastrowid)


def finish_run(run_id: int, status: str, rows: int = 0, message: str = "", db_path: Optional[Path] = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE sync_runs SET finished_at = ?, status = ?, rows = ?, message = ? WHERE id = ?",
            (_now(), status, rows, message[:1000], run_id),
        )


def recent_runs(limit: int = 20, db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
