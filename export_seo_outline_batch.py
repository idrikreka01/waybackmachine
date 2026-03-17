from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from waybackmachine.ai.rewrite_thread import (
    _build_prompt,
    _call_ollama,
    _thread_to_payload,
)
from waybackmachine.db.models import Thread, ThreadEvergreenScore
from waybackmachine.db.session import get_session_factory


def export_seo_outline_batch(model: str | None = None) -> Path:
    """
    Generate SEO outlines for all PROMOTE threads and write them to a CSV.

    This does NOT persist anything back to the database; it only reads threads,
    calls the AI rewrite pipeline, and writes one row per thread with:
    - thread_id, title, url, decision, final_score, seo_outline_json
    """
    if not model:
        model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")

    output_dir = Path("exports")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "seo_outline_batch.csv"

    factory = get_session_factory()
    session = factory()

    try:
        rows = (
            session.query(ThreadEvergreenScore)
            .filter(ThreadEvergreenScore.decision == "PROMOTE")
            .order_by(ThreadEvergreenScore.final_score.desc())
            .all()
        )

        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "thread_id",
                    "title",
                    "url",
                    "decision",
                    "final_score",
                    "seo_outline_json",
                ]
            )

            for row in rows:
                thread = (
                    session.query(Thread)
                    .filter(Thread.id == row.thread_id)
                    .first()
                )
                if thread is None:
                    continue

                try:
                    payload = _thread_to_payload(thread)
                    prompt = _build_prompt(payload)
                    rewrite = _call_ollama(prompt, model=model)
                    seo_outline = rewrite.get("seo_outline") or []
                except Exception as exc:
                    print(f"Error on thread {row.thread_id}: {exc}")
                    seo_outline = []

                seo_outline_json = json.dumps(seo_outline, ensure_ascii=False)
                writer.writerow(
                    [
                        row.thread_id,
                        thread.title,
                        thread.link,
                        row.decision,
                        row.final_score,
                        seo_outline_json,
                    ]
                )
    finally:
        session.close()

    return output_path


def main() -> None:
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    path = export_seo_outline_batch(model=model)
    print(f"SEO outline batch written to {path.resolve()}")


if __name__ == "__main__":
    main()

