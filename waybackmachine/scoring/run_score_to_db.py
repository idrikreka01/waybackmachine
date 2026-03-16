import json
import os
import sys

from sqlalchemy.orm import joinedload

from waybackmachine.ai.rewrite_thread import _thread_to_payload  # type: ignore[attr-defined]
from waybackmachine.config import EVERGREEN_MIN_SCORE, EVERGREEN_SAVE_DECISION_SET
from waybackmachine.db.models import Thread, ThreadEvergreenScore
from waybackmachine.db.session import get_session_factory
from waybackmachine.logging_config import configure_logging
from waybackmachine.routing import route_thread
from waybackmachine.scoring.context_builder import build_thread_context
from waybackmachine.scoring.evergreen_score import compute_evergreen_score


def _build_tags(result: dict, routing: dict | None) -> list[str]:
    tags: list[str] = []
    breakdown = result.get("breakdown") or {}
    problem = breakdown.get("problem_intent") or {}
    matched_keywords = problem.get("matched_keywords") or []
    routing = routing or {}

    era_id = routing.get("era_id") or ""
    era_map = {
        "SQUAREBODY_73_87": "squarebody",
        "GMT400_OBS": "gmt400",
        "GMT800_NBS": "gmt800",
        "GMT900_NNBS": "gmt900",
        "K2XX": "k2xx",
        "T1XX_EV": "t1xx",
    }
    gen_tag = era_map.get(era_id)
    if gen_tag:
        tags.append(gen_tag)

    tech_type = routing.get("tech_type") or ""
    system_map = {
        "INTERIOR": ["interior"],
        "SUSPENSION": ["suspension"],
        "STEREO_ELECTRICAL": ["electrical", "audio", "lighting"],
        "TRANSMISSION": ["transmission"],
    }
    for t in system_map.get(tech_type, []):
        if t not in tags:
            tags.append(t)

    kw_lower = [str(k).lower() for k in matched_keywords]
    intent_tags: list[str] = []
    if any("how to" in k or "guide" in k for k in kw_lower):
        intent_tags.append("how-to")
        intent_tags.append("guide")
    if any("troubleshooting" in k or "symptoms" in k for k in kw_lower):
        intent_tags.append("troubleshooting")
    if any("upgrade" in k or "swap" in k or "install" in k or "retrofit" in k for k in kw_lower):
        intent_tags.append("upgrade")

    for t in intent_tags:
        if t not in tags:
            tags.append(t)

    return tags


def _eligible_thread_ids(session, posts_fetched_only: bool = True):
    q = session.query(Thread.id)
    if posts_fetched_only:
        q = q.filter(Thread.posts_fetched)
    return [r[0] for r in q.all()]


def _should_save(
    result: dict,
    save_decisions: frozenset[str] | None = None,
    min_score: int | None = None,
) -> bool:
    decision = result["score"]["decision"]
    final_score = result["score"]["final"]
    decisions = save_decisions if save_decisions is not None else EVERGREEN_SAVE_DECISION_SET
    min_s = min_score if min_score is not None else EVERGREEN_MIN_SCORE
    if decision not in decisions:
        return False
    if min_s is not None and final_score < min_s:
        return False
    return True


def _upsert_score(session, thread_id: int, result: dict, routing: dict | None) -> None:
    score = result["score"]
    tags = _build_tags(result, routing)
    result_with_tags = dict(result)
    if tags:
        result_with_tags["tags"] = tags
    row = (
        session.query(ThreadEvergreenScore)
        .filter(ThreadEvergreenScore.thread_id == thread_id)
        .first()
    )
    payload = {
        "scoring_version": result_with_tags["scoring_version"],
        "final_score": score["final"],
        "raw_score": score["raw"],
        "decision": score["decision"],
        "result_json": json.dumps(result_with_tags),
    }
    if routing is not None:
        payload.update(
            {
                "era_id": routing.get("era_id"),
                "era_score": routing.get("era_score"),
                "tech_type": routing.get("tech_type"),
                "tech_score": routing.get("tech_score"),
                "forum_main": routing.get("forum_main"),
                "forum_sub": routing.get("forum_sub"),
            }
        )
    if row:
        for k, v in payload.items():
            setattr(row, k, v)
    else:
        session.add(
            ThreadEvergreenScore(
                thread_id=thread_id,
                **payload,
            )
        )


def run_score_to_db(
    posts_fetched_only: bool = True,
    save_decisions: frozenset[str] | None = None,
    min_score: int | None = None,
) -> dict:
    factory = get_session_factory()
    session = factory()
    try:
        thread_ids = _eligible_thread_ids(session, posts_fetched_only=posts_fetched_only)
    finally:
        session.close()

    eligible = len(thread_ids)
    processed = 0
    saved = 0
    saved_by_decision = {}
    skipped = 0
    excluded = 0

    session = factory()
    try:
        for thread_id in thread_ids:
            ctx = build_thread_context(session, thread_id)
            if ctx is None:
                skipped += 1
                continue
            result = compute_evergreen_score(ctx)
            processed += 1
            if not _should_save(result, save_decisions=save_decisions, min_score=min_score):
                excluded += 1
                continue

            thread = (
                session.query(Thread)
                .options(joinedload(Thread.posts), joinedload(Thread.subcategory))
                .filter(Thread.id == thread_id)
                .first()
            )
            if thread is None:
                skipped += 1
                continue

            thread_payload = _thread_to_payload(thread)
            routing = route_thread(thread_payload)

            _upsert_score(session, thread_id, result, routing)
            saved += 1
            dec = result["score"]["decision"]
            saved_by_decision[dec] = saved_by_decision.get(dec, 0) + 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return {
        "eligible": eligible,
        "processed": processed,
        "saved": saved,
        "saved_by_decision": saved_by_decision,
        "skipped": skipped,
        "excluded": excluded,
    }


def main() -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    posts_fetched_only = os.environ.get("EVERGREEN_ALL_THREADS", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    )
    stats = run_score_to_db(posts_fetched_only=posts_fetched_only)
    print(f"Threads eligible:     {stats['eligible']}")
    print(f"Threads processed:   {stats['processed']}")
    print(f"Threads saved:       {stats['saved']}")
    if stats["saved_by_decision"]:
        for dec, count in sorted(stats["saved_by_decision"].items()):
            print(f"  by {dec}: {count}")
    print(f"Threads skipped:     {stats['skipped']}")
    print(f"Threads excluded:    {stats['excluded']}")


if __name__ == "__main__":
    main()
    sys.exit(0)
