import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _resolve_database_url() -> str:
    url = settings.database_url
    if url.startswith("sqlite"):
        return url
    if os.getenv("USE_SQLITE_FALLBACK", "1") == "1":
        return "sqlite:///./enterprise_ai_local.db"
    return url


engine = create_engine(_resolve_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
