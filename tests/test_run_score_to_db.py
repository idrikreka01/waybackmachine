import json
from datetime import datetime, timedelta

from waybackmachine.db.models import Category, Post, Subcategory, Thread, ThreadEvergreenScore
from waybackmachine.db.session import get_session_factory
from waybackmachine.scoring.run_score_to_db import run_score_to_db


def _make_promote_thread(session):
    cat = Category(name="General Discussion", link="https://example.com/cat")
    session.add(cat)
    session.flush()
    sub = Subcategory(
        category_id=cat.id,
        name="Electrical",
        link="https://example.com/sub",
        threads_no=1,
        posts_no=10,
    )
    session.add(sub)
    session.flush()
    thread = Thread(
        title="How to fix wiring",
        link="https://example.com/t1",
        subcategory_id=sub.id,
        replies_no=100,
        is_sticky=True,
        pagination_no=4,
        posts_fetched=True,
    )
    session.add(thread)
    session.flush()
    base = datetime(2020, 1, 1)
    for i in range(3):
        session.add(
            Post(
                thread_id=thread.id,
                post_date_time=base + timedelta(days=i * 100),
                post_content="wiring guide" if i == 0 else "reply",
            )
        )
    session.flush()
    return thread.id


def _make_archive_thread(session):
    cat = Category(name="General", link="https://example.com/c2")
    session.add(cat)
    session.flush()
    sub = Subcategory(
        category_id=cat.id,
        name="Appearance",
        link="https://example.com/sub2",
        threads_no=1,
        posts_no=2,
    )
    session.add(sub)
    session.flush()
    thread = Thread(
        title="Random chat",
        link="https://example.com/t2",
        subcategory_id=sub.id,
        replies_no=2,
        is_sticky=False,
        posts_fetched=True,
    )
    session.add(thread)
    session.flush()
    session.add(
        Post(thread_id=thread.id, post_date_time=datetime(2021, 1, 1), post_content="hi")
    )
    session.flush()
    return thread.id


def test_decision_filter_only_promote_saved(session):
    _make_promote_thread(session)
    _make_archive_thread(session)
    session.commit()
    session.close()

    stats = run_score_to_db(
        posts_fetched_only=True,
        save_decisions=frozenset(["PROMOTE"]),
    )
    assert stats["processed"] == 2
    assert stats["saved"] == 1
    assert stats["excluded"] == 1
    assert stats["saved_by_decision"] == {"PROMOTE": 1}

    factory = get_session_factory()
    s = factory()
    rows = s.query(ThreadEvergreenScore).all()
    s.close()
    assert len(rows) == 1
    assert rows[0].decision == "PROMOTE"


def test_decision_filter_promote_and_hold_saved(session):
    _make_promote_thread(session)
    _make_archive_thread(session)
    session.commit()
    session.close()

    stats = run_score_to_db(
        posts_fetched_only=True,
        save_decisions=frozenset(["PROMOTE", "HOLD"]),
    )
    assert stats["saved"] >= 1
    factory = get_session_factory()
    s = factory()
    rows = s.query(ThreadEvergreenScore).all()
    s.close()
    for row in rows:
        assert row.decision in ("PROMOTE", "HOLD")


def test_upsert_second_run_updates_row(session):
    tid = _make_promote_thread(session)
    session.commit()
    session.close()

    run_score_to_db(posts_fetched_only=True, save_decisions=frozenset(["PROMOTE"]))
    factory = get_session_factory()
    s = factory()
    row1 = s.query(ThreadEvergreenScore).filter(ThreadEvergreenScore.thread_id == tid).first()
    s.close()
    assert row1 is not None
    updated_at1 = row1.updated_at

    run_score_to_db(posts_fetched_only=True, save_decisions=frozenset(["PROMOTE"]))
    s = factory()
    rows = s.query(ThreadEvergreenScore).filter(ThreadEvergreenScore.thread_id == tid).all()
    s.close()
    assert len(rows) == 1
    assert rows[0].updated_at >= updated_at1


def test_result_json_stored_valid(session):
    _make_promote_thread(session)
    session.commit()
    session.close()

    run_score_to_db(posts_fetched_only=True, save_decisions=frozenset(["PROMOTE"]))
    factory = get_session_factory()
    s = factory()
    row = s.query(ThreadEvergreenScore).first()
    s.close()
    assert row is not None
    data = json.loads(row.result_json)
    assert "thread" in data
    assert "score" in data
    assert "breakdown" in data
    assert data["score"]["decision"] == row.decision
    assert data["score"]["final"] == row.final_score


def test_min_score_filter(session):
    _make_promote_thread(session)
    _make_archive_thread(session)
    session.commit()
    session.close()

    stats = run_score_to_db(
        posts_fetched_only=True,
        save_decisions=frozenset(["PROMOTE", "HOLD", "ARCHIVE"]),
        min_score=65,
    )
    factory = get_session_factory()
    s = factory()
    rows = s.query(ThreadEvergreenScore).all()
    s.close()
    for row in rows:
        assert row.final_score >= 65
