import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy.orm import joinedload

from waybackmachine.ai.rewrite_thread import (  # type: ignore[attr-defined]
    _build_prompt,
    _call_ollama,
    _thread_to_payload,
    _validate_rewrite,
    rewrite_post,
)
from waybackmachine.db.models import Thread, ThreadEvergreenScore
from waybackmachine.db.session import get_session_factory
from waybackmachine.logging_config import configure_logging
from waybackmachine.routing import route_thread

LOG = logging.getLogger(__name__)

_EXPECTED_REWRITE_KEYS = {
    "rewritten_title",
    "summary",
    "seo_outline",
    "rewritten_article_markdown",
    "evidence",
    "notes",
}


def _assert_rewrite_shape(rewrite: Any) -> dict[str, Any]:
    if not isinstance(rewrite, dict):
        raise ValueError("rewrite must be a dict.")
    keys = set(rewrite.keys())
    if keys != _EXPECTED_REWRITE_KEYS:
        unexpected = sorted(keys - _EXPECTED_REWRITE_KEYS)
        missing = sorted(_EXPECTED_REWRITE_KEYS - keys)
        raise ValueError(
            f"rewrite has invalid keys. unexpected={unexpected} missing={missing} keys={sorted(keys)}"
        )
    return rewrite


def _rewrite_with_fallback(thread_payload: dict[str, Any], model: str) -> dict[str, Any]:
    prompt = _build_prompt(thread_payload)
    first_rewrite = _call_ollama(prompt, model=model)
    rewrite = first_rewrite
    try:
        _validate_rewrite(thread_payload, first_rewrite)
        return first_rewrite
    except ValueError as first_err:
        LOG.warning("First rewrite failed validation: %s", first_err)
        correction_prompt = (
            prompt
            + "\n\nYour last output failed validation. Return one JSON OBJECT only (not an array). "
            "Do not return an array of per-post rewrites. Keep the exact same JSON schema and keys. "
            "Fix evidence so that evidence.article_excerpt values are copied from rewritten_article_markdown "
            "exactly (exact substring) and are NOT copied from source posts. Add missing evidence entries "
            "for meaningful technical bullet lines and paragraphs. Remove any banned filler phrases "
            "('generally', 'typically', 'usually', 'recommended', 'might require', "
            "'with a few modifications', 'research indicates') unless directly supported by THREAD_DATA.posts. "
            "If a point comes from one side of a disagreement, attribute it explicitly in the article "
            "instead of presenting it as a settled fact. Do not insert post ids into the article text."
        )
        try:
            second_rewrite = _call_ollama(correction_prompt, model=model)
            _validate_rewrite(thread_payload, second_rewrite)
            rewrite = second_rewrite
        except ValueError as second_err:
            msg = str(second_err).lower()
            if "did not return json" in msg or "invalid json" in msg or "non-json" in msg:
                LOG.warning(
                    "Retry produced non-JSON or invalid JSON (%s); falling back to first-pass JSON "
                    "despite validation error: %s",
                    second_err,
                    first_err,
                )
                rewrite = first_rewrite
            else:
                LOG.warning(
                    "Retry rewrite also failed validation (%s); falling back to first-pass JSON "
                    "despite validation error: %s",
                    second_err,
                    first_err,
                )
                rewrite = first_rewrite
    return rewrite


def main() -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))

    parser = argparse.ArgumentParser(
        description="Generate JSON samples (thread + scoring + AI rewrite) for PROMOTE threads."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of PROMOTE threads to export (default: no limit).",
    )
    parser.add_argument(
        "--output-dir",
        default="samples",
        help="Directory where JSON samples will be written (default: samples).",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
        help="Ollama model name to use for rewrites.",
    )
    parser.add_argument(
        "--regenerate-existing",
        action="store_true",
        help=(
            "Regenerate AI output for threads that already have AI saved. "
            "Overwrites ai_article_json and ai_post_rewrites_json in DB."
        ),
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    factory = get_session_factory()
    session = factory()
    try:
        q = session.query(ThreadEvergreenScore).filter(
            ThreadEvergreenScore.decision == "PROMOTE"
        )
        if args.regenerate_existing:
            q = q.filter(ThreadEvergreenScore.ai_post_rewrites_json.isnot(None))
        else:
            q = q.filter(ThreadEvergreenScore.ai_article_json.is_(None))

        q = q.order_by(ThreadEvergreenScore.final_score.desc())
        if args.limit is not None:
            q = q.limit(args.limit)
        rows = q.all()
        if not rows:
            LOG.warning("No PROMOTE rows found in thread_evergreen_score; nothing to export.")
            return

        for row in rows:
            thread = (
                session.query(Thread)
                .options(
                    joinedload(Thread.subcategory),
                    joinedload(Thread.posts),
                )
                .filter(Thread.id == row.thread_id)
                .first()
            )
            if thread is None:
                LOG.warning("Thread id=%s not found; skipping.", row.thread_id)
                continue

            thread_payload = _thread_to_payload(thread)
            try:
                rewrite = _rewrite_with_fallback(thread_payload, model=args.model)
            except Exception as exc:  # pragma: no cover - defensive
                LOG.error("Rewrite failed for thread id=%s: %s", row.thread_id, exc)
                continue
            rewrite = _assert_rewrite_shape(rewrite)

            # Debug/internal helper rewrites (per-post). Not the publishable thread article.
            post_rewrites: list[dict[str, Any]] = []
            for post in thread_payload.get("posts", []):
                post_id = post.get("id")
                html = post.get("post_content_html") or ""
                try:
                    rewritten = rewrite_post(html, model=args.model)
                    post_rewrites.append({"post_id": post_id, "rewritten_content": rewritten})
                except Exception as exc:
                    LOG.warning("Per-post rewrite failed for post_id=%s: %s", post_id, exc)
                    post_rewrites.append({"post_id": post_id, "rewritten_content": ""})

            try:
                scoring_payload = json.loads(row.result_json)
            except Exception:
                scoring_payload = None

            routing = route_thread(thread_payload)

            # Persist AI output into DB for this thread.
            try:
                row.ai_article_json = json.dumps(
                    {
                        "rewritten_title": rewrite.get("rewritten_title"),
                        "summary": rewrite.get("summary"),
                        "seo_outline": rewrite.get("seo_outline"),
                        "rewritten_article_markdown": rewrite.get("rewritten_article_markdown"),
                        "evidence": rewrite.get("evidence"),
                        "notes": rewrite.get("notes"),
                    },
                    ensure_ascii=False,
                )
                row.ai_post_rewrites_json = json.dumps(post_rewrites, ensure_ascii=False)
            except Exception as exc:  # pragma: no cover - defensive
                LOG.warning(
                    "Failed to serialize AI output for thread_id=%s: %s", row.thread_id, exc
                )

            sample = {
                "thread": thread_payload,
                "scoring": {
                    "thread_id": row.thread_id,
                    "final_score": row.final_score,
                    "raw_score": row.raw_score,
                    "decision": row.decision,
                    "scoring_version": row.scoring_version,
                    "result": scoring_payload,
                },
                "rewrite": rewrite,
                "post_rewrites": post_rewrites,
                "routing": routing,
                "model": args.model,
            }
            _assert_rewrite_shape(sample.get("rewrite"))

            out_path = out_dir / f"thread_{row.thread_id}.json"
            out_path.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
            LOG.info("Wrote sample for thread_id=%s to %s", row.thread_id, out_path)
            session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    main()
