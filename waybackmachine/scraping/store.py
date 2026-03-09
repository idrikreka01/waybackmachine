import logging

from sqlalchemy.orm import Session

from waybackmachine.db.models import Category, Post, Subcategory, Thread
from waybackmachine.scraping.categories import CategoryItem
from waybackmachine.scraping.posts import PostItem
from waybackmachine.scraping.subcategories import SubcategoryItem
from waybackmachine.scraping.threads import ThreadItem

LOG = logging.getLogger(__name__)


def save_categories(session: Session, items: list[CategoryItem]) -> list[Category]:
    result: list[Category] = []
    new_count = 0
    for item in items:
        existing = session.query(Category).filter(Category.link == item.link).first()
        if existing:
            result.append(existing)
            continue
        cat = Category(name=item.name, link=item.link)
        session.add(cat)
        result.append(cat)
        new_count += 1
    session.flush()
    LOG.info(
        "Categories saved",
        extra={"total": len(result), "new": new_count},
    )
    return result


def save_subcategories(
    session: Session, category_id: int, items: list[SubcategoryItem]
) -> list[Subcategory]:
    saved: list[Subcategory] = []
    for item in items:
        existing = (
            session.query(Subcategory)
            .filter(
                Subcategory.category_id == category_id,
                Subcategory.link == item.link,
            )
            .first()
        )
        if existing:
            continue
        sub = Subcategory(
            category_id=category_id,
            name=item.name,
            link=item.link,
            threads_no=item.threads_no,
            posts_no=item.posts_no,
            description=item.description,
        )
        session.add(sub)
        saved.append(sub)
    session.flush()
    LOG.info(
        "Subcategories saved",
        extra={"category_id": category_id, "new_count": len(saved)},
    )
    return saved


def save_threads(session: Session, subcategory_id: int, items: list[ThreadItem]) -> list[Thread]:
    result: list[Thread] = []
    new_count = 0
    for item in items:
        existing = (
            session.query(Thread)
            .filter(
                Thread.subcategory_id == subcategory_id,
                Thread.link == item.link,
            )
            .first()
        )
        if existing:
            result.append(existing)
            continue
        thread = Thread(
            subcategory_id=subcategory_id,
            title=item.title,
            link=item.link,
            replies_no=item.replies_no,
            views_no=item.views_no,
            pagination=item.pagination,
            is_sticky=item.is_sticky,
            pagination_no=item.pagination_no,
        )
        session.add(thread)
        result.append(thread)
        new_count += 1
    session.flush()
    LOG.info(
        "Threads saved to DB: %d total, %d new (subcategory_id=%s)",
        len(result),
        new_count,
        subcategory_id,
    )
    return result


def save_posts(session: Session, thread_id: int, items: list[PostItem]) -> int:
    new_count = 0
    for item in items:
        if item.post_page_id is not None:
            existing = (
                session.query(Post)
                .filter(
                    Post.thread_id == thread_id,
                    Post.post_page_id == item.post_page_id,
                )
                .first()
            )
            if existing:
                continue
        post = Post(
            thread_id=thread_id,
            user_username=item.user_username,
            user_joindate=item.user_joindate,
            user_location=item.user_location,
            user_posts=item.user_posts,
            user_register=item.user_register,
            user_age=item.user_age,
            post_date_time=item.post_date_time,
            post_content=item.post_content,
            post_page_id=item.post_page_id,
            post_counter=item.post_counter,
        )
        session.add(post)
        new_count += 1
    session.flush()
    LOG.info(
        "Posts saved to DB: %d parsed, %d new (thread_id=%s)",
        len(items),
        new_count,
        thread_id,
    )
    return new_count
