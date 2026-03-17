# export_full_articles_only.py
from pathlib import Path

from client_export import build_report, export_full_articles_csv  # type: ignore[attr-defined]


def main() -> None:
    report = build_report()

    # Filter to threads that actually have an AI article attached.
    threads = report.get("threads") or []
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