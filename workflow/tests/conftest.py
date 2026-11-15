"""Database tests run against a real PostgreSQL, because some rules live there.

They drop and recreate every table, so they refuse to run unless the database
name ends in _test. Tests that don't ask for `db` (like test_rules.py) need no database.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5433/priorauth_test")
os.environ.setdefault("SEED_DEMO_DATA", "0")

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.clocks import clock
from app.db import Base, SessionLocal, create_schema, engine
from app.seed import load_members

if not (make_url(os.environ["DATABASE_URL"]).database or "").endswith("_test"):
    raise RuntimeError("Tests drop every table. Point DATABASE_URL at a database whose name ends in _test.")

START = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def schema():
    Base.metadata.drop_all(engine)
    create_schema()
    yield
    engine.dispose()


@pytest.fixture
def db(schema):
    table_names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
    with SessionLocal() as session:
        load_members(session)
    clock.set(START)
    yield
    clock.set(None)


@pytest.fixture
def session(db):
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client(db):
    from app.main import app

    return TestClient(app)
