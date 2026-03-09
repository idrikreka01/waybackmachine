import json

from waybackmachine.db.models import Phase1ExportRun, Phase1ExportThread, ThreadEvergreenScore
from waybackmachine.db.session import get_session_factory, init_db, reset_db_for_scraper
from waybackmachine.reporting.export_seo_pack import main as export_main


def _make_score_row(
    session,
    thread_id: int,
    final_score: int,
    decision: str,
    scoring_version: str = "v1",
    title: str = "Title",
    link: str = "https://example.com/t",
    category_path: str = "Root > Cat",
    matched_keywords: list[str] | None = None,
    matched_category: str | None = None,
    cross_signals: list[str] | None = None,
    noise_flags: list[str] | None = None,
) -> None:
    payload = {
        "scoring_version": scoring_version,
        "thread": {
            "thread_id": thread_id,
            "title": title,
            "link": link,
            "category_path": category_path,
            "subcategory_name": "",
            "is_sticky": False,
            "replies_no": 10,
            "pagination_no": 1,
            "created_at": "2020-01-01T00:00:00Z",
            "last_post_at": "2020-01-02T00:00:00Z",
            "activity_span_years": 1,
            "revival_count": 0,
        },
        "score": {"raw": final_score, "final": final_score, "decision": decision},
        "breakdown": {
            "problem_intent": {
                "points": 0,
                "matched_keywords": matched_keywords or [],
                "match_sources": [],
            },
            "category_bonus": {
                "points": 0,
                "matched_category": matched_category,
            },
            "cross_generation": {
                "points": 0,
                "detected": bool(cross_signals),
                "signals_matched": cross_signals or [],
            },
            "noise": {
                "points": 0,
                "flags": noise_flags or [],
            },
        },
    }
    row = ThreadEvergreenScore(
        thread_id=thread_id,
        scoring_version=scoring_version,
        final_score=final_score,
        raw_score=final_score,
        decision=decision,
        result_json=json.dumps(payload),
    )
    session.add(row)


