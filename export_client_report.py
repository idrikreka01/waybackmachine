import json
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from waybackmachine.db.models import Category, Post, Subcategory, Thread, ThreadEvergreenScore
from waybackmachine.db.session import get_session_factory


def build_report() -> dict:
    factory = get_session_factory()
    session = factory()
    try:
        total_threads = session.query(func.count(Thread.id)).scalar() or 0
        threads_with_posts = (
            session.query(func.count(Thread.id)).filter(Thread.posts_fetched).scalar() or 0
        )
        total_posts = session.query(func.count(Post.id)).scalar() or 0

        total_scored = session.query(func.count(ThreadEvergreenScore.id)).scalar() or 0
        promote_count = (
            session.query(func.count(ThreadEvergreenScore.id))
            .filter(ThreadEvergreenScore.decision == "PROMOTE")
            .scalar()
            or 0
        )
        hold_count = (
            session.query(func.count(ThreadEvergreenScore.id))
            .filter(ThreadEvergreenScore.decision == "HOLD")
            .scalar()
            or 0
        )
        archive_count = (
            session.query(func.count(ThreadEvergreenScore.id))
            .filter(ThreadEvergreenScore.decision == "ARCHIVE")
            .scalar()
            or 0
        )
        ai_completed = (
            session.query(func.count(ThreadEvergreenScore.id))
            .filter(ThreadEvergreenScore.ai_article_json.isnot(None))
            .scalar()
            or 0
        )

        scored_rows = (
            session.query(ThreadEvergreenScore)
            .options(
                joinedload(ThreadEvergreenScore.thread)
                .joinedload(Thread.subcategory)
                .joinedload(Subcategory.category),
                joinedload(ThreadEvergreenScore.thread).joinedload(Thread.posts),
            )
            .order_by(ThreadEvergreenScore.final_score.desc())
            .all()
        )

        thread_items: list[dict] = []
        categories_map: dict[str, dict[str, list[dict]]] = {}
        for row in scored_rows:
            thread: Thread | None = row.thread
            if thread is None or thread.subcategory is None:
                continue
            sub: Subcategory = thread.subcategory
            cat: Category | None = sub.category
            if cat is None:
                continue

            score_payload_raw = row.result_json
            try:
                score_payload = json.loads(score_payload_raw) if score_payload_raw else None
            except Exception:
                score_payload = None

            try:
                ai_article = json.loads(row.ai_article_json) if row.ai_article_json else None
            except Exception:
                ai_article = None
            try:
                post_rewrites_raw = (
                    json.loads(row.ai_post_rewrites_json)
                    if row.ai_post_rewrites_json
                    else None
                )
            except Exception:
                post_rewrites_raw = None

            rewrite_by_post_id: dict[int, str] = {}
            if isinstance(post_rewrites_raw, list):
                for item in post_rewrites_raw:
                    pid = item.get("post_id")
                    content = item.get("rewritten_content") or ""
                    if isinstance(pid, int):
                        rewrite_by_post_id[pid] = content

            post_items: list[dict] = []
            for post in sorted(thread.posts, key=lambda p: (p.post_page_id or 0, p.id)):
                post_items.append(
                    {
                        "post_id": post.id,
                        "post_page_id": post.post_page_id,
                        "post_counter": post.post_counter,
                        "post_date_time": (
                            post.post_date_time.isoformat() if post.post_date_time else None
                        ),
                        "user_username": post.user_username,
                        "user_age": post.user_age,
                        "user_location": post.user_location,
                        "user_posts": post.user_posts,
                        "user_joindate": post.user_joindate,
                        "user_register": post.user_register,
                        "original_html": post.post_content,
                        "rewritten_content": rewrite_by_post_id.get(post.id, ""),
                    }
                )

            item = {
                "thread_id": thread.id,
                "title": thread.title,
                "url": thread.link,
                "category_path": f"{cat.name} > {sub.name}",
                "replies": thread.replies_no,
                "views": thread.views_no,
                "is_sticky": thread.is_sticky,
                "pagination": thread.pagination,
                "pagination_no": thread.pagination_no,
                "posts_fetched": thread.posts_fetched,
                "scoring": {
                    "final_score": row.final_score,
                    "raw_score": row.raw_score,
                    "decision": row.decision,
                    "scoring_version": row.scoring_version,
                    "result_json": score_payload,
                    "result_json_raw": score_payload_raw,
                    "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() + "Z" if row.updated_at else None,
                },
                "routing": {
                    "era_id": row.era_id,
                    "era_score": row.era_score,
                    "tech_type": row.tech_type,
                    "tech_score": row.tech_score,
                    "forum_main": row.forum_main,
                    "forum_sub": row.forum_sub,
                },
                "ai_article": ai_article,
                "ai_article_json_raw": row.ai_article_json,
                "ai_post_rewrites_json_raw": row.ai_post_rewrites_json,
                "ai_post_rewrites_count": len(rewrite_by_post_id),
                "posts": post_items,
            }
            thread_items.append(item)

            cat_name = cat.name
            sub_name = sub.name
            if cat_name not in categories_map:
                categories_map[cat_name] = {}
            categories_map[cat_name].setdefault(sub_name, []).append(item)

        categories: list[dict] = []
        for cat_name, subs in categories_map.items():
            sub_list: list[dict] = []
            for sub_name, items in subs.items():
                sub_list.append(
                    {
                        "subcategory": sub_name,
                        "threads": items,
                    }
                )
            categories.append(
                {
                    "category": cat_name,
                    "subcategories": sub_list,
                }
            )

        report = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "summary": {
                "threads_total": total_threads,
                "threads_with_posts": threads_with_posts,
                "posts_total": total_posts,
                "scored_total": total_scored,
                "decisions": {
                    "PROMOTE": promote_count,
                    "HOLD": hold_count,
                    "ARCHIVE": archive_count,
                },
                "ai_completed_threads": ai_completed,
            },
            "threads": thread_items,
            "categories": categories,
        }
        return report
    finally:
        session.close()


def main() -> None:
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

