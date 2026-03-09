import json
import os
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from waybackmachine.db.models import (
    Phase1ExportCategory,
    Phase1ExportCrossgenHit,
    Phase1ExportKeywordHit,
    Phase1ExportRun,
    Phase1ExportThread,
    ThreadEvergreenScore,
)
from waybackmachine.db.session import get_session_factory
from waybackmachine.logging_config import configure_logging


def _get_env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _get_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _load_result_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    if not isinstance(raw, str):
        return {}
    raw = raw.strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _get_nested(d: dict[str, Any], path: list[str], default: Any = None) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def _extract_thread_row(tid: int, final_score: int, decision: str, payload: dict[str, Any]) -> dict[str, Any]:
    thread = payload.get("thread") or {}
    breakdown = payload.get("breakdown") or {}
    problem = breakdown.get("problem_intent") or {}
    category_bonus = breakdown.get("category_bonus") or {}
    cross_gen = breakdown.get("cross_generation") or {}
    noise = breakdown.get("noise") or {}

    matched_keywords = problem.get("matched_keywords") or []
    cross_signals = cross_gen.get("signals_matched") or []
    noise_flags = noise.get("flags") or []

    return {
        "thread_id": tid,
        "final_score": final_score,
        "decision": decision,
        "title": thread.get("title") or "",
        "url": thread.get("link") or "",
        "category_path": thread.get("category_path") or "",
        "is_sticky": bool(thread.get("is_sticky")),
        "replies_no": thread.get("replies_no") or 0,
        "pagination_no": thread.get("pagination_no") or 0,
        "created_at": thread.get("created_at") or "",
        "last_post_at": thread.get("last_post_at") or "",
        "activity_span_years": thread.get("activity_span_years") or 0,
        "revival_count": thread.get("revival_count") or 0,
        "matched_category": category_bonus.get("matched_category") or "",
        "problem_keywords": [k for k in matched_keywords if k],
        "cross_gen_signals": [s for s in cross_signals if s],
        "noise_flags": [f for f in noise_flags if f],
    }


def _category_label(row: dict[str, Any]) -> str:
    matched = row.get("matched_category")
    if matched:
        return str(matched)
    path = (row.get("category_path") or "").strip()
    if not path:
        return "UNKNOWN"
    parts = [p.strip() for p in path.split(">") if p.strip()]
    if not parts:
        return path
    return parts[-1]


def _write_phase1_top_threads(path: Path, rows: list[dict[str, Any]]) -> None:
    import csv

    fieldnames = [
        "thread_id",
        "final_score",
        "decision",
        "title",
        "url",
        "category_path",
        "is_sticky",
        "replies_no",
        "pagination_no",
        "created_at",
        "last_post_at",
        "activity_span_years",
        "revival_count",
        "matched_category",
        "problem_keywords",
        "cross_gen_signals",
        "noise_flags",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **{k: row.get(k) for k in fieldnames[:-3]},
                    "problem_keywords": ",".join(row.get("problem_keywords") or []),
                    "cross_gen_signals": ",".join(row.get("cross_gen_signals") or []),
                    "noise_flags": ",".join(row.get("noise_flags") or []),
                }
            )


def _write_bucket_counts(
    path: Path,
    total_rows: int,
    by_decision: dict[str, int],
    exported_decision: str,
    exported_count: int,
    scoring_version_filter: str | None,
) -> None:
    data = {
        "total_scored_rows": total_rows,
        "by_decision": by_decision,
        "exported_decision": exported_decision,
        "exported_count": exported_count,
        "scoring_version_filter": scoring_version_filter,
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _write_category_distribution(path: Path, rows: list[dict[str, Any]]) -> None:
    import csv

    buckets: dict[str, list[int]] = {}
    for row in rows:
        label = _category_label(row)
        buckets.setdefault(label, []).append(int(row.get("final_score") or 0))

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "count", "avg_score", "median_score"])
        for category, scores in sorted(buckets.items()):
            if not scores:
                continue
            count = len(scores)
            avg = sum(scores) / count
            med = statistics.median(scores)
            writer.writerow([category, count, f"{avg:.2f}", f"{med:.2f}"])


def _write_keyword_hits(path: Path, rows: list[dict[str, Any]]) -> None:
    import csv

    counter: Counter[str] = Counter()
    for row in rows:
        for kw in row.get("problem_keywords") or []:
            counter[kw] += 1

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["keyword", "count"])
        for kw, count in sorted(counter.items(), key=lambda x: (-x[1], x[0])):
            writer.writerow([kw, count])


