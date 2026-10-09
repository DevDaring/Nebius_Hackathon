"""PostgreSQL app state (users, user actions on the twin, agent audit trail, FHIR, lab revisions).

Time series for training/evaluation stay in Parquet (``data/processed``); everything a
user does in the app lives here, scoped to that user.

Schema changes are additive: ``init_db`` creates missing tables and adds missing columns
with ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``, so an existing database is migrated in
place without losing rows.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from nemotwins.config import get_settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(120))
    roles: Mapped[str] = mapped_column(String(120), default="patient,clinician")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TwinEvent(Base):
    """A reading or meal a user added to a persona's twin, at its own replay time.

    ``t_min``: replay time in minutes relative to the replay start (day 7, 19:30); ``observed_at``
    is the same instant on the displayed replay clock (timezone-aware, Asia/Kolkata);
    ``received_at`` is the server's wall-clock time when it arrived."""

    __tablename__ = "twin_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    persona_id: Mapped[str] = mapped_column(String(40), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # reading | meal
    payload: Mapped[dict] = mapped_column(JSON)
    t_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True,
                                                         server_default=func.now())
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # manual | chat | replay
    unit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReplayClock(Base):
    """Per user + persona replay clock (minutes past the replay start)."""

    __tablename__ = "replay_clocks"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    persona_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    offset_min: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class AuditLog(Base):
    """Every agent reply with the tool calls and outputs it used (spec section 7.6)."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    persona_id: Mapped[str] = mapped_column(String(40), index=True)
    lang: Mapped[str] = mapped_column(String(8))
    request_text: Mapped[str] = mapped_column(Text)
    reply_text: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(40))
    tool_calls: Mapped[list] = mapped_column(JSON)
    grounding: Mapped[dict] = mapped_column(JSON)
    safety: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FhirResource(Base):
    """A confirmed FHIR resource. Owned by the user who uploaded it (``user_id``); rows from before
    ownership existed have NULL and are returned to nobody."""

    __tablename__ = "fhir_resources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True,
                                                index=True)
    persona_id: Mapped[str] = mapped_column(String(40), index=True)
    resource_type: Mapped[str] = mapped_column(String(40))
    bundle_id: Mapped[str] = mapped_column(String(64), index=True)
    resource: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CovariateRevision(Base):
    """A confirmed, timestamped change to model-supported EHR covariates (HbA1c, BMI) from a lab upload."""

    __tablename__ = "covariate_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    persona_id: Mapped[str] = mapped_column(String(40), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    fields: Mapped[dict] = mapped_column(JSON)  # {code: {value, unit, original_value, original_unit, collection_date}}
    bundle_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PendingAction(Base):
    """A chat mutation (log a reading / meal) waiting for the user's confirmation."""

    __tablename__ = "pending_actions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    persona_id: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    summary_en: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String(8), default="en-US")
    ladder: Mapped[str] = mapped_column(String(8), default="2")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | done | cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DoctorReview(Base):
    """A clinician's review state for one persona (per signed-in user)."""

    __tablename__ = "doctor_reviews"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    persona_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))  # unreviewed | reviewed | follow_up
    note: Mapped[str] = mapped_column(Text, default="")
    by: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


_engine = None
_Session: sessionmaker | None = None


def engine():  # noqa: ANN201 - SQLAlchemy Engine
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
        _Session = sessionmaker(_engine, expire_on_commit=False)
    return _engine


@contextmanager
def session() -> Iterator[Session]:
    engine()
    assert _Session is not None
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# Columns added after the first release: (table, column, SQL type). Applied idempotently.
MIGRATIONS = [
    ("twin_events", "t_min", "DOUBLE PRECISION"),
    ("twin_events", "observed_at", "TIMESTAMP WITH TIME ZONE"),
    ("twin_events", "received_at", "TIMESTAMP WITH TIME ZONE DEFAULT now()"),
    ("twin_events", "source", "VARCHAR(20)"),
    ("twin_events", "unit", "VARCHAR(10)"),
    ("twin_events", "idempotency_key", "VARCHAR(80)"),
    ("fhir_resources", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
]
INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_twin_events_idem ON twin_events (user_id, persona_id, idempotency_key) "
    "WHERE idempotency_key IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_fhir_resources_user_id ON fhir_resources (user_id)",
]


def migrate() -> None:
    with engine().begin() as c:
        for table, col, typ in MIGRATIONS:
            c.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}"))
        for stmt in INDEXES:
            c.execute(text(stmt))


def ping() -> bool:
    try:
        with engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - readiness probe
        return False


def init_db() -> None:
    """Create tables, migrate old ones, and seed the demo login accounts (idempotent)."""
    from nemotwins.auth import hash_password

    Base.metadata.create_all(engine())
    migrate()
    with session() as s:
        admins = get_settings().admin_usernames
        for username, password in get_settings().demo_user_pairs():
            u = s.scalar(select(User).where(User.username == username))
            roles = "patient,clinician,admin" if username in admins else "patient,clinician"
            if u is None:
                s.add(User(username=username, password_hash=hash_password(password), display_name=username,
                           roles=roles))
            elif u.roles != roles and (username in admins or "admin" in (u.roles or "").split(",")):
                u.roles = roles  # ADMIN_USERS is the source of truth for the admin role
