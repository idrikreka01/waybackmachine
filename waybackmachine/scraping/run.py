import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium.common.exceptions import InvalidSessionIdException, NoSuchWindowException

from waybackmachine.db.models import Category, Subcategory, Thread
from waybackmachine.db.session import get_session_factory, init_db
from waybackmachine.logging_config import configure_logging
from waybackmachine.scraping.browser import create_driver
from waybackmachine.scraping.categories import fetch_categories
from waybackmachine.scraping.posts import fetch_posts
from waybackmachine.scraping.store import (
    save_categories,
    save_posts,
    save_subcategories,
    save_threads,
)
from waybackmachine.scraping.subcategories import fetch_subcategories
from waybackmachine.scraping.threads import fetch_threads

LOG = logging.getLogger(__name__)
MAX_SCRAPE_WORKERS = 5
MAX_SUBCATEGORY_WORKERS = 3


def _fetch_subcategories_chunk(
    chunk: list[tuple[int, str, str]],
    worker_index: int = 0,
) -> tuple[int, str | None]:
    driver = None
    session = None
    try:
        driver = create_driver(worker_index=worker_index)
        factory = get_session_factory()
        session = factory()
        total_saved = 0
        LOG.info("Worker %s: starting chunk (%s categories)", worker_index, len(chunk))
        for category_id, category_name, link in chunk:
            try:
                sub_items = fetch_subcategories(driver, link)
                save_subcategories(session, category_id, sub_items)
                session.commit()
                total_saved += len(sub_items)
                LOG.info(
                    "Worker %s: category '%s' (id=%s) %d subcategories saved",
                    worker_index,
                    category_name[:50],
                    category_id,
                    len(sub_items),
                )
            except (InvalidSessionIdException, NoSuchWindowException):
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                raise
        LOG.info("Worker %s: chunk done (%s subcategories saved)", worker_index, total_saved)
        return (total_saved, None)
    except Exception as e:
        if session:
            try:
                session.rollback()
            except Exception:
                pass
        return (0, str(e))
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass
        if driver:
            try:
                driver.quit()
            except (InvalidSessionIdException, NoSuchWindowException):
                pass
            except Exception:
                LOG.debug("Driver quit failed in worker", exc_info=True)


def _fetch_thread_lists_chunk(
    chunk: list[tuple[int, str, str]],
    worker_index: int = 0,
) -> tuple[int, str | None]:
    driver = None
    session = None
    try:
        driver = create_driver(worker_index=worker_index)
        factory = get_session_factory()
        session = factory()
        total_saved = 0
        LOG.info("Worker %s: starting chunk (%s subcategories)", worker_index, len(chunk))
        for subcategory_id, subcategory_name, link in chunk:
            try:
                thread_items = fetch_threads(driver, link)
                threads = save_threads(session, subcategory_id, thread_items)
                session.query(Subcategory).filter(Subcategory.id == subcategory_id).update(
                    {Subcategory.thread_list_fetched: True}
                )
                session.commit()
                total_saved += len(threads)
                LOG.info(
                    "Worker %s: '%s' (id=%s) %d threads saved",
                    worker_index,
                    subcategory_name[:50],
                    subcategory_id,
                    len(threads),
                )
            except (InvalidSessionIdException, NoSuchWindowException):
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                raise
        LOG.info("Worker %s: chunk done (%s threads saved)", worker_index, total_saved)
        return (total_saved, None)
    except Exception as e:
        if session:
            try:
                session.rollback()
            except Exception:
                pass
        return (0, str(e))
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass
        if driver:
            try:
                driver.quit()
            except (InvalidSessionIdException, NoSuchWindowException):
                pass
            except Exception:
                LOG.debug("Driver quit failed in worker", exc_info=True)


def _fetch_posts_chunk(
    chunk: list[tuple[int, str]],
    worker_index: int = 0,
) -> tuple[int, int, str | None]:
    driver = None
    session = None
    fetched = 0
    saved = 0
    try:
        driver = create_driver(worker_index=worker_index)
        factory = get_session_factory()
        session = factory()
        LOG.info("Worker %s: starting chunk (%s threads)", worker_index, len(chunk))
        for thread_id, link in chunk:
            try:
                session.query(Thread).filter(Thread.id == thread_id).update(
                    {Thread.scrape_in_progress: True}
                )
                session.commit()
                items = fetch_posts(driver, link)
                n = save_posts(session, thread_id, items)
                fetched += len(items)
                saved += n
                session.query(Thread).filter(Thread.id == thread_id).update(
                    {
                        Thread.posts_fetched: n > 0,
                        Thread.scrape_in_progress: False,
                    }
                )
                session.commit()
            except (InvalidSessionIdException, NoSuchWindowException):
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                raise
        LOG.info(
            "Worker %s: chunk done (%s posts fetched, %s new saved)",
            worker_index,
            fetched,
            saved,
        )
        return (fetched, saved, None)
    except Exception as e:
        if session:
            try:
                session.rollback()
            except Exception:
                pass
        if fetched or saved:
            LOG.warning(
                "Worker %s: failed after partial progress (%s fetched, %s saved): %s",
                worker_index,
                fetched,
                saved,
                e,
            )
        return (fetched, saved, str(e))
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass
        if driver:
            try:
                driver.quit()
            except (InvalidSessionIdException, NoSuchWindowException):
                pass
            except Exception:
                LOG.debug("Driver quit failed in worker", exc_info=True)


