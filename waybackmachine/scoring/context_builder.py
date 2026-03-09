from datetime import datetime

from sqlalchemy.orm import Session

from waybackmachine.db.models import Category, Post, Subcategory, Thread

REVIVAL_GAP_DAYS = 180


def build_thread_context(session: Session, thread_id: int) -> dict | None:
    thread = session.query(Thread).filter(Thread.id == thread_id).first()
    if not thread:
        return None
    sub = session.query(Subcategory).filter(Subcategory.id == thread.subcategory_id).first()
    if not sub:
        return None
    cat = session.query(Category).filter(Category.id == sub.category_id).first()
    if not cat:
        return None
    category_path = f"{cat.name} > {sub.name}"

    posts = (
        session.query(Post)
        .filter(Post.thread_id == thread_id, Post.post_date_time.isnot(None))
        .order_by(Post.post_date_time.asc())
        .all()
    )
    created_at: datetime | None = None
    last_post_at: datetime | None = None
    first_post_text: str | None = None
    revival_count = 0
    activity_span_years = 0

    if posts:
        dates = [p.post_date_time for p in posts if p.post_date_time]
        if dates:
            created_at = min(dates)
            last_post_at = max(dates)
            first_post = next((p for p in posts if p.post_date_time == created_at), posts[0])
            first_post_text = (first_post.post_content or "").strip() or None
            sorted_dates = sorted(dates)
            for i in range(1, len(sorted_dates)):
                delta = (sorted_dates[i] - sorted_dates[i - 1]).days
                if delta >= REVIVAL_GAP_DAYS:
                    revival_count += 1
            if created_at and last_post_at:
                activity_span_years = int(
                    (last_post_at - created_at).total_seconds() / (365.25 * 24 * 3600)
                )

    return {
        "thread_id": thread.id,
        "title": thread.title,
        "link": thread.link,
        "category_path": category_path,
        "subcategory_name": sub.name,
        "is_sticky": thread.is_sticky,
        "replies_no": thread.replies_no,
        "pagination_no": thread.pagination_no,
        "created_at": created_at,
        "last_post_at": last_post_at,
        "activity_span_years": activity_span_years,
        "revival_count": revival_count,
        "first_post_text": first_post_text,
    }
