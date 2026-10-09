"""One-click demo sessions: every visitor gets a private throw-away user (no shared replay state)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from nemotwins.config import get_settings
from nemotwins.db import ReplayClock, User, session

PID = "biman"


@pytest.fixture(autouse=True)
def _fresh_limits():
    from nemotwins.api.main import RATE

    RATE.reset()
    yield
    RATE.reset()


def _demo(client, ip: str | None = None):
    """POST /api/auth/demo, optionally from a given client address (uvicorn sets it from the proxy's
    X-Forwarded-For in production; the test client needs it set directly)."""
    if ip is None:
        return client.post("/api/auth/demo")
    from fastapi.testclient import TestClient

    from nemotwins.api.main import app

    return TestClient(app, client=(ip, 50000)).post("/api/auth/demo")


def _h(r) -> dict:
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_each_click_is_a_new_private_user(client) -> None:
    a, b = _demo(client), _demo(client)
    assert a.status_code == 200 and b.status_code == 200
    ua, ub = a.json()["user"], b.json()["user"]
    assert ua["username"].startswith("demo-") and ua["username"] != ub["username"]
    assert ua["demo"] is True and "admin" not in ua["roles"]
    me = client.get("/api/auth/me", headers=_h(a)).json()
    assert me["username"] == ua["username"] and me["demo"] is True


def test_demo_visitors_do_not_share_the_replay_clock(client, auth) -> None:
    a, b = _demo(client), _demo(client)
    r = client.post(f"/api/twin/{PID}/advance", json={"ladder": "2", "minutes": 120}, headers=_h(a))
    assert r.status_code == 200 and r.json()["replay"]["offset_min"] == 120
    assert client.get(f"/api/twin/{PID}/state", headers=_h(b)).json()["replay"]["offset_min"] == 0
    assert client.get(f"/api/twin/{PID}/state", headers=auth).json()["replay"]["offset_min"] == 0  # jury account untouched


def test_demo_sessions_are_rate_limited_per_client_and_per_day(client, monkeypatch) -> None:
    monkeypatch.setenv("RATE_DEMO_SESSION_PER_HOUR", "2")
    monkeypatch.setenv("DEMO_SESSIONS_PER_DAY", "3")
    get_settings.cache_clear()
    try:
        assert _demo(client, "198.51.100.1").status_code == 200
        assert _demo(client, "198.51.100.1").status_code == 200
        r = _demo(client, "198.51.100.1")
        assert r.status_code == 429 and int(r.headers["Retry-After"]) > 60
        assert _demo(client, "198.51.100.2").status_code == 200  # another visitor
        assert _demo(client, "198.51.100.3").status_code == 429  # daily cap reached
    finally:
        get_settings.cache_clear()


def test_demo_sessions_can_be_switched_off(client, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_SESSIONS", "false")
    get_settings.cache_clear()
    try:
        assert _demo(client).status_code == 404
    finally:
        get_settings.cache_clear()


def test_expired_demo_users_and_their_data_are_purged(client) -> None:
    r = _demo(client)
    name = r.json()["user"]["username"]
    assert client.post(f"/api/twin/{PID}/advance", json={"ladder": "2", "minutes": 60}, headers=_h(r)).status_code == 200
    with session() as s:
        uid = s.scalar(select(User.id).where(User.username == name))
        assert s.scalar(select(ReplayClock).where(ReplayClock.user_id == uid)) is not None
        s.execute(update(User).where(User.id == uid).values(created_at=datetime.now(UTC) - timedelta(hours=25)))
        s.commit()
    assert _demo(client).status_code == 200  # creating a session purges expired ones
    with session() as s:
        assert s.scalar(select(User).where(User.username == name)) is None
        assert s.scalar(select(ReplayClock).where(ReplayClock.user_id == uid)) is None
        assert s.scalar(select(User).where(User.username == "TestUser")) is not None  # seeded accounts stay
    assert client.get("/api/auth/me", headers=_h(r)).status_code == 401
