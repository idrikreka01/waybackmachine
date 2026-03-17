import os
import sys
import time
from typing import Dict, Any, Optional, List

import requests
from waybackmachine.db.models import Thread, ThreadEvergreenScore, Post
from waybackmachine.db.session import get_session_factory


def _normalize_tags(tags: List[str]) -> List[str]:
    cleaned = [t.strip().lower() for t in tags if t and t.strip()]
    return list(dict.fromkeys(cleaned))


def ensure_tags_exist(
    base_url: str,
    headers: Dict[str, str],
    tags: List[str],
) -> None:
    """
    Ensure tags exist on the Discourse instance.

    Uses the admin "Upload Tags" endpoint /tags/upload.json (admin-only).
    This is safe to call repeatedly; existing tags are not duplicated.
    """
    tags = _normalize_tags(tags)
    if not tags:
        return

    url = base_url.rstrip("/") + "/tags/upload.json"
    payload = "\n".join(tags) + "\n"
    files = {"file": ("tags.txt", payload.encode("utf-8"), "text/plain")}
    resp = requests.post(url, headers=headers, files=files, timeout=30)
    try:
        resp.raise_for_status()
    except Exception:
        print(
            "Error response from Discourse (tags/upload):",
            resp.status_code,
            resp.text[:500],
            file=sys.stderr,
        )
        raise
CATEGORY_BY_ID = {
    3: "Staff",
    4: "Welcome to FSC",
    6: "New Member Check-In",
    8: "Show Us Your Truck!",
    9: "FSC Giveaways",
    10: "FSC Announcements",
    11: "FullSize Feature / Truck of The Month (TOTM)",
    12: "Forum Rules & FAQ",
    20: "GMT400 (1988–1998) – OBS Discussions",
    21: "Interior (GMT400)",
    22: "Exterior (GMT400)",
    23: "Suspension, Wheels & Tires (GMT400)",
    25: "Performance, Mods & Tuning (GMT400)",
    26: "Stereo, Wiring & Electronics (GMT400)",
    28: "GMT800 (1999–2006) – NBS Discussions",
    29: "Interior (GMT800)",
    30: "Exterior (GMT800)",
    31: "Suspension, Wheels & Tires (GMT800)",
    33: "Performance, Mods & Tuning (GMT800)",
    34: "Stereo, Wiring & Electronics (GMT800)",
    36: "GMT900 (2007–2013) – NNBS Discussions",
    37: "Interior (GMT900)",
    38: "Exterior (GMT900)",
    39: "Suspension, Wheels & Tires (GMT900)",
    41: "Performance, Mods & Tuning (GMT900)",
    42: "Stereo, Wiring & Electronics (GMT900)",
    44: "K2XX (2014–2018) Discussions",
    45: "Interior (K2XX)",
    46: "Exterior (K2XX)",
    47: "Suspension, Wheels & Tires (K2XX)",
    49: "Performance, Mods & Tuning (K2XX)",
    50: "Stereo, Wiring & Electronics (K2XX)",
    52: "T1XX (2019 & Beyond) + EVs",
    53: "Interior (T1XX)",
    54: "Exterior (T1XX)",
    55: "Suspension, Wheels & Tires (T1XX)",
    57: "Performance, Mods & Tuning (T1XX)",
    58: "Stereo, Wiring & Electronics (T1XX)",
    60: "Community & Off Topic",
    61: "Shop Talk (Garage Life)",
    62: "Smoking Tavern (Lounge)",
    63: "Meetups & Events",
    64: "Suggestions & Site Feedback",
    65: "Diesel Tech & Duramax Discussion",
    66: "Duramax 2001–Present",
    67: "General Truck Discussion",
    70: "Towing, Hauling & Work Rigs",
    71: "Detailing",
    72: "Parts & Accessories",
    74: "LB7 / LLY / LBZ / LMM",
    75: "LML / L5P",
    76: "Diesel Tuning & Emissions",
    77: "Transmissions (Allison Focused)",
    79: "Electrical & Wiring",
    80: "Lighting & Accessories",
    81: "FSC Vendor Marketplace",
    82: "How to Become a Vendor",
    83: "Buy, Sell, Trade",
    84: "Trucks for Sale",
    85: "Parts & Accessories (BST)",
    86: "Wanted to Buy",
    88: "Audio, Video & Lighting",
    89: "Car Audio & Video Systems",
    90: "Head Units & Infotainment",
    91: "Speakers, Subs & Amps",
    92: "Backup Cameras & Displays",
    93: "Interior Electronics",
    94: "Builds & Projects",
    95: "In Progress",
    96: "Completed Builds",
    97: "Classic Chevy Trucks (1947–1972)",
    98: "6.2L / 6.5L Detroit Diesel (1982–2000)",
    99: "Technical & Maintenance (Squarebody)",
    100: "Technical & Maintenance (GMT400)",
    101: "Technical & Maintenance (GMT800)",
    102: "Technical & Maintenance (Classic)",
    103: "Technical & Maintenance (GMT900)",
    104: "Technical & Maintenance (K2XX)",
    105: "Technical & Maintenance (T1XX)",
    106: "FSC Merchandise",
    107: "AuigBelle Performance",
    108: "Interior (Classic 47–72)",
    109: "Exterior (Classic 47–72)",
    110: "Suspension, Wheels & Tires (Classic 47–72)",
    111: "Performance, Mods & Tuning (Classic 47–72)",
    112: "Stereo, Wiring & Electronics (Classic 47–72)",
    114: "General Lighting",
    115: "Technical & Maintenance (General)",
    116: "Suspension, Wheels & Tires (General)",
    117: "Performance, Mods & Tuning (General)",
}