def scrape_and_save_categories_and_subcategories() -> None:
    factory = get_session_factory()
    init_db()
    posts_only = os.environ.get("SCRAPE_POSTS_ONLY", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if posts_only:
        LOG.info("SCRAPE_POSTS_ONLY set; skipping Phase 1a/1b/1c, running post fetch only")
    if not posts_only:
        driver = create_driver()
        try:
            session = factory()
            try:
                categories = fetch_categories(driver)
                saved_cats = save_categories(session, categories)
                session.commit()
                LOG.info("Phase 1a done: categories saved (%d)", len(saved_cats))
            except KeyboardInterrupt:
                LOG.warning("Interrupted by user; committing progress so far")
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                raise
            except (InvalidSessionIdException, NoSuchWindowException) as e:
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                raise RuntimeError(
                    "Browser session lost. Progress saved. Run again to continue."
                ) from e
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        finally:
            try:
                driver.quit()
            except (InvalidSessionIdException, NoSuchWindowException):
                pass
            except Exception:
                LOG.debug("Driver quit failed", exc_info=True)

        session = factory()
        try:
            category_rows = [
                (r.id, r.name, r.link)
                for r in session.query(Category.id, Category.name, Category.link).all()
            ]
        finally:
            session.close()

        if not category_rows:
            LOG.warning("No categories; skipping Phase 1b")
        else:
            num_workers = min(MAX_SUBCATEGORY_WORKERS, len(category_rows))
            chunk_size = (len(category_rows) + num_workers - 1) // num_workers
            chunks = [
                category_rows[i : i + chunk_size] for i in range(0, len(category_rows), chunk_size)
            ]
            LOG.info(
                "Phase 1b: fetching subcategories for %d categories with %d workers",
                len(category_rows),
                num_workers,
            )
            total_subs = 0
            errors = []
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = {
                    executor.submit(_fetch_subcategories_chunk, c, idx): c
                    for idx, c in enumerate(chunks)
                }
                for future in as_completed(futures):
                    try:
                        saved, err = future.result()
                        total_subs += saved
                        if err:
                            errors.append(err)
                    except Exception as e:
                        errors.append(str(e))
            if errors:
                for err in errors:
                    LOG.error("Phase 1b worker error: %s", err)
            LOG.info("Phase 1b done: %d subcategories saved", total_subs)

        session = factory()
        try:
            subcategory_rows = [
                (r.id, r.name, r.link)
                for r in session.query(Subcategory.id, Subcategory.name, Subcategory.link)
                .filter(Subcategory.thread_list_fetched == False)
                .all()
            ]
        finally:
            session.close()

        if not subcategory_rows:
            LOG.info("No subcategories left to fetch thread lists for; skipping Phase 1c")
        else:
            num_workers = min(MAX_SCRAPE_WORKERS, len(subcategory_rows))
            chunk_size = (len(subcategory_rows) + num_workers - 1) // num_workers
            chunks = [
                subcategory_rows[i : i + chunk_size]
                for i in range(0, len(subcategory_rows), chunk_size)
            ]
            LOG.info(
                "Phase 1c: fetching thread lists for %d subcategories with %d workers",
                len(subcategory_rows),
                num_workers,
            )
            total_threads = 0
            errors = []
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = {
                    executor.submit(_fetch_thread_lists_chunk, c, idx): c
                    for idx, c in enumerate(chunks)
                }
                for future in as_completed(futures):
                    try:
                        saved, err = future.result()
                        total_threads += saved
                        if err:
                            errors.append(err)
                    except Exception as e:
                        errors.append(str(e))
            if errors:
                for err in errors:
                    LOG.error("Phase 1c worker error: %s", err)
            LOG.info("Phase 1c done: %d threads saved across subcategories", total_threads)

    session = factory()
    try:
        thread_rows = [
            (r.id, r.link)
            for r in session.query(Thread.id, Thread.link)
            .filter(Thread.posts_fetched == False)
            .all()
        ]
    finally:
        session.close()

    if not thread_rows:
        LOG.info("No threads left to fetch posts for; skipping Phase 2")
    else:
        num_workers = min(MAX_SCRAPE_WORKERS, len(thread_rows))
        chunk_size = (len(thread_rows) + num_workers - 1) // num_workers
        chunks = [thread_rows[i : i + chunk_size] for i in range(0, len(thread_rows), chunk_size)]
        LOG.info(
            "Phase 2: fetching posts for %d threads with %d workers "
            "(re-run to continue after cooldown/interruptions)",
            len(thread_rows),
            num_workers,
        )
        total_fetched = 0
        total_saved = 0
        errors = []
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(_fetch_posts_chunk, c, idx): c for idx, c in enumerate(chunks)
            }
            for future in as_completed(futures):
                chunk = futures[future]
                try:
                    fetched, saved, err = future.result()
                    total_fetched += fetched
                    total_saved += saved
                    if err:
                        errors.append(err)
                except Exception as e:
                    errors.append(str(e))
        if errors:
            for err in errors:
                LOG.error("Worker error: %s", err)
        LOG.info(
            "Phase 2 done: %d posts fetched, %d new saved",
            total_fetched,
            total_saved,
        )


if __name__ == "__main__":
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    try:
        scrape_and_save_categories_and_subcategories()
    except Exception:
        LOG.exception("Scrape failed")
        sys.exit(1)
