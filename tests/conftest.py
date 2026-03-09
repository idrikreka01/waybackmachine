import os

os.environ["DATABASE_PATH"] = ":memory:"  # tests never use scraper DB (wayback.sqlite)

import pytest
from waybackmachine.db.session import get_session_factory, init_db


@pytest.fixture
def db_url():
    return os.environ.get("DATABASE_PATH", ":memory:")


@pytest.fixture
def session():
    init_db()
    factory = get_session_factory()
    sess = factory()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()