def get_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is required.")
    return value


def build_headers() -> Dict[str, str]:
    api_key = get_env("DISCOURSE_API_KEY")
    api_user = get_env("DISCOURSE_API_USERNAME")
    return {
        "Api-Key": api_key,
        "Api-Username": api_user,
    }


def create_topic(
    base_url: str,
    headers: Dict[str, str],
    title: str,
    body: str,
    category_id: int,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/posts.json"

    # Use list-of-tuples so requests sends repeated tags[] fields
    data: List[tuple[str, Any]] = [
        ("title", title),
        ("raw", body),
        ("category", str(category_id)),
    ]
    if tags:
        for t in tags:
            data.append(("tags[]", t))

    resp = requests.post(url, headers=headers, data=data, timeout=30)
    try:
        resp.raise_for_status()
    except Exception:
        print("Error response from Discourse:", resp.status_code, resp.text[:500], file=sys.stderr)
        raise
    return resp.json()


def create_reply(
    base_url: str,
    headers: Dict[str, str],
    topic_id: int,
    body: str,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/posts.json"
    data: Dict[str, Any] = {
        "topic_id": topic_id,
        "raw": body,
    }
    resp = requests.post(url, headers=headers, data=data, timeout=30)
    try:
        resp.raise_for_status()
    except Exception:
        print("Error response from Discourse (reply):", resp.status_code, resp.text[:500], file=sys.stderr)
        raise
    return resp.json()


def pick_first_row(csv_path: str) -> Dict[str, str]:
    raise RuntimeError(f"pick_first_row is no longer used (DB-only version).")


def load_posts_for_thread(thread_id: str, csv_path: str) -> List[Dict[str, str]]:
    raise RuntimeError("load_posts_for_thread is no longer used (DB-only version).")


def strip_html_to_text(html: Optional[str]) -> str:
    if not html:
        return ""
    import re

    # First, replace anchors with their href so we keep full URLs instead of truncated link text.
    def _anchor_to_href(match: re.Match) -> str:
        href = match.group(1) or ""
        return href

    text = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>.*?</a>', _anchor_to_href, html, flags=re.I | re.S)
    # Then strip the remaining HTML tags.
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def main() -> None:
    """
    Pick the highest-scoring PROMOTE thread from the DB and:
    create a Discourse topic with the thread-level AI article as a single post.
    """
    base_url = get_env("DISCOURSE_BASE_URL")

    factory = get_session_factory()
    session = factory()
    try:
        # Pick highest-score PROMOTE thread with AI post rewrites.
        score_row: Optional[ThreadEvergreenScore] = (
            session.query(ThreadEvergreenScore)
            .filter(
                ThreadEvergreenScore.decision == "PROMOTE",
                ThreadEvergreenScore.ai_post_rewrites_json.isnot(None),
            )
            .order_by(ThreadEvergreenScore.final_score.desc())
            .first()
        )
        if score_row is None:
            raise RuntimeError("No PROMOTE threads with AI post rewrites found in DB.")

        thread: Optional[Thread] = (
            session.query(Thread)
            .filter(Thread.id == score_row.thread_id)
            .first()
        )
        if thread is None:
            raise RuntimeError(f"Thread id={score_row.thread_id} not found.")

        thread_id_str = str(thread.id)

        import json

        # Prefer full thread-level AI article when available.
        body = ""
        if score_row.ai_article_json:
            try:
                article = json.loads(score_row.ai_article_json)
            except Exception:
                article = None
            if isinstance(article, dict):
                body = (article.get("rewritten_article_markdown") or "").strip()

        # Fallback: synthesize from original posts if needed.
        if not body.strip():
            posts: List[Post] = (
                session.query(Post)
                .filter(Post.thread_id == thread.id)
                .order_by(Post.post_page_id.asc().nullsfirst(), Post.id.asc())
                .all()
            )
            if not posts:
                raise RuntimeError(f"No posts found for thread_id={thread.id}")
            parts: List[str] = []
            for p in posts:
                text = strip_html_to_text(p.post_content or "")
                if not text:
                    continue
                # Drop quoting boilerplate like "Originally Posted by <user>"
                lines = []
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.lower().startswith("originally posted by "):
                        continue
                    lines.append(line)
                cleaned = "\n".join(lines).strip()
                if cleaned:
                    parts.append(cleaned)
            body = "\n\n".join(parts).strip()

        if not body.strip():
            raise RuntimeError("Thread has no article or post text to create topic body.")

        title = thread.title or "Imported topic"

        # Tags: derive from score_row.result_json if present.
        tags: List[str] = []
        try:
            result_payload = json.loads(score_row.result_json)
            tags_raw = (result_payload.get("tags") or [])
            if isinstance(tags_raw, list):
                tags = [str(t).strip() for t in tags_raw if str(t).strip()]
        except Exception:
            tags = []
        tags = _normalize_tags(tags)

        forum_main = score_row.forum_main or ""
        derived_category_id: Optional[int] = None
        if forum_main:
            for cid, name in CATEGORY_BY_ID.items():
                if name == forum_main:
                    derived_category_id = cid
                    break

        if derived_category_id is None:
            category_id_str = get_env("DISCOURSE_CATEGORY_ID")
            try:
                derived_category_id = int(category_id_str)
            except ValueError:
                raise RuntimeError("DISCOURSE_CATEGORY_ID must be an integer.")

        print("Using DB thread for topic:")
        print("  thread_id:", thread_id_str)
        print("  title:", title)
        print("  forum_main:", forum_main)
        print("  mapped_category_id:", derived_category_id)
        print("  tags:", tags)

        headers = build_headers()
        if tags:
            ensure_tags_exist(base_url=base_url, headers=headers, tags=tags)

        try:
            result = create_topic(
                base_url=base_url,
                headers=headers,
                title=title,
                body=body,
                category_id=derived_category_id,
                tags=tags if tags else None,
            )
        except requests.exceptions.HTTPError:
            if tags:
                print(
                    "Topic creation failed with tags; retrying without tags.",
                    file=sys.stderr,
                )
                result = create_topic(
                    base_url=base_url,
                    headers=headers,
                    title=title,
                    body=body,
                    category_id=derived_category_id,
                    tags=None,
                )
            else:
                raise

        topic_id = int(result.get("topic_id"))
        first_post_id = int(result.get("id"))
        print("Created Discourse topic.")
        print("  topic_id:", topic_id)
        print("  first_post_id:", first_post_id)

        # No replies: client wants one consolidated post per thread.
    finally:
        session.close()


if __name__ == "__main__":
    main()