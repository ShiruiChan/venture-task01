import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app import db
from app.config import settings


_ENV_PREFIXES = ("LASER_", "RARUS_", "SYNC_", "DIFF_")
_ENV_KEYS = ("DB_PATH", "AUTOSYNC")


@pytest.fixture(autouse=True, scope="session")
def isolate_env():
    """Прячет от тестов настройки из .env.

    Конфиги источников читают окружение в умолчаниях полей, поэтому локальный
    .env подменял бы значения, заданные в тесте явно, — вплоть до похода в
    реальную сеть к счётчикам.
    """
    saved = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(_ENV_PREFIXES) or key in _ENV_KEYS
    }
    for key in saved:
        del os.environ[key]
    yield
    os.environ.update(saved)


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "db_path", path)
    db.init_db(path)
    return path
