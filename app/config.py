"""Settings for the system. Values come from the .env file (created by setup.ps1)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

try:  # python-dotenv is optional; environment variables work without it
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass


def db_engine():
    """'postgres' (default, as in the proposal) or 'sqlite' (used only by automatic tests)."""
    return os.environ.get("DB_ENGINE", "postgres").strip().lower()


def sqlite_path():
    return os.environ.get("SQLITE_PATH", str(BASE_DIR / "data" / "policing_ai.sqlite3"))


def pg_settings():
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "user": os.environ.get("PGUSER", "postgres"),
        "password": os.environ.get("PGPASSWORD", ""),
        "dbname": os.environ.get("PGDATABASE", "policing_ai"),
    }


def secret_key():
    return os.environ.get("SECRET_KEY", "change-this-secret-in-the-env-file")


def model_path():
    return os.environ.get("MODEL_PATH", str(BASE_DIR / "models" / "link_model.joblib"))


TOKEN_HOURS = 8
