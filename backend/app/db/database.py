from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False)
_ENGINE: Engine | None = None


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(settings.database_url, pool_pre_ping=True, future=True)
        SessionLocal.configure(bind=_ENGINE)
    return _ENGINE


def get_db() -> Generator[Session, None, None]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
