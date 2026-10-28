from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app import config

engine = create_engine(config.DB_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
    config.ensure_dirs()
    from app import models  # noqa: F401  (registers tables)
    SQLModel.metadata.create_all(engine)


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
