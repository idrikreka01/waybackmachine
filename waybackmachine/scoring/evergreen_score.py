import re
from datetime import datetime
from typing import Any

SCORING_VERSION = "v1"

PROBLEM_KEYWORDS = [
    "fix",
    "how to",
    "guide",
    "wiring",
    "swap",
    "upgrade",
    "troubleshooting",
    "symptoms",
    "torque specs",
    "compatibility",
    "install",
    "retrofit",
]

CATEGORY_BONUSES = [
    ("engine performance", 15),
    ("electrical", 15),
    ("transmission", 15),
    ("suspension", 12),
    ("hvac", 10),
    ("interior repair", 10),
    ("towing", 10),
    ("appearance", 0),
    ("show & shine", 0),
    ("show and shine", 0),
]

CROSS_GEN_YEAR_PATTERN = re.compile(
    r"\b(19\d{2}|20[0-2]\d)\b|'?\s*(\d{2})\s*[-–]\s*(\d{2})\b|(\d{4})\s*[-–]\s*(\d{4})"
)
CROSS_GEN_ENGINES = [
    "ls",
    "5.3",
    "6.0",
    "8.1",
    "4.8",
    "duramax",
    "4l60e",
    "4l80e",
    "4l60",
    "4l80",
    "lm7",
    "lq4",
    "lq9",
    "ls1",
    "ls2",
    "ls3",
    "ls6",
]
CROSS_GEN_UNIVERSAL = [
    r"all\s+trucks",
    r"any\s+gmt",
    r"works\s+on",
    r"\buniversal\b",
    r"across\s+years",
    r"multiple\s+years",
]
CROSS_GEN_WIRING = [r"wiring\s+diagram", r"schematic", r"pinout"]

NOISE_FOR_SALE = re.compile(r"for\s+sale|classified|wanted", re.I)
NOISE_OFFTOPIC = re.compile(r"meme|lounge|off[- ]?topic", re.I)
OPINION_PHRASES = [
    r"what\s+do\s+you\s+think",
    r"\bpoll\b",
    r"best\s+looking",
    r"show\s+me",
    r"which\s+is\s+better",
    r"\s+vs\s+",
    r"\bfavorite\b",
]


def _word_boundary_pattern(phrase: str) -> re.Pattern:
    escaped = re.escape(phrase)
    return re.compile(rf"\b{escaped}\b", re.I)


def _problem_intent_points(
    title: str | None, first_post_text: str | None
) -> tuple[int, list[str], list[str]]:
    title_matches: list[str] = []
    if title:
        for kw in PROBLEM_KEYWORDS:
            if _word_boundary_pattern(kw).search(title.lower()) and kw not in title_matches:
                title_matches.append(kw)
    first_matches: list[str] = []
    if first_post_text:
        for kw in PROBLEM_KEYWORDS:
            if (
                _word_boundary_pattern(kw).search(first_post_text.lower())
                and kw not in first_matches
            ):
                first_matches.append(kw)
    matched_keywords = list(dict.fromkeys(title_matches + first_matches))
    match_sources = []
    if title_matches:
        match_sources.append("title")
    if first_matches:
        match_sources.append("first_post")
    points = 20 if matched_keywords else 0
    return points, matched_keywords, match_sources


def _category_bonus(category_path: str, subcategory_name: str) -> tuple[int, str | None]:
    combined = f"{category_path} {subcategory_name}".lower()
    for label, points in CATEGORY_BONUSES:
        if label in combined:
            return points, label.title()
    return 0, None


def _cross_generation_signals(
    title: str | None, first_post_text: str | None
) -> tuple[bool, list[str]]:
    raw_text = f"{title or ''} {first_post_text or ''}"
    text = raw_text.lower()
    signals_matched: list[str] = []
    years: set[int] = set()
    for m in CROSS_GEN_YEAR_PATTERN.finditer(raw_text):
        for g in m.groups():
            if g:
                n = int(g)
                if len(g) == 2:
                    full_year = 2000 + n if n < 50 else 1900 + n
                    years.add(full_year)
                else:
                    years.add(n)
    if len(years) >= 2:
        signals_matched.append("multiple_years")
    engine_hits = [e for e in CROSS_GEN_ENGINES if re.search(rf"\b{re.escape(e)}\b", text)]
    if len(engine_hits) >= 2:
        signals_matched.append("engine_platform_hits")
    for pat in CROSS_GEN_UNIVERSAL:
        if re.search(pat, text):
            signals_matched.append("universal_language")
            break
    for pat in CROSS_GEN_WIRING:
        if re.search(pat, text):
            signals_matched.append("wiring_diagram")
            break
    detected = len(signals_matched) >= 1
    return detected, signals_matched


