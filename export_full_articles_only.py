from pathlib import Path
import json

from client_export import build_report, export_full_articles_csv  # type: ignore[attr-defined]
from waybackmachine.db.models import ThreadEvergreenScore  # type: ignore[attr-defined]
from waybackmachine.db.session import get_session_factory  # type: ignore[attr-defined]


def _synth_body_from_post_rewrites(score_row: ThreadEvergreenScore) -> str:
    raw = score_row.ai_post_rewrites_json
    if not raw:
        return ""
    try:
        items = json.loads(raw)
    except Exception:
        return ""
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        txt = (it.get("rewritten_content") or "").strip()
        if txt:
            parts.append(txt)
    return "\n\n".join(parts).strip()


def main() -> None:
    report = build_report()

    # Enrich threads with a best-effort AI article body.
    factory = get_session_factory()
    session = factory()
    try:
        score_by_tid: dict[int, ThreadEvergreenScore] = {
            r.thread_id: r for r in session.query(ThreadEvergreenScore).all()
        }
    finally:
        session.close()

    threads = report.get("threads") or []
    for t in threads:
        tid = t.get("thread_id")
        if not isinstance(tid, int):
            continue
        score_row = score_by_tid.get(tid)
        if score_row is None:
            continue

        # Start from DB ai_article_json if present.
        ai_article_raw = score_row.ai_article_json
        ai_article: dict = {}
        if ai_article_raw:
            try:
                loaded = json.loads(ai_article_raw)
                if isinstance(loaded, dict):
                    ai_article = loaded
            except Exception:
                ai_article = {}

        body = (ai_article.get("rewritten_article_markdown") or "").strip()
        if not body:
            # Fall back to synthesizing from per-post rewrites.
            body = _synth_body_from_post_rewrites(score_row)

        if not ai_article and body:
            ai_article = {
                "rewritten_title": t.get("title") or "",
                "summary": "",
                "seo_outline": [],
                "rewritten_article_markdown": body,
                "evidence": [],
                "notes": "",
            }
        elif body:
            ai_article["rewritten_article_markdown"] = body

        if ai_article:
            t["ai_article"] = ai_article

    # Keep only threads that now have some ai_article attached.
    filtered_threads = []
    for t in threads:
        ai_article = t.get("ai_article")
        if isinstance(ai_article, dict) and ai_article:
            filtered_threads.append(t)

    report["threads"] = filtered_threads

    export_full_articles_csv(report)  # type: ignore[arg-type]
    out = Path("exports") / "full_articles.csv"
    print(f"Done. Full Articles CSV: {out.resolve()}")


if __name__ == "__main__":
    main()