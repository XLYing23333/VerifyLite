"""Application configuration loaded from environment variables."""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_PORT = 22222
MAX_BLOB_SIZE_CAP = 1_000_000_000
MAX_BLOB_SIZE = MAX_BLOB_SIZE_CAP
GUNICORN_TIMEOUT = 600


def _data_dir():
    """Resolve the directory used for SQLite and uploaded blobs.

    Returns:
        Path: Absolute data directory path.
    """
    raw = os.environ.get("DATA_DIR", "").strip()
    path = Path(raw) if raw else BASE_DIR / "data"
    return path.resolve()


class Config:
    """Default runtime configuration for VerifyLite."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
    PORT = int(os.environ.get("PORT", DEFAULT_PORT))
    DATA_DIR = str(_data_dir())
    MAX_BLOB_SIZE = min(
        max(int(os.environ.get("MAX_BLOB_SIZE", MAX_BLOB_SIZE)), 1),
        MAX_BLOB_SIZE_CAP,
    )
    MAX_CONTENT_LENGTH = MAX_BLOB_SIZE + 1024 * 1024
    GUNICORN_TIMEOUT = int(os.environ.get("GUNICORN_TIMEOUT", GUNICORN_TIMEOUT))
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(
        Path(DATA_DIR) / "verifylite.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
    }
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    WTF_CSRF_TIME_LIMIT = None
    MAX_BATCH_KEYS = 500
