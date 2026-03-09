import re
from urllib.parse import urljoin

WAYBACK_PREFIX_PATTERN = re.compile(
    r"^(https?://web\.archive\.org/web/)(\d{14})(/)(.*)$", re.IGNORECASE
)


def ensure_wayback_url(current_page_url: str, link: str) -> str:
    if not link or not current_page_url:
        return link
    link = link.strip()
    if link.startswith("https://web.archive.org/") or link.startswith(
        "http://web.archive.org/"
    ):
        return link
    m = WAYBACK_PREFIX_PATTERN.match(current_page_url)
    if not m:
        return urljoin(current_page_url, link)
    prefix, timestamp, slash, original_base = m.groups()
    if not original_base:
        original_base = ""
    if link.startswith("http://") or link.startswith("https://"):
        full_original = link
    else:
        full_original = urljoin(original_base, link)
    return f"{prefix}{timestamp}{slash}{full_original}"
