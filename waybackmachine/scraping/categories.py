import logging
from dataclasses import dataclass
from urllib.parse import urljoin

from lxml import html
from selenium.webdriver.remote.webdriver import WebDriver

from waybackmachine.config import FORUM_INDEX_URL
from waybackmachine.scraping.browser import get_page_html
from waybackmachine.scraping.urls import ensure_wayback_url

LOG = logging.getLogger(__name__)

CATEGORY_CONTAINER_XPATH = "//div[@class='tcatRight foruminfo L1 collapse']"


@dataclass
class CategoryItem:
    name: str
    link: str


def fetch_categories(driver: WebDriver, url: str = FORUM_INDEX_URL) -> list[CategoryItem]:
    LOG.info("Fetching categories", extra={"url": url})
    html_str = get_page_html(driver, url)
    tree = html.fromstring(html_str, base_url=url)
    items: list[CategoryItem] = []
    for div in tree.xpath(CATEGORY_CONTAINER_XPATH):
        anchor = div.xpath(".//a[@href][1]")
        if not anchor:
            continue
        a = anchor[0]
        href = (a.get("href") or "").strip()
        if not href:
            continue
        full_url = ensure_wayback_url(url, urljoin(url, href))
        name = (a.text_content() or "").strip() or "(no name)"
        name = name[:512] if name else "(no name)"
        items.append(CategoryItem(name=name, link=full_url))
    LOG.info("Categories parsed", extra={"count": len(items)})
    return items
