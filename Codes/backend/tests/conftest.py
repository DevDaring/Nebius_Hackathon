"""Shared fixtures.

The API tests run against a separate PostgreSQL database (``nemotwins_test``) via a
DATABASE_URL override, always in offline demo mode (no live LLM / speech calls).
These variables must be set before any ``nemotwins`` module reads the settings.
"""

from __future__ import annotations

import os

TEST_DB = os.environ.get(
    "NEMOTWINS_TEST_DATABASE_URL",
    "postgresql+psycopg://nemotwins:nemotwins@localhost:5432/nemotwins_test",
)
os.environ["DATABASE_URL"] = TEST_DB
os.environ["APP_MODE"] = "demo"
# Test-only accounts (test database only): the jury account plus a second user for isolation tests.
os.environ["DEMO_USERS"] = "TestUser:TestUser11,Reviewer2:Reviewer22"
# Only the second test user gets the developer admin role (integration page).
os.environ["ADMIN_USERS"] = "Reviewer2"

import pytest  # noqa: E402

from nemotwins.config import PROCESSED_DIR  # noqa: E402

HAS_PROCESSED = (PROCESSED_DIR / "timeseries.parquet").exists() and (PROCESSED_DIR / "covariates.parquet").exists()


@pytest.fixture(scope="session")
def engine():
    from nemotwins.twin.engine import get_engine

    return get_engine()


def _reset_test_db() -> None:
    from sqlalchemy import create_engine, text

    assert TEST_DB.rsplit("/", 1)[-1].endswith("_test"), "refusing to reset a non-test database"
    eng = create_engine(TEST_DB, future=True)
    with eng.begin() as c:
        for t in ("audit_log", "twin_events", "fhir_resources", "replay_clocks", "covariate_revisions",
                  "pending_actions", "doctor_reviews"):
            c.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))
    eng.dispose()


@pytest.fixture(scope="session")
def client(engine):
    from fastapi.testclient import TestClient

    from nemotwins.api.main import app

    _reset_test_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def token(client) -> str:
    r = client.post("/api/auth/login", json={"username": "TestUser", "password": "TestUser11"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth(token) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def auth_b(client) -> dict:
    """A second user (Reviewer2): must never see TestUser's labs, FHIR resources or forecasts."""
    r = client.post("/api/auth/login", json={"username": "Reviewer2", "password": "Reviewer22"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
