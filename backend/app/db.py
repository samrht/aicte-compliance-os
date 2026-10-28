from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
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


def init_db() -> None:
    config.ensure_dirs()
    from app import models  # noqa: F401  (registers tables)
    try:
        SQLModel.metadata.create_all(engine)
    except Exception:
        # Two cold starts creating the same tables at once: the loser's error is harmless.
        if IS_SQLITE:
            raise


def clear_db() -> None:
    """Empty every table except the reset lock, restarting ids. Tables stay in place."""
    from app import models  # noqa: F401
    names = [t.name for t in SQLModel.metadata.sorted_tables if t.name != "demolock"]
    with engine.begin() as conn:
        if IS_SQLITE:
            for name in reversed(names):
                conn.execute(text(f'DELETE FROM "{name}"'))
        else:
            conn.execute(text("TRUNCATE TABLE " + ", ".join(f'"{n}"' for n in names)
                              + " RESTART IDENTITY CASCADE"))


def serialize(s: Session, key: int = 7) -> None:
    """Postgres: one writer at a time for this key until the transaction ends.

    Audit appends must be ordered the way they commit, or two instances could
    each sign a root that misses the other's entry. SQLite already allows a
    single writer, so this is a no-op there.
    """
    if not IS_SQLITE:
        s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


def reset_db() -> None:
    from app import models  # noqa: F401
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


@contextmanager
def session() -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as s:
        yield s


def get_session() -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as s:
        yield s
