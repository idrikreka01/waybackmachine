import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from waybackmachine.config import get_database_url
from waybackmachine.db.models import Base

_engine = None
_session_factory = None


def reset_db_for_scraper() -> None:
    global _engine, _session_factory
    _session_factory = None
    if _engine is not None:
        _engine.dispose()
        _engine = None
    url = get_database_url()
    if url.startswith("sqlite:///") and "memory" not in url:
        path = url.replace("sqlite:///", "", 1)
        if path and os.path.isfile(path):
            os.remove(path)


def get_engine():
    global _engine
    if _engine is None:
        url = get_database_url()
        opts = {"echo": False}
        if url.startswith("sqlite"):
            opts["connect_args"] = {"check_same_thread": False}
        else:
            opts["pool_pre_ping"] = True
        _engine = create_engine(url, **opts)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


def get_session() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())
