from pathlib import Path
import csv
import json


SAMPLES_DIR = Path("samples")
OUTPUT_PATH = Path("exports") / "full_articles.csv"


def main() -> None:
    rows: list[list[str]] = []

    for path in sorted(SAMPLES_DIR.glob("thread_*.json")):
        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        thread = data.get("thread") or {}
        scoring = data.get("scoring") or {}
        routing = data.get("routing") or {}
        rewrite = data.get("rewrite") or {}

        # Prefer article-style rewrite if present at top level
        body = ""
        if isinstance(rewrite, dict):
            body = (rewrite.get("rewritten_article_markdown") or "").strip()

        # If not present, try nested under scoring.result.rewrite
        if not body:
            result = scoring.get("result") or {}
            inner_rewrite = result.get("rewrite") or {}
            if isinstance(inner_rewrite, dict):
                body = (inner_rewrite.get("rewritten_article_markdown") or "").strip()

        if not body:
            # Skip threads without an article body
            continue

        # Tags come from scoring.result.tags if present
        tags_list: list[str] = []
        result = scoring.get("result") or {}
        tags_raw = result.get("tags") or []
        if isinstance(tags_raw, list):
            tags_list = [str(t).strip() for t in tags_raw if str(t).strip()]
        # Dedupe while preserving order
        seen = set()
        deduped_tags: list[str] = []
        for t in tags_list:
            if t not in seen:
                seen.add(t)
                deduped_tags.append(t)
        tags = ",".join(deduped_tags)

        rows.append(
            [
                str(thread.get("thread_id") or ""),
                str(thread.get("title") or ""),
                str(thread.get("url") or ""),
                str(thread.get("category_path") or ""),
                str(scoring.get("decision") or ""),
                str(scoring.get("final_score") or ""),
                str(routing.get("forum_main") or ""),
                str(routing.get("forum_sub") or ""),
                tags,
                body,
            ]
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    headers = [
        "thread_id",
        "title",
        "url",
        "category_path",
        "decision",
        "final_score",
        "forum_main",
        "forum_sub",
        "tags",
        "rewritten_article_markdown",
    ]

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"Done. Full Articles CSV (from samples/*): {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()