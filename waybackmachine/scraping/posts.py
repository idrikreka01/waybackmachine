import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime

from lxml import etree, html
from selenium.webdriver.remote.webdriver import WebDriver

from waybackmachine.scraping.browser import get_page_html

LOG = logging.getLogger(__name__)

POST_ITEM_XPATH = "//ol[@id='posts']/li[contains(@class,'postbitlegacy')]"
POSTCOUNTER_XPATH = ".//a[contains(@class,'postcounter')]"
DATE_XPATH = ".//div[contains(@class,'posthead')]//span[@class='date']"
USERNAME_XPATH = ".//div[contains(@class,'username_container')]//a[contains(@class,'username')]"
USERTITLE_XPATH = ".//span[@class='usertitle']"
POST_CONTENT_XPATH = ".//div[contains(@class,'postbody')]//div[starts-with(@id,'post_message_')]"


@dataclass
class PostItem:
    user_username: str | None
    user_joindate: str | None
    user_location: str | None
    user_posts: int | None
    user_register: bool
    user_age: int | None
    post_date_time: datetime | None
    post_content: str | None
    post_page_id: int | None
    post_counter: str | None


def _parse_post_date(text: str) -> datetime | None:
    if not text:
        return None
    text = text.strip().replace("\xa0", " ").replace("\u00a0", " ")
    try:
        return datetime.strptime(text, "%m-%d-%Y, %I:%M %p")
    except ValueError:
        try:
            return datetime.strptime(text, "%m-%d-%Y,&nbsp;%I:%M %p".replace("&nbsp;", " "))
        except ValueError:
            return None


def _parse_int_from_text(text: str) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None


def _dd_for_dt(li_el, dt_text: str) -> str | None:
    for dt in li_el.xpath(".//dl[@class='userinfo_extra']/dt"):
        if (dt.text or "").strip() == dt_text:
            dd = dt.getnext()
            if dd is not None and dd.tag == "dd":
                return (dd.text or "").strip() or None
    return None


def fetch_posts(driver: WebDriver, thread_url: str) -> list[PostItem]:
    LOG.info("Fetching posts: %s", thread_url[:80] + "..." if len(thread_url) > 80 else thread_url)
    html_str = get_page_html(driver, thread_url)
    tree = html.fromstring(html_str, base_url=thread_url)
    items: list[PostItem] = []
    for li in tree.xpath(POST_ITEM_XPATH):
        post_page_id = None
        post_counter = None
        postcounter = li.xpath(POSTCOUNTER_XPATH)
        if postcounter:
            raw = (postcounter[0].text_content() or "").strip()
            post_counter = raw[:32] if raw else None
            post_page_id = _parse_int_from_text(raw)

        date_el = li.xpath(DATE_XPATH)
        post_date_time = None
        if date_el:
            post_date_time = _parse_post_date(date_el[0].text_content() or "")

        user_username = None
        username_el = li.xpath(USERNAME_XPATH)
        if username_el:
            user_username = (username_el[0].text_content() or "").strip()[:255] or None

        user_register = False
        usertitle_el = li.xpath(USERTITLE_XPATH)
        if usertitle_el:
            title_text = (usertitle_el[0].text_content() or "").strip().lower()
            user_register = "registered user" in title_text or "registered" in title_text

        user_joindate = _dd_for_dt(li, "Join Date")
        if user_joindate:
            user_joindate = user_joindate[:255]
        user_location = _dd_for_dt(li, "Location")
        if user_location:
            user_location = user_location[:512]
        user_posts = None
        posts_dd = _dd_for_dt(li, "Posts")
        if posts_dd:
            user_posts = _parse_int_from_text(posts_dd)

        user_age = None
        age_dd = _dd_for_dt(li, "Age")
        if age_dd:
            user_age = _parse_int_from_text(age_dd)

        post_content = None
        content_el = li.xpath(POST_CONTENT_XPATH)
        if content_el:
            el = content_el[0]
            inner_parts = [
                etree.tostring(c, encoding="unicode", method="html") for c in el
            ]
            raw = "".join(inner_parts).strip()
            post_content = raw[:500000] if raw else None

        items.append(
            PostItem(
                user_username=user_username,
                user_joindate=user_joindate,
                user_location=user_location,
                user_posts=user_posts,
                user_register=user_register,
                user_age=user_age,
                post_date_time=post_date_time,
                post_content=post_content,
                post_page_id=post_page_id,
                post_counter=post_counter,
            )
        )
    LOG.info("Posts parsed: %d from thread | %s", len(items), thread_url[:70] + "..." if len(thread_url) > 70 else thread_url)
    return items


if __name__ == "__main__":
    from waybackmachine.scraping.browser import create_driver

    default_url = (
        "https://web.archive.org/web/20160408164426/http://www.fullsizechevy.com/forum/"
        "general-discussion/technical-maintenance/213662-96-99-454-vortec-owners-564.html"
    )
    url = sys.argv[1] if len(sys.argv) > 1 else default_url
    driver = create_driver()
    try:
        items = fetch_posts(driver, url)
        out = json.dumps(
            [asdict(i) for i in items],
            indent=2,
            default=str,
        )
        print(f"Fetched {len(items)} posts. Full JSON written to posts_test_result.json")
        with open("posts_test_result.json", "w", encoding="utf-8") as f:
            f.write(out)
    finally:
        driver.quit()
