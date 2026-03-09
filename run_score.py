"""
Score threads and write results to score.json only. Does NOT update the database.
To refresh routing (era_id, forum_main, forum_sub) in the DB and in exports, run:
  python main.py --skip-scrape --skip-samples
or: python -m waybackmachine.scoring.run_score_to_db
"""
import json
import os
import sys

if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from waybackmachine.db.models import Thread
    from waybackmachine.db.session import get_session_factory
    from waybackmachine.logging_config import configure_logging
    from waybackmachine.scoring.context_builder import build_thread_context
    from waybackmachine.scoring.evergreen_score import compute_evergreen_score

    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    factory = get_session_factory()
    session = factory()
    try:
        thread_ids = [
            r.id
            for r in session.query(Thread.id).filter(Thread.posts_fetched == True).all()
        ]
    finally:
        session.close()

    if not thread_ids:
        print("No threads with posts_fetched; run scraping first.", file=sys.stderr)
        sys.exit(0)

    total_eligible = len(thread_ids)
    results = []
    session = factory()
    try:
        for thread_id in thread_ids:
            ctx = build_thread_context(session, thread_id)
            if ctx is None:
                continue
            results.append(compute_evergreen_score(ctx))
    finally:
        session.close()

    processed = len(results)
    skipped = total_eligible - processed
    print(f"Threads eligible (posts_fetched): {total_eligible}")
    print(f"Threads processed (scored):      {processed}")
    if skipped:
        print(f"Threads skipped (no context):   {skipped}")

    out_path = os.environ.get("EVERGREEN_SCORE_OUTPUT", "score.json")
    if out_path and out_path != "-":
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Wrote {processed} scores to {out_path}")
    else:
        print(json.dumps(results, indent=2))
