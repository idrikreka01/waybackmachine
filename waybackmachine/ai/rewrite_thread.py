import argparse
import json
import logging
import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any
from urllib import request

from sqlalchemy.orm import joinedload

from waybackmachine.config import REQUEST_TIMEOUT
from waybackmachine.db.models import Thread, ThreadEvergreenScore
from waybackmachine.db.session import get_session_factory
from waybackmachine.logging_config import configure_logging

LOG = logging.getLogger(__name__)

_SUSPICIOUS_WORD_PATTERNS: tuple[tuple[str, str], ...] = (
    ("gpu", "Possible misread of 'gp' (group purchase) as GPU."),
)


def _get_ollama_url() -> str:
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    return base.rstrip("/") + "/api/generate"


def _pick_promote_thread(session, thread_id: int | None = None) -> Thread:
    if thread_id is not None:
        row = (
            session.query(ThreadEvergreenScore)
            .filter(
                ThreadEvergreenScore.thread_id == thread_id,
                ThreadEvergreenScore.decision == "PROMOTE",
            )
            .first()
        )
        if row is None:
            raise ValueError(f"Thread {thread_id} is not scored as PROMOTE.")
    else:
        row = (
            session.query(ThreadEvergreenScore)
            .filter(ThreadEvergreenScore.decision == "PROMOTE")
            .order_by(ThreadEvergreenScore.final_score.desc())
            .first()
        )
        if row is None:
            raise ValueError("No PROMOTE threads found in thread_evergreen_score.")
        thread_id = row.thread_id

    thread = (
        session.query(Thread)
        .options(
            joinedload(Thread.subcategory),
            joinedload(Thread.posts),
        )
        .filter(Thread.id == thread_id)
        .first()
    )
    if thread is None:
        raise ValueError(f"Thread {thread_id} not found.")
    return thread


def _thread_to_payload(thread: Thread) -> dict[str, Any]:
    subcat = getattr(thread, "subcategory", None)
    category = getattr(subcat, "category", None) if subcat is not None else None
    category_path = ""
    if category is not None and subcat is not None:
        category_path = f"{category.name} > {subcat.name}"
    elif subcat is not None:
        category_path = subcat.name

    posts = sorted(
        getattr(thread, "posts", []),
        key=lambda p: (p.post_date_time or datetime.min, p.id),
    )
    post_items: list[dict[str, Any]] = []
    for p in posts:
        html = p.post_content or ""
        plain = _html_to_plain(html)
        post_items.append(
            {
                "id": p.id,
                "post_date_time": p.post_date_time.isoformat() if p.post_date_time else None,
                "user_username": p.user_username,
                "post_content_html": html,
                "post_content_plain": plain,
            }
        )

    first_post_html = post_items[0]["post_content_html"] if post_items else None

    return {
        "thread_id": thread.id,
        "title": thread.title,
        "url": thread.link,
        "category_path": category_path,
        "replies_no": thread.replies_no,
        "pagination": thread.pagination,
        "pagination_no": thread.pagination_no,
        "is_sticky": thread.is_sticky,
        "first_post_html": first_post_html,
        "posts": post_items,
    }


def _html_to_plain(html: str) -> str:
    if not html or not html.strip():
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _call_ollama_text(prompt: str, model: str) -> str:
    body = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.1}}
    data = json.dumps(body).encode("utf-8")
    url = _get_ollama_url()
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return (payload.get("response") or "").strip()


