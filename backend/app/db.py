from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator

from sqlalchemy import Engine, select, text
from sqlmodel import Session, SQLModel, create_engine

from app import config

IS_SQLITE = config.DB_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(config.DB_URL, connect_args={"check_same_thread": False})
else:
    # prepare_threshold=None: no server-side prepared statements, which a
    # transaction-pooling proxy (Neon's pooler) can't route reliably.
    engine = create_engine(config.DB_URL, pool_pre_ping=True, pool_size=3, max_overflow=2,
                           pool_recycle=300, connect_args={"prepare_threshold": None})

# Lets one thread (a demo reset) build into a scratch database while every
# other request keeps reading the live one.
_override: ContextVar[Engine | None] = ContextVar("engine_override", default=None)

KEEP = {"demolock", "adminaccount"}   # survive resets


def current_engine() -> Engine:
    return _override.get() or engine


def init_db() -> None:
    config.ensure_dirs()
    from app import models  # noqa: F401  (registers tables)
    try:
        SQLModel.metadata.create_all(current_engine())
    except Exception:
        # Two cold starts creating the same tables at once: the loser's error is harmless.
        if IS_SQLITE:
            raise


def reset_db() -> None:
    from app import models  # noqa: F401
    SQLModel.metadata.drop_all(current_engine())
    SQLModel.metadata.create_all(current_engine())


def serialize(s: Session, key: int = 7) -> None:
    """Postgres: one writer at a time for this key until the transaction ends.

    Audit appends must be ordered the way they commit, or two instances could
    each sign a root that misses the other's entry. SQLite already allows a
    single writer, so this is a no-op there.
    """
    if s.get_bind().dialect.name == "postgresql":
        s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


def rebuild(build: Callable[[], None]) -> None:
    """Run `build` against a scratch SQLite file, then swap its rows in atomically.

    Seeding makes thousands of small queries; against a remote Postgres each
    one waits a network round trip, so a direct seed takes minutes. Built
    locally it takes seconds, and the copy is a few batched inserts inside
    one transaction, so readers see the old world or the new one, never half.
    """
    from app import models  # noqa: F401
    config.ensure_dirs()
    path = config.DATA / f"build-{uuid.uuid4().hex}.db"
    scratch = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    token = _override.set(scratch)
    try:
        SQLModel.metadata.create_all(scratch)
        build()
    finally:
        _override.reset(token)
    tables = [t for t in SQLModel.metadata.sorted_tables if t.name not in KEEP]
    try:
        with scratch.connect() as src, engine.begin() as dst:
            if dst.dialect.name == "postgresql":
                dst.execute(text("TRUNCATE TABLE " + ", ".join(f'"{t.name}"' for t in tables)
                                 + " RESTART IDENTITY CASCADE"))
            else:
                for t in reversed(tables):
                    dst.execute(t.delete())
            for t in tables:
                rows = [dict(r) for r in src.execute(select(t)).mappings()]
                if rows:
                    dst.execute(t.insert(), rows)
            if dst.dialect.name == "postgresql":
                for t in tables:
                    if "id" in t.c and t.c.id.autoincrement in (True, "auto") and t.c.id.primary_key:
                        dst.execute(text(
                            f"SELECT setval(pg_get_serial_sequence('\"{t.name}\"', 'id'), "
                            f"COALESCE((SELECT MAX(id) FROM \"{t.name}\"), 0) + 1, false)"))
    finally:
        scratch.dispose()
        path.unlink(missing_ok=True)


@contextmanager
def session() -> Iterator[Session]:
    with Session(current_engine(), expire_on_commit=False) as s:
        yield s


def get_session() -> Iterator[Session]:
    with Session(current_engine(), expire_on_commit=False) as s:
        yield s
