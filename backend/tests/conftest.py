import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./enterprise_ai_test.db")
os.environ.setdefault("USE_SQLITE_FALLBACK", "1")

import app.models  # noqa: F401  # register SQLAlchemy models
from app.db.base import Base
from app.db.session import engine

Base.metadata.create_all(bind=engine)