def _tokenize_simple(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _extract_word_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def _best_substring_match(article: str, excerpt: str) -> str | None:
    ex = excerpt.strip()
    art = article
    if not ex or not art:
        return None
    spans = _extract_word_spans(art)
    if not spans:
        return None

    norm_ex = _normalize_text(ex)
    ex_tokens = norm_ex.split()
    if not ex_tokens:
        return None

    target = len(ex_tokens)
    min_w = max(4, int(target * 0.70))
    max_w = min(len(spans), int(target * 1.30) + 2)

    best_ratio = 0.0
    best_sub: str | None = None

    # Sliding token window over the article text, reconstructing exact substrings.
    for w in range(min_w, max_w + 1):
        for i in range(0, len(spans) - w + 1):
            start = spans[i][0]
            end = spans[i + w - 1][1]
            sub = art[start:end].strip()
            if len(sub) < 24:
                continue
            ratio = SequenceMatcher(None, norm_ex, _normalize_text(sub)).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_sub = sub
            if ratio >= 0.94:
                return sub

    if best_ratio >= 0.92:
        return best_sub
    return None


def _repair_evidence_excerpts(thread_payload: dict[str, Any], rewrite: dict[str, Any]) -> dict[str, Any]:
    article = rewrite.get("rewritten_article_markdown")
    evidence = rewrite.get("evidence")
    if not isinstance(article, str) or not article.strip():
        return rewrite
    if not isinstance(evidence, list) or not evidence:
        return rewrite

    thread_plain = " ".join((p.get("post_content_plain") or "") for p in thread_payload.get("posts", []))

    changed = False
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        ex = ev.get("article_excerpt")
        if not isinstance(ex, str) or not ex.strip():
            continue
        if ex in article:
            continue
        snapped = _best_substring_match(article, ex)
        if not snapped:
            continue
        if _is_likely_source_quote(snapped, thread_plain):
            continue
        ev["article_excerpt"] = snapped
        changed = True

    if changed:
        rewrite["evidence"] = evidence
    return rewrite


def _detect_suspicious_article_content(thread_payload: dict[str, Any], rewrite: dict[str, Any]) -> list[str]:
    article = rewrite.get("rewritten_article_markdown")
    if not isinstance(article, str) or not article.strip():
        return ["Empty rewritten_article_markdown."]

    thread_plain = " ".join((p.get("post_content_plain") or "") for p in thread_payload.get("posts", []))
    t = _normalize_text(thread_plain)
    a = _normalize_text(article)

    issues: list[str] = []
    for needle, reason in _SUSPICIOUS_WORD_PATTERNS:
        if needle in a and needle not in t:
            issues.append(reason)

    # Common range formatting hallucination: "$4-500" becomes "$4,500".
    if "$4,500" in article and ("$4-500" in thread_plain or "4-500" in thread_plain):
        issues.append("Suspicious price normalization: '$4-500' became '$4,500'.")

    # Another common drift: 'more' becoming 'rare' (meaning flip).
    if " rare " in f" {a} " and " rare " not in f" {t} " and " more " in f" {t} ":
        issues.append("Suspicious meaning drift: 'more' possibly rewritten as 'rare'.")

    return issues


def _assert_publish_ready(thread_payload: dict[str, Any], rewrite: dict[str, Any]) -> None:
    article = (rewrite.get("rewritten_article_markdown") or "").strip()
    if "@" in article:
        raise ValueError("Publish-ready check failed: article contains '@' mentions.")
    issues = _detect_suspicious_article_content(thread_payload, rewrite)
    if issues:
        raise ValueError("Publish-ready check failed: " + "; ".join(issues))
    _validate_rewrite(thread_payload, rewrite)


def rewrite_post(post_html: str, model: str) -> str:
    plain = _html_to_plain(post_html)
    if not plain:
        return ""
    if len(plain) > 4000:
        plain = plain[:4000] + "..."
    prompt = (
        "Rewrite this forum post into clean, modern prose. Keep the same meaning and "
        "technical content. Remove casual filler, fix grammar, keep it concise. "
        "Do not add new facts. Output only the rewritten text, no quotes or preamble.\n\n"
        "Original post:\n" + plain
    )
    rewritten = _call_ollama_text(prompt, model=model)
    src = plain.strip()
    dst = (rewritten or "").strip()
    if len(src) <= 32 and dst:
        src_tokens = set(_tokenize_simple(src))
        dst_tokens = set(_tokenize_simple(dst))
        novel = [t for t in dst_tokens if t not in src_tokens]
        # Allow trivial grammar glue words; reject obvious nouny expansions.
        glue = {
            "i",
            "im",
            "i'm",
            "in",
            "this",
            "that",
            "it",
            "is",
            "was",
            "be",
            "would",
            "buy",
            "awesome",
            "thanks",
            "thank",
            "you",
            "yes",
            "no",
            "more",
        }
        if any(t not in glue and len(t) >= 4 for t in novel):
            raise ValueError("Suspicious short-post rewrite expansion; refusing rewrite_post output.")
    return rewritten


def _normalize_text(value: str) -> str:
    """
    Normalize text for approximate matching:
    - lowercase
    - strip backticks/quotes
    - collapse all whitespace
    """
    value = value.lower()
    value = re.sub(r"[`\"']", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _excerpt_in_article(excerpt: str, article: str) -> bool:
    """
    Best-effort grounding check:
    - First, require normalize(excerpt) to be a substring of normalize(article)
      when possible.
    - If that fails, use a fuzzy SequenceMatcher-based window search and accept
      when similarity >= 0.92.
    """
    norm_ex = _normalize_text(excerpt)
    norm_article = _normalize_text(article)
    if not norm_ex:
        return False
    if norm_ex in norm_article:
        return True

    # Fuzzy fallback: sliding window with SequenceMatcher
    ex_tokens = norm_ex.split()
    art_tokens = norm_article.split()
    if not ex_tokens or not art_tokens:
        return False

    window = min(len(ex_tokens), len(art_tokens))

    best_ratio = 0.0
    for i in range(0, len(art_tokens) - window + 1):
        window_text = " ".join(art_tokens[i : i + window])
        ratio = SequenceMatcher(None, norm_ex, window_text).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
        if ratio >= 0.90:
            return True
    LOG.debug("Best excerpt/article similarity ratio: %.3f", best_ratio)
    return False


def _is_likely_source_quote(excerpt: str, source_text: str) -> bool:
    ex = excerpt.strip()
    if len(ex) < 80:
        return False
    norm_ex = _normalize_text(ex)
    if not norm_ex:
        return False
    norm_src = _normalize_text(source_text)
    return norm_ex in norm_src


def _build_prompt(thread_payload: dict[str, Any]) -> str:
    instructions = (
        "You are a senior automotive editor rewriting one archived forum thread.\n"
        "\n"
        "You will receive THREAD_DATA as JSON.\n"
        "\n"
        "PRIMARY GOAL:\n"
        "Rewrite the whole thread into one modern, readable, but faithful article suitable for editorial review and later posting.\n"
        "Faithfulness is more important than polish.\n"
        "The article should be fuller than a thin summary: keep important thread-specific technical details when clearly supported.\n"
        "Write in a clean, search-friendly style without marketing language.\n"
        "\n"
        "HARD RULES:\n"
        "- Rewrite the whole thread, not each post separately.\n"
        "- Output one JSON object only.\n"
        "- Do not output an array of rewritten posts.\n"
        "- Use only information explicitly stated in THREAD_DATA.posts.\n"
        "- Do not add facts, assumptions, advice, motivations, warnings, steps, requirements, or conclusions that are not explicitly stated.\n"
        "- Do not turn forum opinions into facts.\n"
        "- Do not make technical claims stronger or cleaner than they are in the thread.\n"
        "- If a point comes from one side of a disagreement, attribute it clearly in the article, for example: 'one reply argues...', 'another estimates...'.\n"
        "- Keep short forum replies short, for example: 'I'm in', 'this would be awesome', 'I'd buy it'.\n"
        "- Keep the technical focus of the thread (do not drift into unrelated systems/categories).\n"
        "- De-duplicate repeated replies, but do not remove meaningful disagreement.\n"
        "- If the thread uses slang that is obvious from context, keep the intended meaning. Example: 'horses' means horsepower.\n"
        "- Preserve shorthand meaning when supported: 'gp' can mean group purchase; do not expand abbreviations unless clearly supported.\n"
        "- Preserve numeric ranges as ranges (example: '$4-500' is a range; do not convert it into '$4,500').\n"
        "- If a statement cannot be supported by one or more post_ids from THREAD_DATA.posts, do not include it.\n"
        "- Do not invent context for links.\n"
        "- Avoid usernames/@mentions in the article unless truly necessary for clarity.\n"
        "- Do not insert citations or post ids into the article text.\n"
        "- Do not output per-post rewrites.\n"
        "- Output valid JSON only.\n"
        "\n"
        "BANNED PHRASES IN rewritten_article_markdown unless directly supported by the thread:\n"
        "- generally\n"
        "- typically\n"
        "- usually\n"
        "- recommended\n"
        "- might require\n"
        "- with a few modifications\n"
        "- research indicates\n"
        "\n"
        "IMPORTANT WRITING RULE:\n"
        "If the thread is messy, the rewrite may still be slightly messy.\n"
        "Do not fill missing gaps just to make the article feel complete.\n"
        "Only write what the thread actually says.\n"
        "\n"
        "OUTPUT JSON MUST HAVE EXACTLY THESE KEYS:\n"
        "- rewritten_title: string\n"
        "- summary: string\n"
        "- seo_outline: array of strings\n"
        "- rewritten_article_markdown: string\n"
        "- evidence: array of objects with EXACT keys:\n"
        "    - article_excerpt: string\n"
        "    - post_ids: array of integers\n"
        "    - certainty: 'certain' | 'uncertain'\n"
        "    - source_excerpt: string\n"
        "- notes: string\n"
        "\n"
        "RULES FOR rewritten_article_markdown:\n"
        "- Use short headings and short paragraphs.\n"
        "- Include only sections that are clearly supported by the thread.\n"
        "- A section may be very short.\n"
        "- Do not add filler just to complete a section.\n"
        "- Do not over-compress central technical details; preserve important specifics supported by the thread.\n"
        "- Capture repeated demand patterns briefly (bolt-on, plug-and-play, avoiding fabrication, willingness to pay for convenience) when supported.\n"
        "- Preserve this general order when supported by the thread:\n"
        "  1) Core proposal\n"
        "  2) Why people want it\n"
        "  3) Proposed kit contents / approach\n"
        "  4) Cost debate\n"
        "  5) Alternatives discussed\n"
        "  6) Real-world example(s) referenced\n"
        "  7) Community response\n"
        "\n"
        "RULES FOR evidence:\n"
        "- article_excerpt must be an exact substring copied from rewritten_article_markdown.\n"
        "- Do not copy article_excerpt from THREAD_DATA source posts.\n"
        "- article_excerpt must match the wording of the final article, not the wording of the original posts.\n"
        "- Evidence should cover the important sections of the article, not just a few lines.\n"
        "- Each major technical paragraph or meaningful bullet should have evidence.\n"
        "- If a section contains multiple meaningful technical claims, use multiple evidence entries.\n"
        "- Every technical sentence or bullet in rewritten_article_markdown must have at least one matching evidence entry.\n"
        "- If two sides disagree, include both sides in the article and cite each side with the relevant post_ids.\n"
        "- Use certainty='uncertain' only when the thread contains disagreement, partial information, or unresolved uncertainty.\n"
        "- source_excerpt should be short and copied from the source post text when possible.\n"
        "\n"
        "RULES FOR notes:\n"
        "- Use notes only for real uncertainty, disagreement, or intentionally omitted unsupported material.\n"
        "- Do not repeat facts already stated clearly in the article.\n"
    )
    thread_json = json.dumps(thread_payload, ensure_ascii=False)
    return instructions + "\n\nTHREAD_DATA:\n" + thread_json


def _call_ollama(prompt: str, model: str) -> dict[str, Any]:
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
    }
    data = json.dumps(body).encode("utf-8")
    url = _get_ollama_url()
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    response_text = payload.get("response", "")
    raw = response_text.strip()
    # Try simple case first
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError(
                    "Model must return one JSON object (not an array) for thread-level rewrite."
                )
            return parsed
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Model returned invalid JSON: {raw[:200]}") from exc

    # Attempt to extract the first JSON object from free-form text
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = raw[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if not isinstance(parsed, dict):
                raise ValueError(
                    "Model must return one JSON object (not an array) for thread-level rewrite."
                )
            return parsed
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model returned non-JSON response: {raw[:200]}") from exc

    raise ValueError(f"Model did not return JSON: {raw[:200]}")


def _build_finalizer_prompt(thread_payload: dict[str, Any], rewrite: dict[str, Any]) -> str:
    instructions = (
        "You are preparing a Discourse-ready editorial draft from an already rewritten automotive forum thread.\n"
        "\n"
        "You will receive:\n"
        "- THREAD_DATA as JSON\n"
        "- REWRITE_DRAFT as JSON\n"
        "\n"
        "Your job:\n"
        "Improve the thread-level article so it is cleaner, more natural, and safer to post after human review.\n"
        "\n"
        "Rules:\n"
        "- Keep the meaning faithful to the original thread.\n"
        "- Use only information supported by THREAD_DATA.posts.\n"
        "- Do not add new facts, advice, warnings, or conclusions.\n"
        "- Do not turn debated claims into settled facts.\n"
        "- Keep estimates and opinions clearly attributed.\n"
        "- Avoid usernames and @mentions unless truly necessary.\n"
        "- Keep the article technically focused and readable.\n"
        "- Make it suitable for Discourse posting after editorial review.\n"
        "- Use clean markdown with short headings and short paragraphs.\n"
        "- Keep SEO-friendly clarity, but do not write like marketing copy.\n"
        "- Keep repeated buyer-interest themes when supported: simple bolt-on install, plug-and-play preference, avoiding fabrication, willingness to pay for convenience.\n"
        "- Keep the article fuller than a thin summary, but do not add unsupported details.\n"
        "- Preserve shorthand meaning and numeric ranges: do not expand abbreviations unless clearly supported; keep ranges as ranges.\n"
        "- Do not output per-post rewrites.\n"
        "- Do not include evidence JSON inside the article body.\n"
        "- Output one JSON object only with the exact same schema as REWRITE_DRAFT.\n"
        "- Regenerate evidence so evidence.article_excerpt values match the final article exactly.\n"
        "- article_excerpt must be an exact substring copied from rewritten_article_markdown.\n"
        "- Do not copy article_excerpt from source posts.\n"
        "- Evidence must match the final article wording, not the original post wording.\n"
        "\n"
        "OUTPUT JSON MUST HAVE EXACTLY THESE KEYS:\n"
        "- rewritten_title: string\n"
        "- summary: string\n"
        "- seo_outline: array of strings\n"
        "- rewritten_article_markdown: string\n"
        "- evidence: array of objects with EXACT keys:\n"
        "    - article_excerpt: string\n"
        "    - post_ids: array of integers\n"
        "    - certainty: 'certain' | 'uncertain'\n"
        "    - source_excerpt: string\n"
        "- notes: string\n"
    )
    payload = {
        "thread": thread_payload,
        "rewrite_draft": rewrite,
    }
    return instructions + "\n\nFINALIZE_INPUT:\n" + json.dumps(payload, ensure_ascii=False)


def _basic_finalized_article_checks(rewrite: dict[str, Any]) -> None:
    title = (rewrite.get("rewritten_title") or "").strip()
    summary = (rewrite.get("summary") or "").strip()
    article = (rewrite.get("rewritten_article_markdown") or "").strip()
    if not title:
        raise ValueError("Finalized rewrite has empty rewritten_title.")
    if not summary:
        raise ValueError("Finalized rewrite has empty summary.")
    if not article:
        raise ValueError("Finalized rewrite has empty rewritten_article_markdown.")
    if "@" in article:
        raise ValueError("Finalized article contains '@' mentions; remove unless necessary.")


def _finalize_article_for_discourse(
    thread_payload: dict[str, Any],
    rewrite: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    prompt = _build_finalizer_prompt(thread_payload, rewrite)
    finalized = _call_ollama(prompt, model=model)
    if not isinstance(finalized, dict):
        raise ValueError("Finalizer must return a JSON object.")
    finalized = _repair_evidence_excerpts(thread_payload, finalized)
    _basic_finalized_article_checks(finalized)
    _validate_rewrite(thread_payload, finalized)
    return finalized


def _validate_rewrite(thread_payload: dict[str, Any], rewrite: dict[str, Any]) -> None:
    post_ids = {p["id"] for p in thread_payload.get("posts", [])}
    article = rewrite.get("rewritten_article_markdown")
    if not isinstance(article, str) or not article.strip():
        raise ValueError("rewritten_article_markdown must be a non-empty string.")
    article_lower = article.lower()
    # Precompute combined thread text for banned-phrase and shift-kit guards.
    thread_text = " ".join(
        (p.get("post_content_html") or "") for p in thread_payload.get("posts", [])
    ).lower()
    thread_plain = " ".join(
        (p.get("post_content_plain") or "") for p in thread_payload.get("posts", [])
    )

    if "evidence" not in rewrite or not isinstance(rewrite["evidence"], list):
        raise ValueError("Missing or invalid 'evidence' array in model output.")

    evidence = rewrite["evidence"]

    for ev in rewrite["evidence"]:
        if not isinstance(ev, dict):
            raise ValueError("Each evidence entry must be an object.")
        # article_excerpt: grounded in article
        article_excerpt = ev.get("article_excerpt")
        if not isinstance(article_excerpt, str) or not article_excerpt.strip():
            raise ValueError("Each evidence entry must have a non-empty 'article_excerpt' string.")
        if article_excerpt not in article:
            raise ValueError("evidence.article_excerpt must be an exact substring of the article.")
        if not _excerpt_in_article(article_excerpt, article):
            raise ValueError(
                "evidence.article_excerpt is not sufficiently grounded in rewritten_article_markdown."
            )
        if _is_likely_source_quote(article_excerpt, thread_plain):
            raise ValueError(
                "evidence.article_excerpt appears to be copied from source posts; use article wording."
            )

        ids = ev.get("post_ids")
        if not isinstance(ids, list) or not ids:
            raise ValueError("Each evidence entry must have a non-empty 'post_ids' array.")
        for pid in ids:
            if not isinstance(pid, int):
                raise ValueError("All post_ids must be integers.")
            if pid not in post_ids:
                raise ValueError(f"Model referenced unknown post_id {pid}.")
        certainty = ev.get("certainty")
        if certainty not in ("certain", "uncertain"):
            raise ValueError("evidence.certainty must be 'certain' or 'uncertain'.")
        source_excerpt = ev.get("source_excerpt")
        if source_excerpt is not None and not isinstance(source_excerpt, str):
            raise ValueError("evidence.source_excerpt must be a string when present.")

    required_keys = {
        "rewritten_title",
        "summary",
        "seo_outline",
        "rewritten_article_markdown",
        "evidence",
        "notes",
    }
    present = set(rewrite.keys())
    missing = required_keys - present
    if missing:
        raise ValueError(f"Model output missing keys: {sorted(missing)}")
    extra = present - required_keys
    if extra:
        raise ValueError(f"Model output has unexpected keys: {sorted(extra)}")

    # Best-effort check: evidence should cover meaningful bullet lines and paragraphs.
    lines = [ln.strip() for ln in article.splitlines() if ln.strip()]
    bullet_lines = [ln for ln in lines if ln.startswith(("-", "*"))]
    para_lines = [ln for ln in lines if not ln.startswith("#") and not ln.startswith(("-", "*"))]

    tech_bullets = [ln for ln in bullet_lines if len(_normalize_text(ln)) >= 24]
    tech_paras = [ln for ln in para_lines if len(_normalize_text(ln)) >= 60]

    def _covered_by_evidence(line: str) -> bool:
        for ev in evidence:
            ex = ev.get("article_excerpt") or ""
            if not isinstance(ex, str) or not ex:
                continue
            if line in ex or ex in line:
                return True
        return False

    if tech_bullets:
        covered = sum(1 for ln in tech_bullets if _covered_by_evidence(ln))
        coverage_ratio = covered / max(1, len(tech_bullets))
        if coverage_ratio < 0.75:
            raise ValueError(
                f"Evidence coverage too low for bullet content: {covered}/{len(tech_bullets)} "
                f"({coverage_ratio:.0%})"
            )

    if tech_paras:
        covered = sum(1 for ln in tech_paras if _covered_by_evidence(ln))
        coverage_ratio = covered / max(1, len(tech_paras))
        if coverage_ratio < 0.50:
            raise ValueError(
                f"Evidence coverage too low for paragraph content: {covered}/{len(tech_paras)} "
                f"({coverage_ratio:.0%})"
            )

    # Banned filler phrases unless present in source thread text.
    banned_phrases = [
        "generally",
        "typically",
        "might require",
        "with a few modifications",
        "recommended",
        "usually",
        "research indicates",
    ]
    for phrase in banned_phrases:
        if phrase in article_lower and phrase not in thread_text:
            raise ValueError(
                f"Banned filler phrase '{phrase}' appears in article without support in thread."
            )

    # Do not mention 'modifications' generically unless thread uses the word.
    if "modifications" in article_lower and "modifications" not in thread_text:
        raise ValueError(
            "Article mentions 'modifications' but source thread does not; remove or ground it."
        )

    # Known failure guard: do not allow 'shift kit' unless it appears in source posts.
    if "shift kit" in article_lower and "shift kit" not in thread_text:
        raise ValueError("Article mentions 'shift kit' but source thread does not.")


def main() -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser(
        description="Rewrite a PROMOTE thread with a local Ollama model (e.g. gpt-oss:20b)."
    )
    parser.add_argument(
        "--thread-id",
        type=int,
        help="Specific thread_id to rewrite (must be scored as PROMOTE). "
        "If omitted, the highest-score PROMOTE thread is used.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "qwen2.5:14b-instruct"),
        help="Ollama model name (default: qwen2.5:14b-instruct).",
    )
    args = parser.parse_args()

    factory = get_session_factory()
    session = factory()
    try:
        thread = _pick_promote_thread(session, thread_id=args.thread_id)
        thread_payload = _thread_to_payload(thread)
    finally:
        session.close()

    prompt = _build_prompt(thread_payload)
    first_rewrite = _call_ollama(prompt, model=args.model)
    first_rewrite = _repair_evidence_excerpts(thread_payload, first_rewrite)
    rewrite = first_rewrite
    try:
        _validate_rewrite(thread_payload, first_rewrite)
    except ValueError as first_err:
        LOG.warning("First rewrite failed validation: %s", first_err)
        correction_prompt = (
            prompt
            + "\n\nYour last output failed validation. Return one JSON OBJECT only (not an array). "
            "Do not return an array of per-post rewrites. Keep the exact same JSON schema and keys. "
            "Fix evidence so that evidence.article_excerpt values are copied from rewritten_article_markdown "
            "exactly (exact substring) and are NOT copied from source posts. Add missing evidence entries "
            "for meaningful technical bullet lines and paragraphs. Remove any banned filler phrases "
            "('generally', 'typically', 'usually', 'recommended', 'might require', "
            "'with a few modifications', 'research indicates') unless directly supported by THREAD_DATA.posts. "
            "If a point comes from one side of a disagreement, attribute it explicitly in the article "
            "instead of presenting it as a settled fact. Do not insert post ids into the article text."
        )
        try:
            second_rewrite = _call_ollama(correction_prompt, model=args.model)
            second_rewrite = _repair_evidence_excerpts(thread_payload, second_rewrite)
            _validate_rewrite(thread_payload, second_rewrite)
            rewrite = second_rewrite
        except ValueError as second_err:
            msg = str(second_err).lower()
            if "did not return json" in msg or "invalid json" in msg or "non-json" in msg:
                LOG.warning(
                    "Retry produced non-JSON or invalid JSON (%s); falling back to first-pass JSON "
                    "despite validation error: %s",
                    second_err,
                    first_err,
                )
                rewrite = first_rewrite
            else:
                raise

    # Enforce publish-ready checks on the selected draft rewrite before any finalization.
    _assert_publish_ready(thread_payload, rewrite)

    # Final Discourse-ready editorial cleanup (thread-level only).
    try:
        finalized = _finalize_article_for_discourse(thread_payload, rewrite, model=args.model)
        _assert_publish_ready(thread_payload, finalized)
        rewrite = finalized
        LOG.info("Finalized thread-level article for Discourse.")
    except Exception as exc:
        LOG.warning("Finalizer failed; attempting to fall back to pre-finalized rewrite: %s", exc)
        try:
            _assert_publish_ready(thread_payload, rewrite)
        except Exception as pub_exc:
            raise ValueError(
                "No publish-ready rewrite available (finalized failed and draft is not publish-ready)."
            ) from pub_exc

    out = {
        "thread": thread_payload,
        "rewrite": rewrite,
        "model": args.model,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