def _write_crossgen_hits(path: Path, rows: list[dict[str, Any]]) -> None:
    import csv

    counter: Counter[str] = Counter()
    for row in rows:
        for sig in row.get("cross_gen_signals") or []:
            counter[sig] += 1

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["signal", "count"])
        for sig, count in sorted(counter.items(), key=lambda x: (-x[1], x[0])):
            writer.writerow([sig, count])


def _write_samples(path: Path, rows: list[dict[str, Any]], raw_payloads: dict[int, dict[str, Any]]) -> None:
    top = sorted(rows, key=lambda r: int(r.get("final_score") or 0), reverse=True)[:10]
    out: list[dict[str, Any]] = []
    for row in top:
        tid = int(row["thread_id"])
        payload = raw_payloads.get(tid, {})
        thread = payload.get("thread") or {}
        breakdown = payload.get("breakdown") or {}
        out.append(
            {
                "thread_id": tid,
                "final_score": row.get("final_score"),
                "title": thread.get("title") or "",
                "url": thread.get("link") or "",
                "score_breakdown": breakdown,
            }
        )
    with path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def _write_summaries_jsonl(
    path: Path,
    rows: list[dict[str, Any]],
    raw_payloads: dict[int, dict[str, Any]],
    session,
) -> int:
    from waybackmachine.db.models import Thread  # type: ignore[attr-defined]

    try:
        from waybackmachine.db.models import ThreadSummary  # type: ignore[attr-defined]
    except ImportError:
        print("SEO summaries requested but ThreadSummary model not available; skipping summaries.")
        return 0

    ids = [int(r["thread_id"]) for r in rows]
    if not ids:
        return 0
    q = session.query(ThreadSummary).filter(ThreadSummary.thread_id.in_(ids))
    summaries_by_tid: dict[int, Any] = {}
    for row in q.all():
        summaries_by_tid[row.thread_id] = row.summary_json

    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in sorted(rows, key=lambda r: int(r.get("final_score") or 0), reverse=True):
            tid = int(row["thread_id"])
            if tid not in summaries_by_tid:
                continue
            payload = raw_payloads.get(tid, {})
            thread = payload.get("thread") or {}
            obj = {
                "thread_id": tid,
                "final_score": row.get("final_score"),
                "title": thread.get("title") or "",
                "url": thread.get("link") or "",
                "summary_json": summaries_by_tid[tid],
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            count += 1
    if count == 0:
        print("SEO summaries requested but no summaries found for exported threads.")
    return count


def _persist_phase1_to_db(
    session,
    exported_decision: str,
    exported_count: int,
    total_rows: int,
    by_decision: dict[str, int],
    scoring_version_filter: str | None,
    top_n: int,
    exported_struct_rows: list[dict[str, Any]],
) -> None:
    now = datetime.now(timezone.utc)
    run = Phase1ExportRun(
        exported_at=now,
        exported_decision=exported_decision,
        exported_count=exported_count,
        total_scored_rows=total_rows,
        by_decision=json.dumps(by_decision),
        scoring_version_filter=scoring_version_filter,
        top_n=top_n,
    )
    session.add(run)
    session.flush()

    for row in exported_struct_rows:
        session.add(
            Phase1ExportThread(
                run_id=run.id,
                thread_id=int(row["thread_id"]),
                final_score=int(row.get("final_score") or 0),
                decision=row.get("decision") or "",
                title=(row.get("title") or "")[:1024],
                url=row.get("url") or "",
                category_path=row.get("category_path") or "",
                is_sticky=bool(row.get("is_sticky")),
                replies_no=int(row.get("replies_no") or 0),
                pagination_no=int(row.get("pagination_no") or 0),
                created_at=str(row.get("created_at") or ""),
                last_post_at=str(row.get("last_post_at") or ""),
                activity_span_years=int(row.get("activity_span_years") or 0),
                revival_count=int(row.get("revival_count") or 0),
                matched_category=(row.get("matched_category") or "")[:512],
                problem_keywords=",".join(row.get("problem_keywords") or []),
                cross_gen_signals=",".join(row.get("cross_gen_signals") or []),
                noise_flags=",".join(row.get("noise_flags") or []),
            )
        )

    buckets: dict[str, list[int]] = {}
    for row in exported_struct_rows:
        label = _category_label(row)
        buckets.setdefault(label, []).append(int(row.get("final_score") or 0))
    for category, scores in sorted(buckets.items()):
        if not scores:
            continue
        count = len(scores)
        avg = sum(scores) / count
        med = statistics.median(scores)
        session.add(
            Phase1ExportCategory(
                run_id=run.id,
                category=category[:512],
                count=count,
                avg_score=round(avg, 2),
                median_score=round(med, 2),
            )
        )

    kw_counter: Counter[str] = Counter()
    for row in exported_struct_rows:
        for kw in row.get("problem_keywords") or []:
            kw_counter[kw] += 1
    for kw, count in kw_counter.items():
        session.add(
            Phase1ExportKeywordHit(run_id=run.id, keyword=kw[:256], count=count)
        )

    sig_counter: Counter[str] = Counter()
    for row in exported_struct_rows:
        for sig in row.get("cross_gen_signals") or []:
            sig_counter[sig] += 1
    for sig, count in sig_counter.items():
        session.add(
            Phase1ExportCrossgenHit(run_id=run.id, signal=sig[:256], count=count)
        )


def main() -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))

    decision = os.environ.get("SEO_EXPORT_DECISION", "PROMOTE").strip().upper() or "PROMOTE"
    top_n = _get_env_int("SEO_EXPORT_TOP_N", 100)
    export_dir = os.environ.get("SEO_EXPORT_DIR", "phase1_exports").strip() or "phase1_exports"
    include_summaries = _get_env_bool("SEO_INCLUDE_SUMMARIES", False)
    scoring_version_filter = os.environ.get("SEO_SCORING_VERSION")
    if scoring_version_filter:
        scoring_version_filter = scoring_version_filter.strip() or None

    out_dir = Path(export_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    factory = get_session_factory()
    session = factory()
    try:
        base_query = session.query(ThreadEvergreenScore)
        if scoring_version_filter:
            base_query = base_query.filter(
                ThreadEvergreenScore.scoring_version == scoring_version_filter
            )
        all_rows = base_query.all()
        total_rows = len(all_rows)

        by_decision: dict[str, int] = {}
        for row in all_rows:
            d = (row.decision or "").upper()
            by_decision[d] = by_decision.get(d, 0) + 1

        exported_query = base_query.filter(
            ThreadEvergreenScore.decision == decision
        )
        exported_rows = exported_query.all()
        exported_count = len(exported_rows)

        exported_rows_sorted = sorted(
            exported_rows, key=lambda r: int(r.final_score), reverse=True
        )
        top_rows = exported_rows_sorted[:top_n]

        raw_payloads: dict[int, dict[str, Any]] = {}
        exported_struct_rows: list[dict[str, Any]] = []
        for row in exported_rows:
            payload = _load_result_json(row.result_json)
            raw_payloads[row.thread_id] = payload
            exported_struct_rows.append(
                _extract_thread_row(row.thread_id, row.final_score, row.decision, payload)
            )

        top_struct_rows = [
            r
            for r in sorted(
                exported_struct_rows,
                key=lambda r: int(r.get("final_score") or 0),
                reverse=True,
            )[:top_n]
        ]

        _write_phase1_top_threads(out_dir / "phase1_top_threads.csv", top_struct_rows)
        _write_bucket_counts(
            out_dir / "phase1_bucket_counts.json",
            total_rows=total_rows,
            by_decision=by_decision,
            exported_decision=decision,
            exported_count=exported_count,
            scoring_version_filter=scoring_version_filter,
        )
        _write_category_distribution(out_dir / "phase1_category_distribution.csv", exported_struct_rows)
        _write_keyword_hits(out_dir / "phase1_keyword_hits.csv", exported_struct_rows)
        _write_crossgen_hits(out_dir / "phase1_crossgen_hits.csv", exported_struct_rows)
        _write_samples(out_dir / "phase1_samples.json", exported_struct_rows, raw_payloads)

        _persist_phase1_to_db(
            session,
            exported_decision=decision,
            exported_count=exported_count,
            total_rows=total_rows,
            by_decision=by_decision,
            scoring_version_filter=scoring_version_filter,
            top_n=top_n,
            exported_struct_rows=exported_struct_rows,
        )
        session.commit()

        summaries_count = 0
        if include_summaries:
            summaries_count = _write_summaries_jsonl(
                out_dir / "phase1_summaries.jsonl",
                exported_struct_rows,
                raw_payloads,
                session,
            )

        print(f"Total scored rows: {total_rows}")
        print(f"By decision: {by_decision}")
        print(f"Exported decision: {decision}, exported count: {exported_count}")
        print(f"Wrote exports to: {out_dir}")
        if include_summaries:
            print(f"Summaries included: {summaries_count}")
    finally:
        session.close()


if __name__ == "__main__":
    main()

