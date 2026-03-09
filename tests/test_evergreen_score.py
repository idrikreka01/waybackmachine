from datetime import datetime, timedelta

from waybackmachine.db.models import Category, Post, Subcategory, Thread
from waybackmachine.scoring.context_builder import build_thread_context
from waybackmachine.scoring.evergreen_score import compute_evergreen_score


def _ctx(**overrides):
    base = {
        "thread_id": 1,
        "title": "Test thread",
        "link": "https://example.com/t",
        "category_path": "Technical > Electrical",
        "subcategory_name": "Electrical",
        "is_sticky": False,
        "replies_no": 0,
        "pagination_no": None,
        "created_at": None,
        "last_post_at": None,
        "activity_span_years": 0,
        "revival_count": 0,
        "first_post_text": None,
    }
    base.update(overrides)
    return base


def test_sticky_adds_25():
    out = compute_evergreen_score(
        _ctx(
            is_sticky=True,
            replies_no=5,
            pagination_no=0,
            category_path="Other",
            subcategory_name="General",
        )
    )
    assert out["breakdown"]["authority"]["sticky_points"] == 25
    assert out["score"]["raw"] >= 25


def test_replies_thresholds():
    assert (
        compute_evergreen_score(_ctx(replies_no=249))["breakdown"]["authority"]["reply_points"]
        == 30
    )
    assert (
        compute_evergreen_score(_ctx(replies_no=250))["breakdown"]["authority"]["reply_points"]
        == 40
    )
    assert (
        compute_evergreen_score(_ctx(replies_no=99))["breakdown"]["authority"]["reply_points"] == 20
    )
    assert (
        compute_evergreen_score(_ctx(replies_no=100))["breakdown"]["authority"]["reply_points"]
        == 30
    )
    assert (
        compute_evergreen_score(_ctx(replies_no=49))["breakdown"]["authority"]["reply_points"] == 0
    )
    assert (
        compute_evergreen_score(_ctx(replies_no=50))["breakdown"]["authority"]["reply_points"] == 20
    )


def test_page_thresholds():
    assert (
        compute_evergreen_score(_ctx(pagination_no=2))["breakdown"]["authority"]["page_points"] == 0
    )
    assert (
        compute_evergreen_score(_ctx(pagination_no=3))["breakdown"]["authority"]["page_points"]
        == 10
    )
    assert (
        compute_evergreen_score(_ctx(pagination_no=5))["breakdown"]["authority"]["page_points"]
        == 10
    )
    assert (
        compute_evergreen_score(_ctx(pagination_no=6))["breakdown"]["authority"]["page_points"]
        == 20
    )


def test_activity_and_revival_both_apply():
    out = compute_evergreen_score(
        _ctx(
            activity_span_years=3,
            revival_count=4,
            replies_no=100,
        )
    )
    assert out["breakdown"]["authority"]["activity_span_points"] == 15
    assert out["breakdown"]["authority"]["revival_points"] == 10


def test_problem_keywords_title_and_first_post():
    out = compute_evergreen_score(
        _ctx(
            title="How to fix wiring",
            first_post_text="Guide for troubleshooting.",
        )
    )
    assert out["breakdown"]["problem_intent"]["points"] == 20
    assert (
        "wiring" in out["breakdown"]["problem_intent"]["matched_keywords"]
        or "how to" in out["breakdown"]["problem_intent"]["matched_keywords"]
    )
    assert "title" in out["breakdown"]["problem_intent"]["match_sources"]
    assert "first_post" in out["breakdown"]["problem_intent"]["match_sources"]


def test_category_mapping_partial():
    out = compute_evergreen_score(_ctx(category_path="Technical Sections > Engine Performance"))
    assert out["breakdown"]["category_bonus"]["points"] == 15
    assert "Engine Performance" in (out["breakdown"]["category_bonus"]["matched_category"] or "")
    out2 = compute_evergreen_score(_ctx(category_path="Stuff > Electrical Systems"))
    assert out2["breakdown"]["category_bonus"]["points"] == 15


def test_noise_for_sale_penalty():
    out = compute_evergreen_score(
        _ctx(
            category_path="For Sale",
            subcategory_name="Classified",
        )
    )
    assert out["breakdown"]["noise"]["points"] <= -40
    assert "for_sale_classified" in out["breakdown"]["noise"]["flags"]


def test_noise_offtopic_penalty():
    out = compute_evergreen_score(
        _ctx(
            category_path="Meme",
            subcategory_name="Lounge",
        )
    )
    assert out["breakdown"]["noise"]["points"] <= -50
    assert "meme_lounge_offtopic" in out["breakdown"]["noise"]["flags"]