def _noise_penalties(
    category_path: str,
    subcategory_name: str,
    title: str | None,
    replies_no: int,
    problem_matched: bool,
) -> tuple[int, list[str]]:
    points = 0
    flags: list[str] = []
    combined = f"{category_path} {subcategory_name}".lower()
    if NOISE_FOR_SALE.search(combined):
        points -= 40
        flags.append("for_sale_classified")
    if NOISE_OFFTOPIC.search(combined):
        points -= 50
        flags.append("meme_lounge_offtopic")
    if replies_no <= 1:
        points -= 30
        flags.append("single_reply")
    opinion_match = title and any(re.search(p, title, re.I) for p in OPINION_PHRASES)
    if opinion_match and not problem_matched:
        points -= 25
        flags.append("opinion_thread")
    return points, flags


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z") if dt.tzinfo else dt.isoformat() + "Z"


def compute_evergreen_score(thread_context: dict) -> dict:
    thread_id = thread_context.get("thread_id", 0)
    title = thread_context.get("title") or ""
    link = thread_context.get("link") or ""
    category_path = thread_context.get("category_path") or ""
    subcategory_name = thread_context.get("subcategory_name") or ""
    is_sticky = bool(thread_context.get("is_sticky"))
    replies_no = int(thread_context.get("replies_no") or 0)
    pagination_no = thread_context.get("pagination_no")
    if pagination_no is not None:
        pagination_no = int(pagination_no)
    created_at = thread_context.get("created_at")
    last_post_at = thread_context.get("last_post_at")
    activity_span_years = int(thread_context.get("activity_span_years") or 0)
    revival_count = int(thread_context.get("revival_count") or 0)
    first_post_text = thread_context.get("first_post_text")

    sticky_points = 25 if is_sticky else 0
    if replies_no >= 250:
        reply_points = 40
    elif replies_no >= 100:
        reply_points = 30
    elif replies_no >= 50:
        reply_points = 20
    else:
        reply_points = 0

    pn = pagination_no if pagination_no is not None else 0
    if pn >= 6:
        page_points = 20
    elif pn >= 3:
        page_points = 10
    else:
        page_points = 0

    activity_span_points = 15 if activity_span_years >= 2 else 0
    revival_points = 10 if revival_count >= 3 else 0

    problem_points, matched_keywords, match_sources = _problem_intent_points(title, first_post_text)
    problem_matched = bool(matched_keywords)

    category_points, matched_category = _category_bonus(category_path, subcategory_name)

    cross_detected, cross_signals = _cross_generation_signals(title, first_post_text)
    cross_points = 20 if cross_detected else 0

    noise_points, noise_flags = _noise_penalties(
        category_path, subcategory_name, title, replies_no, problem_matched
    )

    raw_score = (
        sticky_points
        + reply_points
        + page_points
        + activity_span_points
        + revival_points
        + problem_points
        + category_points
        + cross_points
        + noise_points
    )
    final_score = max(0, min(100, raw_score))

    if final_score >= 65:
        decision = "PROMOTE"
    elif final_score >= 45:
        decision = "HOLD"
    else:
        decision = "ARCHIVE"

    breakdown: dict[str, Any] = {
        "authority": {
            "sticky_points": sticky_points,
            "reply_points": reply_points,
            "page_points": page_points,
            "activity_span_points": activity_span_points,
            "revival_points": revival_points,
        },
        "problem_intent": {
            "points": problem_points,
            "matched_keywords": matched_keywords,
            "match_sources": match_sources,
        },
        "category_bonus": {
            "points": category_points,
            "matched_category": matched_category,
        },
        "cross_generation": {
            "points": cross_points,
            "detected": cross_detected,
            "signals_matched": cross_signals,
        },
        "noise": {
            "points": noise_points,
            "flags": noise_flags,
        },
    }

    return {
        "scoring_version": SCORING_VERSION,
        "thread": {
            "thread_id": thread_id,
            "title": title,
            "link": link,
            "category_path": category_path,
            "subcategory_name": subcategory_name,
            "is_sticky": is_sticky,
            "replies_no": replies_no,
            "pagination_no": pagination_no,
            "created_at": _to_iso(created_at),
            "last_post_at": _to_iso(last_post_at),
            "activity_span_years": activity_span_years,
            "revival_count": revival_count,
        },
        "score": {
            "raw": raw_score,
            "final": final_score,
            "decision": decision,
        },
        "breakdown": breakdown,
    }
