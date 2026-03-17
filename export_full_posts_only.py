from pathlib import Path

from client_export import export_full_posts_csv, build_report  # type: ignore[attr-defined]


def main() -> None:
    report = build_report()
    export_full_posts_csv(report)  # type: ignore[arg-type]
    out = Path("exports") / "full_posts.csv"
    print(f"Done. Full Posts CSV: {out.resolve()}")


if __name__ == "__main__":
    main()

