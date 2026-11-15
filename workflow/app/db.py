"""Database connection. PostgreSQL only: the audit log and duplicate protection rely on it."""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Matches the throwaway server in the README. Override with DATABASE_URL.
DEFAULT_URL = "postgresql+psycopg://postgres@127.0.0.1:5433/priorauth"

# Any fixed number works; it only has to be the same in every copy of the service.
SCHEMA_LOCK = 72002


class Base(DeclarativeBase):
    pass


# connect_timeout: fail in seconds when the database is unreachable, so the
# readiness check answers before an orchestrator gives up on it.
engine = create_engine(
    os.environ.get("DATABASE_URL", DEFAULT_URL),
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def create_schema() -> None:
    """Create missing tables. Several copies may start at once, so they take turns."""
    from app import models  # noqa: F401  (registers the tables)

    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SCHEMA_LOCK})
        Base.metadata.create_all(connection)
