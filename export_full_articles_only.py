# export_full_articles_only.py
from client_export import build_report, export_full_articles_csv  # type: ignore[attr-defined]
from pathlib import Path

def main() -> None:
    report = build_report()
    export_full_articles_csv(report)  # type: ignore[arg-type]
    out = Path("exports") / "full_articles.csv"
    print(f"Done. Full Articles CSV: {out.resolve()}")

if __name__ == "__main__":
    main()