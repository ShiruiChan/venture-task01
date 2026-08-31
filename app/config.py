from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_pairs(name: str) -> list[tuple[str, str]]:
    """Разбирает список вида ``ключ=значение; ключ=значение``.

    Разделитель — точка с запятой или перевод строки, но не запятая: запятых
    хватает внутри названий подразделений («Планета Электро, Якутск, ...»).
    Значение необязательно, тогда во второй элемент пары попадает пустая строка.
    """
    pairs: list[tuple[str, str]] = []
    for chunk in re.split(r"[;\n]", _env(name)):
        chunk = chunk.strip()
        if not chunk:
            continue
        key, _, value = chunk.partition("=")
        pairs.append((key.strip(), value.strip()))
    return pairs


def _env_ints(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    values = tuple(int(x) for x in re.findall(r"\d+", _env(name)))
    return values or default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name) or default)
    except ValueError:
        return default


@dataclass
class RarusConfig:
    """Доступ к API 1С-Рарус (backend.rarus-spp.ru)."""

    base_url: str = field(default_factory=lambda: _env("RARUS_BASE_URL", "https://backend.rarus-spp.ru"))
    user: str = field(default_factory=lambda: _env("RARUS_USER"))
    password: str = field(default_factory=lambda: _env("RARUS_PASSWORD"))
    timeout: float = field(default_factory=lambda: _env_float("RARUS_TIMEOUT", 30.0))

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.user and self.password)


@dataclass(frozen=True)
class CounterAddress:
    """Адрес одного счётчика «Посещаемость»: ``host[:port]`` и необязательная подпись."""

    host: str
    label: str = ""


@dataclass
class LaserConfig:
    """Доступ к счётчикам посещаемости.

    Режим задаётся ``LASER_MODE``:

    ``guestance``
        Счётчики «Посещаемость» (TIGRA electronic). Центрального API у них нет:
        опрашивается каждое устройство по своему адресу из ``LASER_COUNTERS``.
    ``http``
        Гипотетический центральный REST API с посуточной агрегацией.
    ``fixture``
        Демо-режим: данные из data/laser_fixture.json либо детерминированная генерация.
    """

    mode: str = field(default_factory=lambda: _env("LASER_MODE", "fixture"))
    base_url: str = field(default_factory=lambda: _env("LASER_BASE_URL"))
    daily_path: str = field(default_factory=lambda: _env("LASER_DAILY_PATH", "/api/v1/counters/daily"))
    objects_path: str = field(default_factory=lambda: _env("LASER_OBJECTS_PATH", "/api/v1/objects"))
    auth_mode: str = field(default_factory=lambda: _env("LASER_AUTH_MODE", "bearer"))  # bearer|basic|login|none
    token: str = field(default_factory=lambda: _env("LASER_TOKEN"))
    user: str = field(default_factory=lambda: _env("LASER_USER"))
    password: str = field(default_factory=lambda: _env("LASER_PASSWORD"))
    login_path: str = field(default_factory=lambda: _env("LASER_LOGIN_PATH", "/login"))
    timeout: float = field(default_factory=lambda: _env_float("LASER_TIMEOUT", 30.0))
    fixture_path: Path = field(default_factory=lambda: Path(_env("LASER_FIXTURE", str(DATA_DIR / "laser_fixture.json"))))

    # --- режим guestance -------------------------------------------------
    #: адреса счётчиков: ``192.168.0.70; guest.advrouter.asuscomm.com:8009=ТЦ Планета``
    counters: tuple[CounterAddress, ...] = field(
        default_factory=lambda: tuple(CounterAddress(host, label) for host, label in _env_pairs("LASER_COUNTERS") if host)
    )
    #: соответствие «серийный номер счётчика — подразделение»: ``12345=Планета Электро, Якутск``
    counter_names: dict[str, str] = field(
        default_factory=lambda: {serial: name for serial, name in _env_pairs("LASER_COUNTER_NAMES") if serial and name}
    )
    #: каталог с выгруженными журналами ``<серийник>_journal.csv`` — работа без доступа к счётчикам
    journal_dir: Optional[Path] = field(
        default_factory=lambda: Path(_env("LASER_JOURNAL_DIR")) if _env("LASER_JOURNAL_DIR") else None
    )
    id_path: str = field(default_factory=lambda: _env("LASER_ID_PATH", "/id.xml"))
    #: путь к журналу; ``{days}`` заменяется на номер суток или диапазон (``d=a`` прошивка обрезает)
    journal_path: str = field(default_factory=lambda: _env("LASER_JOURNAL_PATH", "/journal.cgi?t=a&f=c&d={days}"))
    journal_encoding: str = field(default_factory=lambda: _env("LASER_JOURNAL_ENCODING", "cp1251"))
    #: гостевая учётная запись счётчика (по умолчанию заводская guest:guest)
    counter_user: str = field(default_factory=lambda: _env("LASER_COUNTER_USER", "guest"))
    counter_password: str = field(default_factory=lambda: _env("LASER_COUNTER_PASSWORD", "guest"))
    #: события журнала, по которым считается посещаемость (10 — EVENT_INNOW: вошло, присутствие, вышло)
    count_events: tuple[int, ...] = field(default_factory=lambda: _env_ints("LASER_JOURNAL_EVENTS", (10,)))
    #: номера полей строки журнала со счётчиками входов и выходов (поле 3 — присутствие, не выходы)
    entered_column: int = field(default_factory=lambda: int(_env_float("LASER_JOURNAL_IN_COLUMN", 2)))
    exited_column: int = field(default_factory=lambda: int(_env_float("LASER_JOURNAL_OUT_COLUMN", 4)))

    @property
    def enabled(self) -> bool:
        if self.mode == "guestance":
            return bool(self.counters or self.journal_dir)
        return self.mode == "fixture" or bool(self.base_url)


@dataclass
class Thresholds:
    """Пороги, при превышении которых расхождение считается значимым."""

    warn_pct: float = field(default_factory=lambda: _env_float("DIFF_WARN_PCT", 5.0))
    critical_pct: float = field(default_factory=lambda: _env_float("DIFF_CRITICAL_PCT", 15.0))
    min_abs: float = field(default_factory=lambda: _env_float("DIFF_MIN_ABS", 5.0))


@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(_env("DB_PATH", str(DATA_DIR / "attendance.db"))))
    timezone_offset_hours: int = field(default_factory=lambda: int(_env_float("TZ_OFFSET_HOURS", 0)))
    sync_interval_minutes: int = field(default_factory=lambda: int(_env_float("SYNC_INTERVAL_MINUTES", 60)))
    sync_lookback_days: int = field(default_factory=lambda: int(_env_float("SYNC_LOOKBACK_DAYS", 14)))
    autosync: bool = field(default_factory=lambda: _env("AUTOSYNC", "1") not in ("0", "false", "no"))
    rarus: RarusConfig = field(default_factory=RarusConfig)
    laser: LaserConfig = field(default_factory=LaserConfig)
    thresholds: Thresholds = field(default_factory=Thresholds)
    # Собранный Nuxt (`npm run generate`): если каталог есть — FastAPI раздаёт его сам.
    frontend_dist: Path = field(
        default_factory=lambda: Path(_env("FRONTEND_DIST", str(BASE_DIR / "frontend" / ".output" / "public")))
    )
    frontend_mount: str = field(default_factory=lambda: _env("FRONTEND_MOUNT", "/app"))
    # Нужны, только если фронт живёт на отдельном домене.
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(x.strip() for x in _env("CORS_ORIGINS").split(",") if x.strip())
    )


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
