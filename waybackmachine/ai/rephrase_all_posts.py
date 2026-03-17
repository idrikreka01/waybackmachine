import argparse
import json
import os
from typing import Any, Dict, List

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


def main() -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))

    parser = argparse.ArgumentParser(
        description=(
            "Rephrase posts for all scored threads that don't yet have "
            "ai_post_rewrites_json."
        )
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
        help="Ollama model name to use for rewrites.",
    )
    args = parser.parse_args()

    factory = get_session_factory()
    session = factory()
    try:
        rows: List[ThreadEvergreenScore] = (
            session.query(ThreadEvergreenScore)
            .options(
                joinedload(ThreadEvergreenScore.thread).joinedload(Thread.posts),
            )
            .filter(ThreadEvergreenScore.ai_post_rewrites_json.is_(None))
            .all()
        )
        print(f"Found {len(rows)} threads without post rewrites.")
        for score_row in rows:
            thread: Thread | None = score_row.thread
            if thread is None:
                continue
            print(f"Rephrasing posts for thread_id={thread.id} title={thread.title!r}")
            post_rewrites: List[Dict[str, Any]] = []
            for post in sorted(
                thread.posts,
                key=lambda p: ((p.post_page_id or 0), p.id),
            ):
                html = post.post_content or ""
                if not html.strip():
                    post_rewrites.append(
                        {"post_id": post.id, "rewritten_content": ""}
                    )
                    continue
                try:
                    rewritten = rewrite_post(html, model=args.model)
                except Exception as exc:  # pragma: no cover - defensive
                    print(f"  rewrite failed for post_id={post.id}: {exc}")
                    rewritten = ""
                post_rewrites.append(
                    {"post_id": post.id, "rewritten_content": rewritten}
                )
            score_row.ai_post_rewrites_json = json.dumps(
                post_rewrites, ensure_ascii=False
            )

            # Also generate a full AI article with SEO outline if missing.
            if score_row.ai_article_json is None:
                try:
                    thread_payload = _thread_to_payload(thread)
                    prompt = _build_prompt(thread_payload)
                    rewrite = _call_ollama(prompt, model=args.model)
                    try:
                        _validate_rewrite(thread_payload, rewrite)
                    except Exception as exc:  # pragma: no cover - defensive
                        # If validation fails, still store the raw rewrite so we at least
                        # have a seo_outline and article for inspection.
                        print(
                            f"  validation failed for thread_id={thread.id}: {exc}"
                        )
                    score_row.ai_article_json = json.dumps(
                        rewrite, ensure_ascii=False
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    print(
                        f"  article rewrite failed for thread_id={thread.id}: {exc}"
                    )
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    main()

