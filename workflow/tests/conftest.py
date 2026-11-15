"""Database tests run against a real PostgreSQL, because some rules live there.

They drop and recreate every table, so they refuse to run unless the database
name ends in _test. Tests that don't ask for `db` (like test_rules.py) need no database.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5433/priorauth_test")
os.environ.setdefault("SEED_DEMO_DATA", "0")
os.environ.setdefault("SESSION_SECRET", "test-secret-test-secret-test-secret-0001")
os.environ.setdefault("CONNECTOR_TOKEN", "connector-token-for-tests-only-0001")
os.environ.setdefault("EXTRACTOR_TOKEN", "extractor-token-for-tests-only-0001")

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.clocks import clock
from app.db import Base, SessionLocal, create_schema, engine
from app.seed import load_members, load_users

if not (make_url(os.environ["DATABASE_URL"]).database or "").endswith("_test"):
    raise RuntimeError("Tests drop every table. Point DATABASE_URL at a database whose name ends in _test.")

START = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
PASSWORD = "test-password-123"


@pytest.fixture(scope="session")
def schema():
    Base.metadata.drop_all(engine)
    create_schema()
    # Password hashing is deliberately slow, so the demo users are created once per run.
    with SessionLocal() as session:
        load_users(session, PASSWORD)
    yield
    engine.dispose()


@pytest.fixture
def db(schema):
    table_names = ", ".join(t.name for t in Base.metadata.sorted_tables if t.name != "users")
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        # Undo whatever the last test did to the demo users.
        connection.execute(text("DELETE FROM users WHERE username NOT IN ('ivy', 'nina', 'omar', 'dr.lee', 'admin')"))
        connection.execute(text("UPDATE users SET active = true, failed_logins = 0, locked_until = NULL"))
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
    """Not signed in."""
    from app.main import app

    return TestClient(app)


@pytest.fixture
def connector(db):
    from app.main import app

    return TestClient(app, headers={"Authorization": f"Bearer {os.environ['CONNECTOR_TOKEN']}"})


@pytest.fixture
def as_user(db):
    """as_user("nina") -> a client signed in as that demo user."""
    from app.main import app

    def make(username: str) -> TestClient:
        c = TestClient(app, headers={"X-Requested-With": "workbench"})
        response = c.post("/api/auth/login", json={"username": username, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return c

    return make