def test_noise_single_reply_penalty():
    out = compute_evergreen_score(_ctx(replies_no=1))
    assert out["breakdown"]["noise"]["points"] <= -30
    assert "single_reply" in out["breakdown"]["noise"]["flags"]


def test_noise_opinion_penalty_when_no_problem_match():
    out = compute_evergreen_score(
        _ctx(
            title="What do you think about this?",
            first_post_text="Just wondering.",
        )
    )
    assert "opinion_thread" in out["breakdown"]["noise"]["flags"]
    assert out["breakdown"]["noise"]["points"] <= -25


def test_noise_opinion_no_penalty_when_problem_matches():
    out = compute_evergreen_score(
        _ctx(
            title="What do you think about this wiring fix?",
            first_post_text="How to fix the wiring.",
        )
    )
    assert out["breakdown"]["problem_intent"]["points"] == 20
    assert "opinion_thread" not in out["breakdown"]["noise"]["flags"]


def test_clamp_negative_to_zero():
    out = compute_evergreen_score(
        _ctx(
            category_path="For Sale",
            subcategory_name="Meme",
            replies_no=0,
            title="What do you think?",
        )
    )
    assert out["score"]["final"] == 0
    assert out["score"]["raw"] < 0


def test_clamp_over_100():
    out = compute_evergreen_score(
        _ctx(
            is_sticky=True,
            replies_no=500,
            pagination_no=10,
            activity_span_years=5,
            revival_count=5,
            title="How to fix wiring guide",
            category_path="Electrical",
            first_post_text="1999 and 2006 wiring schematic 5.3 6.0",
        )
    )
    assert out["score"]["final"] == 100
    assert out["score"]["raw"] >= 100


def test_decision_thresholds():
    high = compute_evergreen_score(
        _ctx(
            is_sticky=True,
            replies_no=100,
            pagination_no=4,
            activity_span_years=2,
            revival_count=3,
            title="How to fix wiring",
            category_path="Electrical",
        )
    )
    assert high["score"]["decision"] == "PROMOTE"
    assert high["score"]["final"] >= 65

    mid = compute_evergreen_score(
        _ctx(
            replies_no=50,
            pagination_no=3,
            title="Wiring guide",
            category_path="Appearance",
            subcategory_name="Show & Shine",
        )
    )
    assert mid["score"]["decision"] == "HOLD"
    assert 45 <= mid["score"]["final"] < 65

    low = compute_evergreen_score(
        _ctx(
            replies_no=5,
            title="Random",
            category_path="Appearance",
        )
    )
    assert low["score"]["decision"] == "ARCHIVE"
    assert low["score"]["final"] < 45


def test_output_format_json_serializable():
    out = compute_evergreen_score(
        _ctx(
            thread_id=123,
            title="Test",
            link="https://x.com",
            created_at=datetime(2020, 1, 1, 12, 0, 0),
            last_post_at=datetime(2023, 2, 1, 10, 0, 0),
        )
    )
    assert out["scoring_version"] == "v1"
    assert out["thread"]["thread_id"] == 123
    assert "T" in (out["thread"]["created_at"] or "")
    assert "T" in (out["thread"]["last_post_at"] or "")
    assert "score" in out and "breakdown" in out
    import json

    json.dumps(out)


def test_build_thread_context_returns_none_for_missing_thread(session):
    assert build_thread_context(session, 99999) is None


def test_build_thread_context_joins_and_derives(session):
    cat = Category(name="Tech", link="https://example.com/cat")
    session.add(cat)
    session.flush()
    sub = Subcategory(
        category_id=cat.id,
        name="Electrical",
        link="https://example.com/sub",
        threads_no=1,
        posts_no=2,
    )
    session.add(sub)
    session.flush()
    thread = Thread(
        title="Wire fix",
        link="https://example.com/t",
        subcategory_id=sub.id,
        replies_no=10,
        is_sticky=False,
        pagination_no=2,
    )
    session.add(thread)
    session.flush()
    base = datetime(2020, 1, 1)
    for i in range(3):
        p = Post(
            thread_id=thread.id,
            post_date_time=base + timedelta(days=i * 400),
            post_content="First post content" if i == 0 else "Later",
        )
        session.add(p)
    session.flush()
    ctx = build_thread_context(session, thread.id)
    assert ctx is not None
    assert ctx["thread_id"] == thread.id
    assert ctx["title"] == "Wire fix"
    assert ctx["category_path"] == "Tech > Electrical"
    assert ctx["subcategory_name"] == "Electrical"
    assert ctx["replies_no"] == 10
    assert ctx["created_at"] is not None
    assert ctx["last_post_at"] is not None
    assert ctx["activity_span_years"] >= 2
    assert ctx["revival_count"] >= 1
    assert ctx["first_post_text"] == "First post content"
