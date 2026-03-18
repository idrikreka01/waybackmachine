"""
Score threads and write results into the database (thread_evergreen_score).

Equivalent to running:
  python -m waybackmachine.scoring.run_score_to_db
"""
import os
import sys

if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from waybackmachine.logging_config import configure_logging
    from waybackmachine.scoring.run_score_to_db import main as run_score_to_db_main

    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    run_score_to_db_main()
