import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from lxml import html
from selenium.webdriver.remote.webdriver import WebDriver

from waybackmachine.scraping.browser import get_page_html
from waybackmachine.scraping.urls import ensure_wayback_url

LOG = logging.getLogger(__name__)

FORUMROW_XPATH = "//div[contains(@class,'forumrow')]"
TITLE_LINK_XPATH = ".//h2[@class='forumtitle']/a"
DESCRIPTION_XPATH = ".//p[@class='forumdescription']"
STATS_XPATH = ".//ul[contains(@class,'forumstats')]//li"


@dataclass
class SubcategoryItem:
    name: str
    link: str
    description: str | None
    threads_no: int
    posts_no: int


def _parse_stat_number(text: str) -> int:
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else 0


def fetch_subcategories(driver: WebDriver, category_url: str) -> list[SubcategoryItem]:
    LOG.info("Fetching subcategories", extra={"url": category_url})
    html_str = get_page_html(driver, category_url)
    tree = html.fromstring(html_str, base_url=category_url)
    items: list[SubcategoryItem] = []
    for div in tree.xpath(FORUMROW_XPATH):
        title_anchor = div.xpath(TITLE_LINK_XPATH)
        if not title_anchor:
            continue
        a = title_anchor[0]
        href = (a.get("href") or "").strip()
        if not href:
            continue
        full_url = ensure_wayback_url(category_url, urljoin(category_url, href))
        name = (a.text_content() or "").strip() or "(no name)"
        name = name[:512] if name else "(no name)"
        desc_el = div.xpath(DESCRIPTION_XPATH)
        description = (desc_el[0].text_content() or "").strip() if desc_el else None
        if description == "":
            description = None
        threads_no = 0
        posts_no = 0
        for li in div.xpath(STATS_XPATH):
            text = (li.text_content() or "").strip()
            if text.startswith("Threads:"):
                threads_no = _parse_stat_number(text)
            elif text.startswith("Posts:"):
                posts_no = _parse_stat_number(text)
        items.append(
            SubcategoryItem(
                name=name,
                link=full_url,
                description=description or None,
                threads_no=threads_no,
                posts_no=posts_no,
            )
        )
        LOG.info("Found subcategory: %s (threads=%s, posts=%s)", name, threads_no, posts_no)
    names_preview = ", ".join(i.name[:40] for i in items[:5])
    if len(items) > 5:
        names_preview += ", ..."
    LOG.info(
        "Subcategories parsed: %d total for url | %s",
        len(items),
        names_preview or "(none)",
    )
    return items
