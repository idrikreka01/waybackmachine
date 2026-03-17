import json
from pathlib import Path
from typing import Any, List, Set

from discourse_publish_test import (  # type: ignore[attr-defined]
    _normalize_tags,
    build_headers,
    ensure_tags_exist,
)
from waybackmachine.db.models import ThreadEvergreenScore
from waybackmachine.db.session import get_session_factory


def main() -> None:
    from waybackmachine.config import FORUM_INDEX_URL  # type: ignore[attr-defined]

    base_url = FORUM_INDEX_URL.split("/forum", 1)[0]
    factory = get_session_factory()
    session = factory()
    try:
        all_tags: Set[str] = set()
        rows: List[ThreadEvergreenScore] = session.query(ThreadEvergreenScore).all()
        for row in rows:
            raw: Any = row.result_json
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            tags_raw = payload.get("tags") or []
            if not isinstance(tags_raw, list):
                continue
            for t in tags_raw:
                s = str(t).strip()
                if s:
                    all_tags.add(s)
    finally:
        session.close()

    normalized = _normalize_tags(list(all_tags))
    print(f"Preparing {len(normalized)} unique tags: {', '.join(normalized)}")

    headers = build_headers()
    ensure_tags_exist(base_url=base_url, headers=headers, tags=normalized)

    out = Path("exports") / "prepared_tags.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(normalized) + "\n", encoding="utf-8")
    print(f"Wrote tag list to: {out.resolve()}")


if __name__ == "__main__":
    main()

