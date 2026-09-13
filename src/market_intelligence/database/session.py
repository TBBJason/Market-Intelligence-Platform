"""SQLAlchemy engine and request-scoped session management."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from market_intelligence.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create one pooled, pre-ping-enabled engine per process."""

    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Build a session factory; accepting an engine keeps tests explicit."""

    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Yield a transaction-capable session for FastAPI dependencies."""

    session = make_session_factory()()
    try:
        yield session
    finally:
        session.close()
