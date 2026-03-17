import argparse
import json
import os

from sqlalchemy.orm import joinedload

from waybackmachine.ai.rewrite_thread import (  # type: ignore[attr-defined]
    _build_prompt,
    _call_ollama,
    _thread_to_payload,
    _validate_rewrite,
)
from waybackmachine.db.models import Thread, ThreadEvergreenScore
from waybackmachine.db.session import get_session_factory
from waybackmachine.logging_config import configure_logging


def main() -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))

    parser = argparse.ArgumentParser(
        description=(
            "Generate full AI articles (with SEO outline) for scored threads that "
            "do not yet have ai_article_json."
        )
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
        help="Ollama model name to use for article generation.",
    )
    parser.add_argument(
        "--decision",
        default="PROMOTE",
        help="Only process threads with this decision (default: PROMOTE). "
        "Use empty string to disable decision filtering.",
    )
    args = parser.parse_args()

    factory = get_session_factory()
    session = factory()
    try:
        q = (
            session.query(ThreadEvergreenScore)
            .options(
                joinedload(ThreadEvergreenScore.thread)
                .joinedload(Thread.posts),
                joinedload(ThreadEvergreenScore.thread)
                .joinedload(Thread.subcategory),
            )
            .filter(ThreadEvergreenScore.ai_article_json.is_(None))
        )
        if args.decision:
            q = q.filter(ThreadEvergreenScore.decision == args.decision)

        rows = list(q.all())
        print(f"Found {len(rows)} threads without ai_article_json to process.")

        for score_row in rows:
            thread: Thread | None = score_row.thread
            if thread is None:
                continue

            print(f"Generating article for thread_id={thread.id} title={thread.title!r}")
            try:
                thread_payload = _thread_to_payload(thread)
                prompt = _build_prompt(thread_payload)
                rewrite = _call_ollama(prompt, model=args.model)
                try:
                    _validate_rewrite(thread_payload, rewrite)
                except Exception as exc:  # pragma: no cover - defensive
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

