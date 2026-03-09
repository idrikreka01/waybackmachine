import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from lxml import html
from selenium.webdriver.remote.webdriver import WebDriver

from waybackmachine.scraping.browser import get_page_html
from waybackmachine.scraping.urls import ensure_wayback_url

LOG = logging.getLogger(__name__)

THREADBIT_XPATH_STICKIES = "//div[@id='threadlist']//ol[contains(@class,'stickies') or @id='stickies']/li[contains(@class,'threadbit')]"
THREADBIT_XPATH_THREADS = "//div[@id='threadlist']//ol[contains(@class,'threads') or @id='threads']/li[contains(@class,'threadbit')]"
THREADBIT_XPATH_FALLBACK = "//div[@id='threadlist']//li[contains(@class,'threadbit')]"
TITLE_LINK_XPATH = ".//h3[contains(@class,'threadtitle')]//a[contains(@class,'title') and @href]"
PAGE_NUM_PATTERN = re.compile(r"[-](\d+)\.html|page=(\d+)|[\?&]p=(\d+)")
PAGES_LABEL_PATTERN = re.compile(r"(\d+)\s*Pages?", re.I)
FORUM_PAGENAV_XPATH = "//div[contains(@class,'pagenav')]//a[@href] | //div[contains(@class,'pagination')]//a[@href]"
FORUM_PAGE_HREF_PATTERN = re.compile(
    r"pagenumber=\d+|[/-]page[-]?\d+|page=\d+|\?.*\d+|/\d+(?:\.html)?(?:\?|$)", re.I
)
MAX_THREAD_LIST_PAGES = 200


@dataclass
class ThreadItem:
    title: str
    link: str
    replies_no: int
    views_no: int
    pagination: bool
    is_sticky: bool
    pagination_no: int | None


def _parse_stat_number(text: str) -> int:
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else 0


def _thread_list_page_urls(tree, base_url: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    base_clean = base_url.split("#")[0].rstrip("/")
    if base_clean not in seen:
        seen.add(base_clean)
        out.append(base_url)
    for a in tree.xpath(FORUM_PAGENAV_XPATH):
        href = (a.get("href") or "").strip()
        if not href or not FORUM_PAGE_HREF_PATTERN.search(href):
            continue
        full = ensure_wayback_url(base_url, urljoin(base_url, href))
        full_clean = full.split("#")[0].rstrip("/")
        if full_clean in seen:
            continue
        seen.add(full_clean)
        out.append(full)
    return out


def _pagination_from_threadbit(li_el) -> tuple[bool, int | None]:
    pagination = False
    max_page: int | None = None
    dl = li_el.xpath(".//dl[contains(@class,'pagination')]")
    if dl:
        dt_text = (dl[0].xpath(".//dt")[0].text_content() or "").strip() if dl[0].xpath(".//dt") else ""
        m = PAGES_LABEL_PATTERN.search(dt_text)
        if m:
            max_page = int(m.group(1))
            pagination = max_page > 1
        for a in dl[0].xpath(".//a[@href]"):
            href = a.get("href") or ""
            for g in PAGE_NUM_PATTERN.finditer(href):
                for group in g.groups():
                    if group:
                        p = int(group)
                        pagination = True
                        if max_page is None or p > max_page:
                            max_page = p
    return pagination, max_page


def _parse_threadbits_from_tree(tree, base_url: str, seen_links: set[str]) -> list[ThreadItem]:
    items: list[ThreadItem] = []
    stickies = tree.xpath(THREADBIT_XPATH_STICKIES)
    normal = tree.xpath(THREADBIT_XPATH_THREADS)
    if not stickies and not normal:
        all_bits = tree.xpath(THREADBIT_XPATH_FALLBACK)
        for li in all_bits:
            _append_threadbit(items, li, base_url, seen_links, is_sticky=bool(li.xpath(".//div[contains(@class,'sticky') and not(contains(@class,'nonsticky'))]")))
        return items
    for li in stickies:
        _append_threadbit(items, li, base_url, seen_links, is_sticky=True)
    for li in normal:
        _append_threadbit(items, li, base_url, seen_links, is_sticky=False)
    return items


def _append_threadbit(
    items: list[ThreadItem],
    li,
    base_url: str,
    seen_links: set[str],
    is_sticky: bool,
) -> None:
    title_links = li.xpath(TITLE_LINK_XPATH)
    if not title_links:
        return
    main_link = title_links[0]
    href = (main_link.get("href") or "").strip()
    if not href:
        return
    full_url = ensure_wayback_url(base_url, urljoin(base_url, href))
    if full_url in seen_links:
        return
    seen_links.add(full_url)
    title = (main_link.text_content() or "").strip() or "(no title)"
    title = title[:1024] if title else "(no title)"
    replies_no = 0
    views_no = 0
    for stat_li in li.xpath(".//ul[contains(@class,'threadstats')]//li"):
        text = (stat_li.text_content() or "").strip()
        if "repl" in text.lower():
            replies_no = _parse_stat_number(text)
        if "view" in text.lower() and "repl" not in text.lower():
            views_no = _parse_stat_number(text)
    pagination, pagination_no = _pagination_from_threadbit(li)
    items.append(
        ThreadItem(
            title=title,
            link=full_url,
            replies_no=replies_no,
            views_no=views_no,
            pagination=pagination,
            is_sticky=is_sticky,
            pagination_no=pagination_no,
        )
    )


def fetch_threads(driver: WebDriver, subcategory_url: str) -> list[ThreadItem]:
    LOG.info("Fetching threads", extra={"url": subcategory_url})
    html_str = get_page_html(driver, subcategory_url)
    tree = html.fromstring(html_str, base_url=subcategory_url)
    page_urls = _thread_list_page_urls(tree, subcategory_url)
    if len(page_urls) > MAX_THREAD_LIST_PAGES:
        LOG.warning(
            "Thread list has %d pages, capping at %d",
            len(page_urls),
            MAX_THREAD_LIST_PAGES,
        )
        page_urls = page_urls[:MAX_THREAD_LIST_PAGES]
    if len(page_urls) > 1:
        LOG.info("Thread list has %d pages, fetching all", len(page_urls))
    items: list[ThreadItem] = []
    seen_links: set[str] = set()
    for page_no, page_url in enumerate(page_urls, start=1):
        if page_no > 1:
            html_str = get_page_html(driver, page_url)
            tree = html.fromstring(html_str, base_url=page_url)
        page_items = _parse_threadbits_from_tree(tree, page_url, seen_links)
        items.extend(page_items)
        if len(page_urls) > 1 and page_items:
            LOG.info("Thread list page %d/%d: %d threads (total so far: %d)", page_no, len(page_urls), len(page_items), len(items))
    if len(items) == 0:
        LOG.warning(
            "No threads found for this page (0 threadbits matched). url=%s",
            subcategory_url[:80],
        )
    else:
        titles_preview = " | ".join(i.title[:50] for i in items[:4])
        if len(items) > 4:
            titles_preview += " ..."
        LOG.info(
            "Threads parsed: %d found | %s",
            len(items),
            titles_preview or "(no titles)",
        )
    return items
