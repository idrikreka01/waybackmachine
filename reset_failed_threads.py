import os
import sys

if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from waybackmachine.db.models import Post, Thread
    from waybackmachine.db.session import get_session_factory
    from waybackmachine.logging_config import configure_logging

    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    factory = get_session_factory()
    session = factory()
    try:
        thread_ids_with_posts = [
            r[0]
            for r in session.query(Post.thread_id).distinct().all()
        ]
        q = session.query(Thread).filter(Thread.posts_fetched == True)
        if thread_ids_with_posts:
            q = q.filter(~Thread.id.in_(thread_ids_with_posts))
        failed = q.all()
        if not failed:
            print("No failed threads (posts_fetched=True but 0 posts).")
            sys.exit(0)
        print(f"Found {len(failed)} threads with posts_fetched=True and 0 posts.")
        dry = os.environ.get("RESET_DRY_RUN", "").strip().lower() in ("1", "true", "yes")
        if dry:
            for t in failed[:20]:
                print(f"  id={t.id} title={t.title[:60]!r}...")
            if len(failed) > 20:
                print(f"  ... and {len(failed) - 20} more")
            print("Set RESET_DRY_RUN=0 and run again to reset posts_fetched to False.")
            sys.exit(0)
        update_q = session.query(Thread).filter(Thread.posts_fetched == True)
        if thread_ids_with_posts:
            update_q = update_q.filter(~Thread.id.in_(thread_ids_with_posts))
        n = update_q.update({Thread.posts_fetched: False}, synchronize_session=False)
        session.commit()
        print(f"Reset posts_fetched to False for {n} threads. Run scraper to retry.")
    finally:
        session.close()
