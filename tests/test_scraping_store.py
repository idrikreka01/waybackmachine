from waybackmachine.db.models import Category, Subcategory, Thread
from waybackmachine.scraping.categories import CategoryItem
from waybackmachine.scraping.store import save_categories, save_subcategories, save_threads
from waybackmachine.scraping.subcategories import SubcategoryItem
from waybackmachine.scraping.threads import ThreadItem


def test_save_categories_idempotent(session):
    items = [
        CategoryItem(name="Cat A", link="https://example.com/a"),
        CategoryItem(name="Cat B", link="https://example.com/b"),
    ]
    first = save_categories(session, items)
    session.commit()
    count_first = session.query(Category).count()
    second = save_categories(session, items)
    session.commit()
    count_second = session.query(Category).count()
    assert count_second == count_first
    assert first[0].id == second[0].id
    assert first[1].id == second[1].id


def test_save_subcategories_idempotent(session):
    cat = Category(name="Cat", link="https://example.com/cat")
    session.add(cat)
    session.flush()
    items = [
        SubcategoryItem(
            name="Sub A",
            link="https://example.com/sub-a",
            description="Desc",
            threads_no=10,
            posts_no=20,
        ),
    ]
    save_subcategories(session, cat.id, items)
    session.commit()
    count_first = session.query(Subcategory).filter(Subcategory.category_id == cat.id).count()
    save_subcategories(session, cat.id, items)
    session.commit()
    count_second = session.query(Subcategory).filter(Subcategory.category_id == cat.id).count()
    assert count_first == 1
    assert count_second == 1


def test_save_threads_idempotent(session):
    cat = Category(name="Cat", link="https://example.com/cat")
    session.add(cat)
    session.flush()
    sub = Subcategory(
        category_id=cat.id,
        name="Sub",
        link="https://example.com/sub",
        threads_no=1,
        posts_no=2,
        description=None,
    )
    session.add(sub)
    session.flush()
    items = [
        ThreadItem(
            title="Thread One",
            link="https://example.com/showthread?t=1",
            replies_no=5,
            views_no=100,
            pagination=True,
            is_sticky=False,
            pagination_no=3,
        ),
    ]
    first = save_threads(session, sub.id, items)
    session.commit()
    count_first = session.query(Thread).filter(Thread.subcategory_id == sub.id).count()
    second = save_threads(session, sub.id, items)
    session.commit()
    count_second = session.query(Thread).filter(Thread.subcategory_id == sub.id).count()
    assert count_first == 1
    assert count_second == 1
    assert first[0].id == second[0].id
