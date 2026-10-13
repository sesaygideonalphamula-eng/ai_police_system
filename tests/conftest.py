"""Every test runs against a fresh, temporary SQLite database - never PostgreSQL - so the
tests are fast, repeatable, and never touch real project data."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_ENGINE", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "model.joblib"))
    yield


@pytest.fixture
def db_with_schema():
    from app import db as dbmod, schema
    with dbmod.connect() as db:
        schema.create_schema(db)
        yield db
