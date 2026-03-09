import argparse
import os
import subprocess
import sys

from waybackmachine.logging_config import configure_logging
from waybackmachine.scraping.run import scrape_and_save_categories_and_subcategories
from waybackmachine.scoring.run_score_to_db import run_score_to_db


def _run_generate_samples(limit: int, output_dir: str, model: str | None) -> None:
    cmd = [
        sys.executable,
        "-m",
        "waybackmachine.ai.generate_samples",
        "--limit",
        str(limit),
        "--output-dir",
        output_dir,
    ]
    if model:
        cmd.extend(["--model", model])
    subprocess.run(cmd, check=True)


def main() -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))

    parser = argparse.ArgumentParser(
        description="End-to-end runner: scrape -> score+route -> AI samples."
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip scraping (use existing DB contents).",
    )
    parser.add_argument(
        "--skip-score",
        action="store_true",
        help="Skip scoring/routing (use existing thread_evergreen_score rows).",
    )
    parser.add_argument(
        "--skip-samples",
        action="store_true",
        help="Skip AI sample generation.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max number of PROMOTE threads for AI samples (default: 10).",
    )
    parser.add_argument(
        "--output-dir",
        default="samples",
        help="Directory where JSON samples will be written (default: samples).",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", None),
        help="Ollama model name to use for rewrites (overrides OLLAMA_MODEL env).",
    )
    args = parser.parse_args()

    if not args.skip_scrape:
        print("=== Phase 1: Scraping categories, threads, posts ===")
        scrape_and_save_categories_and_subcategories()
    else:
        print("=== Phase 1: Scraping skipped (using existing DB) ===")

    if not args.skip_score:
        print("=== Phase 2: Evergreen scoring + routing into DB ===")
        stats = run_score_to_db()
        print(
            f"Scoring stats: eligible={stats['eligible']} processed={stats['processed']} "
            f"saved={stats['saved']} skipped={stats['skipped']} excluded={stats['excluded']}"
        )
    else:
        print("=== Phase 2: Scoring skipped (using existing thread_evergreen_score) ===")

    if not args.skip_samples:
        print("=== Phase 3: AI rewrite + sample export ===")
        _run_generate_samples(args.limit, args.output_dir, args.model)
    else:
        print("=== Phase 3: AI sample generation skipped ===")


if __name__ == "__main__":
    main()

import os
import sys

if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from waybackmachine.db.session import init_db
    from waybackmachine.logging_config import configure_logging
    from waybackmachine.scraping.run import scrape_and_save_categories_and_subcategories

    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    init_db()
    try:
        scrape_and_save_categories_and_subcategories()
    except Exception:
        import logging

        logging.getLogger("__main__").exception("Scrape failed")
        sys.exit(1)
