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
        post_items.append(
            {
                "id": p.id,
                "post_date_time": p.post_date_time.isoformat() if p.post_date_time else None,
                "user_username": p.user_username,
                "post_content_html": p.post_content,
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
    body = {"model": model, "prompt": prompt, "stream": False}
    data = json.dumps(body).encode("utf-8")
    url = _get_ollama_url()
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return (payload.get("response") or "").strip()


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
    return _call_ollama_text(prompt, model=model)


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


def _build_prompt(thread_payload: dict[str, Any]) -> str:
    instructions = (
        "You are a senior automotive technical writer.\n"
        "\n"
        "You will receive THREAD_DATA (JSON for one forum thread).\n"
        "\n"
        "CRITICAL RULES (DO NOT BREAK):\n"
        "- You are creating a NEW standalone technical how-to article for a modern forum.\n"
        "- Do NOT recreate the original forum thread, conversation flow, or narrative.\n"
        "- Do NOT copy sentences or long phrases directly from THREAD_DATA; always paraphrase in new wording.\n"
        "- Remove usernames, dates, signatures, jokes, chit-chat, and other personal or social content.\n"
        "- Focus only on neutral, factual, step-by-step technical explanation and troubleshooting.\n"
        "- Use ONLY information explicitly present in THREAD_DATA.\n"
        "- Do NOT add new facts, parts, steps, costs, requirements, or warnings unless they appear in THREAD_DATA.\n"
        "- If something is unclear or debated in the thread, mark it as 'uncertain' and describe both sides briefly in the article.\n"
        "- For EVERY bullet/QA pair in rewritten_article_markdown, you MUST create a matching evidence entry.\n"
        "- Every technical sentence or bullet in rewritten_article_markdown must be backed by one or more post_ids from THREAD_DATA.posts.\n"
        "- If you cannot support a technical statement with a post_id, do NOT include it.\n"
        "- BANNED PHRASES in the article text (unless directly quoted from a post): 'generally', 'typically', 'might require', 'with a few modifications', 'recommended', 'usually'.\n"
        "- Do not introduce new words like 'modifications' unless the thread explicitly states what those modifications are in the cited posts.\n"
        "- Do not append things like '(Post ID: 1234)' into the article text; the article must read cleanly. All citations go into the evidence array only.\n"
        "- Output ONLY valid JSON (no markdown, no extra text).\n"
        "\n"
        "OUTPUT JSON MUST HAVE EXACTLY THESE KEYS:\n"
        "- rewritten_title: string\n"
        "- summary: string (2–4 sentences)\n"
        "- seo_outline: array of strings\n"
        "- rewritten_article_markdown: string\n"
        "- evidence: array of objects with EXACT keys:\n"
        "    - article_excerpt: string (an exact substring copied from rewritten_article_markdown)\n"
        "    - post_ids: array of integers (ids from THREAD_DATA.posts)\n"
        "    - certainty: 'certain' | 'uncertain'\n"
        "    - source_excerpt: string (optional but preferred; max ~25 words copied from the source post text)\n"
        "- notes: string (only for unknowns, disagreements, or intentionally omitted info)\n"
        "\n"
        "Only set certainty='uncertain' if there are conflicting posts or the author explicitly says the information is partial/unknown.\n"
        "When you mark something as uncertain, you MUST include both positions in the article (for example, two bullets) and cite the post_ids for each side.\n"
        "\n"
        "Use the notes field only for truly unknown or unclear points (for example, when a term is used but never defined). Do not write 'Unknown based on the thread' when the thread clearly states the fact.\n"
    )
    thread_json = json.dumps(thread_payload, ensure_ascii=False)
    return instructions + "\n\nTHREAD_DATA:\n" + thread_json


def _call_ollama(prompt: str, model: str) -> dict[str, Any]:
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
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
            return json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Model returned invalid JSON: {raw[:200]}") from exc

    # Attempt to extract the first JSON object from free-form text
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = raw[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model returned non-JSON response: {raw[:200]}") from exc

    raise ValueError(f"Model did not return JSON: {raw[:200]}")


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
        if not _excerpt_in_article(article_excerpt, article):
            raise ValueError(
                "evidence.article_excerpt is not sufficiently grounded in rewritten_article_markdown."
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

    # Best-effort check: evidence should cover most content lines
    lines = [ln.strip() for ln in article.splitlines()]
    content_lines = [ln for ln in lines if ln and not ln.startswith("#")]
    # Evidence coverage must be at least the number of QA answers (or a small floor).
    answer_lines = [ln for ln in lines if ln.startswith("- **Answer:**")]
    answer_count = len(answer_lines)
    expected_min = max(3, answer_count)
    if len(evidence) < expected_min:
        raise ValueError(
            f"Evidence too sparse: {len(evidence)} < expected minimum {expected_min} "
            f"for {answer_count} Answer lines."
        )

    # Every Answer line must be covered by at least one evidence.article_excerpt.
    for ans in answer_lines:
        if not any(ans in ev.get("article_excerpt", "") for ev in evidence):
            raise ValueError(f"No evidence entry found for Answer line: {ans!r}")

    # Banned filler phrases unless present in source thread text.
    banned_phrases = [
        "generally",
        "typically",
        "might require",
        "with a few modifications",
        "recommended",
        "usually",
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
        default=os.environ.get("OLLAMA_MODEL", "gpt-oss:20b"),
        help="Ollama model name (default: gpt-oss:20b).",
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
    rewrite = first_rewrite
    try:
        _validate_rewrite(thread_payload, first_rewrite)
    except ValueError as first_err:
        LOG.warning("First rewrite failed validation: %s", first_err)
        correction_prompt = (
            prompt
            + "\n\nYour last output failed validation because evidence coverage was insufficient "
            "and/or banned filler phrases were used. Return JSON only. Add evidence for EVERY "
            '"- **Answer:**" line and ensure each Answer line has at least one matching '
            "evidence.article_excerpt substring. Paraphrase all content instead of copying "
            "sentences from THREAD_DATA posts. Remove any banned filler phrases "
            "('generally', 'typically', 'might require', 'with a few modifications', "
            "'recommended', 'usually') unless you quote them exactly from THREAD_DATA posts. "
            "Do not change the JSON schema."
        )
        try:
            second_rewrite = _call_ollama(correction_prompt, model=args.model)
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

    out = {
        "thread": thread_payload,
        "rewrite": rewrite,
        "model": args.model,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
