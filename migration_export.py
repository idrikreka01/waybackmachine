import csv
from pathlib import Path
from typing import Any

from export_client_report import build_report


OUTPUT_DIR = Path("exports")
OUTPUT_DIR.mkdir(exist_ok=True)


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _should_include_thread(thread: dict[str, Any]) -> bool:
    scoring = thread.get("scoring") or {}
    decision = (scoring.get("decision") or "").upper()
    if decision != "PROMOTE":
        return False

    title = (thread.get("title") or "").lower()
    category_path = (thread.get("category_path") or "").lower()

    soft_exclude_keywords = [
        "my truck",
        "project:",
        "build:",
        " build ",
        "before & after",
        "before and after",
        "post your lifted",
        "post your setup",
        "post your expo",
        "post your worst",
        "show your expo",
        "post your pics",
        "mud pics",
        "members rides",
        "new members - help us out",
        "official chit-chat",
        "chit-chat thread",
        "sold my silverado",
        "detail sites /links",
    ]

    for kw in soft_exclude_keywords:
        if kw in title:
            return False

    non_technical_categories = [
        "image gallery",
        "snapshots/videos",
        "signature requests",
        "digital dreams",
        "fsc chapters",
        "introduction",
        "overland expeditions",
        "trails and mudholes",
        "other rides tech",
        "detailing",
    ]

    for cat_kw in non_technical_categories:
        if cat_kw in category_path:
            return False

    return True


def export_migration_csv(path: Path | None = None) -> Path:
    report = build_report()
    threads = report.get("threads", []) or []

    if path is None:
        path = OUTPUT_DIR / "migration_topics.csv"

    headers = [
        "id_source_thread",
        "original_url",
        "original_category_path",
        "title",
        "body_markdown",
        "target_category",
        "target_era",
        "target_tech_type",
        "tags",
        "decision",
        "final_score",
        "has_ai_article",
        "has_post_rewrites",
    ]

    rows: list[list[str]] = []

    for thread in threads:
        if not _should_include_thread(thread):
            continue

        scoring = thread.get("scoring") or {}
        routing = thread.get("routing") or {}
        ai_article = thread.get("ai_article") or {}

        thread_id = thread.get("thread_id")
        original_url = thread.get("url") or ""
        original_category_path = thread.get("category_path") or ""

        rewritten_title = ai_article.get("rewritten_title") if isinstance(ai_article, dict) else None
        rewritten_md = (
            ai_article.get("rewritten_article_markdown") if isinstance(ai_article, dict) else None
        )

        title = rewritten_title or thread.get("title") or ""
        body_markdown = rewritten_md or ""

        era_id = routing.get("era_id") or ""
        tech_type = routing.get("tech_type") or ""
        forum_main = routing.get("forum_main") or ""
        forum_sub = routing.get("forum_sub") or ""

        if forum_main and forum_sub:
            target_category = f"{forum_main} > {forum_sub}"
        else:
            target_category = forum_main or ""

        tags: list[str] = []
        score_payload = scoring.get("result_json") or {}
        payload_tags = score_payload.get("tags")
        if isinstance(payload_tags, list):
            tags = [str(t) for t in payload_tags if t]
        else:
            if era_id:
                tags.append(str(era_id))
            if tech_type:
                tags.append(str(tech_type))

        decision = scoring.get("decision") or ""
        if decision:
            tags.append(str(decision))

        final_score = scoring.get("final_score")

        has_ai_article = "yes" if isinstance(ai_article, dict) and ai_article else "no"
        post_rewrites_count = thread.get("ai_post_rewrites_count") or 0
        has_post_rewrites = "yes" if post_rewrites_count else "no"

        rows.append(
            [
                _safe_str(thread_id),
                _safe_str(original_url),
                _safe_str(original_category_path),
                _safe_str(title),
                _safe_str(body_markdown),
                _safe_str(target_category),
                _safe_str(era_id),
                _safe_str(tech_type),
                ",".join(tags),
                _safe_str(decision),
                _safe_str(final_score),
                has_ai_article,
                has_post_rewrites,
            ]
        )

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    return path


def main() -> None:
    csv_path = export_migration_csv()
    print(f"Wrote migration topics CSV to: {csv_path.resolve()}")


if __name__ == "__main__":
    main()