def test_export_seo_pack_promote_only(tmp_path, monkeypatch):
    reset_db_for_scraper()
    init_db()
    factory = get_session_factory()
    s = factory()
    _make_score_row(
        s,
        thread_id=1,
        final_score=90,
        decision="PROMOTE",
        title="How to fix wiring",
        link="https://example.com/t1",
        category_path="Root > Electrical",
        matched_keywords=["fix", "wiring"],
        matched_category="Electrical",
        cross_signals=["multiple_years"],
        noise_flags=["single_reply"],
    )
    _make_score_row(
        s,
        thread_id=2,
        final_score=70,
        decision="HOLD",
        title="Some other thread",
        link="https://example.com/t2",
        category_path="Root > Suspension",
        matched_keywords=["upgrade"],
    )
    _make_score_row(
        s,
        thread_id=3,
        final_score=30,
        decision="ARCHIVE",
        title="Random chat",
        link="https://example.com/t3",
        category_path="Root > Offtopic",
    )
    s.commit()
    s.close()

    export_dir = tmp_path / "exports"
    monkeypatch.setenv("SEO_EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("SEO_EXPORT_DECISION", "PROMOTE")
    monkeypatch.setenv("SEO_EXPORT_TOP_N", "10")
    monkeypatch.delenv("SEO_SCORING_VERSION", raising=False)
    monkeypatch.setenv("SEO_INCLUDE_SUMMARIES", "false")

    export_main()

    assert (export_dir / "phase1_top_threads.csv").is_file()
    assert (export_dir / "phase1_bucket_counts.json").is_file()
    assert (export_dir / "phase1_category_distribution.csv").is_file()
    assert (export_dir / "phase1_keyword_hits.csv").is_file()
    assert (export_dir / "phase1_crossgen_hits.csv").is_file()
    assert (export_dir / "phase1_samples.json").is_file()
    assert not (export_dir / "phase1_summaries.jsonl").exists()

    with (export_dir / "phase1_bucket_counts.json").open(encoding="utf-8") as f:
        counts = json.load(f)
    assert counts["total_scored_rows"] == 3
    assert counts["by_decision"]["PROMOTE"] == 1
    assert counts["by_decision"]["HOLD"] == 1
    assert counts["by_decision"]["ARCHIVE"] == 1
    assert counts["exported_decision"] == "PROMOTE"
    assert counts["exported_count"] == 1
    assert counts["scoring_version_filter"] is None

    top_lines = (export_dir / "phase1_top_threads.csv").read_text(encoding="utf-8").splitlines()
    assert len(top_lines) == 2
    header = top_lines[0].split(",")
    assert "thread_id" in header
    assert "problem_keywords" in header
    row = top_lines[1].split(",")
    assert "https://example.com/t1" in top_lines[1]

    kw_lines = (export_dir / "phase1_keyword_hits.csv").read_text(encoding="utf-8").splitlines()
    assert "keyword,count" == kw_lines[0]
    assert any("fix,1" in line for line in kw_lines[1:])
    assert any("wiring,1" in line for line in kw_lines[1:])

    cross_lines = (export_dir / "phase1_crossgen_hits.csv").read_text(encoding="utf-8").splitlines()
    assert "signal,count" == cross_lines[0]
    assert any("multiple_years,1" in line for line in cross_lines[1:])

    cat_lines = (export_dir / "phase1_category_distribution.csv").read_text(encoding="utf-8").splitlines()
    assert "category,count,avg_score,median_score" == cat_lines[0]
    assert any("Electrical,1," in line for line in cat_lines[1:])

    with (export_dir / "phase1_samples.json").open(encoding="utf-8") as f:
        samples = json.load(f)
    assert len(samples) == 1
    assert samples[0]["thread_id"] == 1
    assert samples[0]["final_score"] == 90
    assert samples[0]["score_breakdown"]["problem_intent"]["matched_keywords"] == ["fix", "wiring"]

    s = factory()
    runs = s.query(Phase1ExportRun).all()
    s.close()
    assert len(runs) == 1
    assert runs[0].exported_decision == "PROMOTE"
    assert runs[0].exported_count == 1
    s = factory()
    threads = s.query(Phase1ExportThread).filter(Phase1ExportThread.run_id == runs[0].id).all()
    s.close()
    assert len(threads) == 1
    assert threads[0].thread_id == 1
    assert threads[0].title == "How to fix wiring"
    assert "fix" in threads[0].problem_keywords and "wiring" in threads[0].problem_keywords


def test_export_seo_pack_scoring_version_filter(tmp_path, monkeypatch):
    reset_db_for_scraper()
    init_db()
    factory = get_session_factory()
    s = factory()
    _make_score_row(
        s,
        thread_id=10,
        final_score=80,
        decision="PROMOTE",
        scoring_version="v1",
        title="Guide v1",
        link="https://example.com/t10",
        category_path="Root > Electrical",
        matched_keywords=["guide"],
    )
    _make_score_row(
        s,
        thread_id=11,
        final_score=85,
        decision="PROMOTE",
        scoring_version="v2",
        title="Guide v2",
        link="https://example.com/t11",
        category_path="Root > Electrical",
        matched_keywords=["guide"],
    )
    s.commit()
    s.close()

    export_dir = tmp_path / "exports_v1"
    monkeypatch.setenv("SEO_EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("SEO_EXPORT_DECISION", "PROMOTE")
    monkeypatch.setenv("SEO_EXPORT_TOP_N", "10")
    monkeypatch.setenv("SEO_SCORING_VERSION", "v1")
    monkeypatch.setenv("SEO_INCLUDE_SUMMARIES", "false")

    export_main()

    with (export_dir / "phase1_bucket_counts.json").open(encoding="utf-8") as f:
        counts = json.load(f)
    assert counts["total_scored_rows"] == 1
    assert counts["by_decision"]["PROMOTE"] == 1
    assert counts["exported_decision"] == "PROMOTE"
    assert counts["exported_count"] == 1
    assert counts["scoring_version_filter"] == "v1"

