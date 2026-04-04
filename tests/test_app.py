from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import MethodType

import requests
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, Submission
from app.fetcher import OJFetcher
from app.services.report import generate_weekly_report
from app.services.stats import (
    get_dashboard_summary,
    list_existing_tags,
    get_period_stats,
    get_tag_distribution,
    get_weekly_stats,
    list_unsolved_problems,
    list_tag_problems,
    list_recent_sync_runs,
)
from app.services.tags import normalize_tags, tags_for_knowledge_stats


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return TestingSession()


def test_status_normalization():
    db = build_session()
    fetcher = OJFetcher(db)
    assert fetcher._normalize_status("OK") == "AC"
    assert fetcher._normalize_status("WRONG_ANSWER") == "WA"
    assert fetcher._normalize_status(14) == "WA"
    assert fetcher._normalize_status(99) == "WA"
    assert fetcher._normalize_status("SOMETHING_NEW") == "UNKNOWN"


def test_weekly_stats_and_tags():
    db = build_session()
    db.add_all(
        [
            Submission(
                oj_source="codeforces",
                problem_id="100A",
                problem_name="Example A",
                difficulty="1200",
                tags='["dp", "math"]',
                status="AC",
                submit_time=datetime.now(timezone.utc),
                runtime=31,
                memory=1024,
            ),
            Submission(
                oj_source="luogu",
                problem_id="P1001",
                problem_name="A+B Problem",
                difficulty="入门",
                tags='["math"]',
                status="WA",
                submit_time=datetime.now(timezone.utc),
                runtime=14,
                memory=512,
            ),
        ]
    )
    db.commit()

    weekly = get_weekly_stats(db)
    tags = get_tag_distribution(db)

    assert weekly["attempt_count"] == 2
    assert weekly["ac_count"] == 1
    assert tags[0]["tag"] in {"dp", "math", "动态规划", "数学"}

    tags_cf_only = get_tag_distribution(db, oj_source="codeforces")
    assert len(tags_cf_only) >= 1
    tags_lg_only = get_tag_distribution(db, oj_source="luogu")
    assert len(tags_lg_only) == 0


def test_tag_distribution_prefers_direct_ac_over_aggregated_mirror():
    db = build_session()
    t_mirror = datetime.now(timezone.utc)
    t_direct = t_mirror + timedelta(seconds=2)
    db.add_all(
        [
            Submission(
                oj_source="nowcoder",
                problem_id="12345",
                problem_name="Mirror",
                difficulty=None,
                tags='["mirror-only-tag"]',
                status="AC",
                submit_time=t_mirror,
                via_vjudge=True,
            ),
            Submission(
                oj_source="nowcoder",
                problem_id="12345",
                problem_name="Direct",
                difficulty=None,
                tags='["direct-tag"]',
                status="AC",
                submit_time=t_direct,
                via_vjudge=False,
            ),
        ]
    )
    db.commit()
    tags = get_tag_distribution(db, limit=20, oj_source="nowcoder")
    tag_names = {item["tag"] for item in tags}
    assert "direct-tag" in tag_names
    assert "mirror-only-tag" not in tag_names


def test_report_generation_for_empty_data():
    report = generate_weekly_report(
        {"week_start": "2026-03-30", "week_end": "2026-04-05", "ac_count": 0, "attempt_count": 0, "accuracy": 0.0},
        [],
    )
    assert "没有同步到提交记录" in report["summary"]


def test_dashboard_summary_without_sync_runs():
    db = build_session()
    db.add(
        Submission(
            oj_source="codeforces",
            problem_id="200A",
            problem_name="Another Example",
            difficulty="1400",
            tags='["graphs"]',
            status="AC",
            submit_time=datetime.now(timezone.utc),
            runtime=40,
            memory=2048,
        )
    )
    db.commit()

    summary = get_dashboard_summary(db)
    assert summary["total_submissions"] == 1
    assert summary["total_ac"] == 1
    assert summary["active_days"] == 1


def test_luogu_first_sync_fetches_all_pages():
    db = build_session()
    fetcher = OJFetcher(db)

    pages = {
        1: [
            {"external_submission_id": "101", "problem_id": "P1001", "problem_name": "A", "status": "AC", "submit_time": 1710000100},
            {"external_submission_id": "102", "problem_id": "P1002", "problem_name": "B", "status": "WA", "submit_time": 1710000000},
        ],
        2: [
            {"external_submission_id": "103", "problem_id": "P1003", "problem_name": "C", "status": "AC", "submit_time": 1709999900},
        ],
        3: [],
    }

    fetcher._fetch_luogu_record_page = MethodType(lambda self, identifier, page: pages.get(page, []), fetcher)
    fetcher._fetch_luogu_user_page_records = MethodType(lambda self, identifier: [], fetcher)

    result = fetcher._fetch_all_luogu_records("123456", force_full=False)
    assert len(result) == 3


def test_luogu_incremental_stops_after_old_records():
    db = build_session()
    db.add(
        Submission(
            oj_source="luogu",
            problem_id="P9999",
            problem_name="Old",
            difficulty="入门",
            tags="[]",
            status="AC",
            submit_time=datetime.fromtimestamp(1710000000, tz=timezone.utc),
            runtime=10,
            memory=10,
        )
    )
    db.commit()

    fetcher = OJFetcher(db)
    pages = {
        1: [
            {"external_submission_id": "201", "problem_id": "P1001", "problem_name": "New", "status": "AC", "submit_time": 1710000200},
            {"external_submission_id": "202", "problem_id": "P1002", "problem_name": "Old", "status": "WA", "submit_time": 1709999900},
        ],
        2: [
            {"external_submission_id": "203", "problem_id": "P1003", "problem_name": "Older", "status": "AC", "submit_time": 1709999800},
        ],
    }

    fetcher._fetch_luogu_record_page = MethodType(lambda self, identifier, page: pages.get(page, []), fetcher)
    fetcher._fetch_luogu_user_page_records = MethodType(lambda self, identifier: [], fetcher)

    result = fetcher._fetch_all_luogu_records("123456", force_full=False)
    assert len(result) == 1
    assert result[0]["external_submission_id"] == "201"


def test_luogu_virtual_judge_style_sync_uses_practice_archive():
    db = build_session()
    fetcher = OJFetcher(db)
    fetcher.config.luogu_cookie = "valid-cookie"

    fetcher._resolve_luogu_uid = MethodType(lambda self, uid=None, username=None: "123456", fetcher)
    fetcher._fetch_luogu_practice_solved = MethodType(
        lambda self, uid: [
            {"problem_id": "P1001", "problem_name": "A+B Problem", "difficulty": "入门", "tags": ["math"]},
            {"problem_id": "P1002", "problem_name": "过河卒", "difficulty": "普及-", "tags": ["dp"]},
        ],
        fetcher,
    )
    fetcher._fetch_all_luogu_records = MethodType(
        lambda self, uid, force_full=True: [
            {"problem_id": "P1001", "status": "AC", "submit_time": 1710000000, "external_submission_id": "1"},
            {"problem_id": "P1002", "status": "AC", "submit_time": 1710000100, "external_submission_id": "2"},
        ],
        fetcher,
    )
    fetcher._fetch_luogu_problem_meta = MethodType(
        lambda self, pid: {"difficulty": "入门", "tags": ["math"]},
        fetcher,
    )

    result = fetcher.fetch_luogu_submissions(uid="123456", force_full=False)
    assert len(result) == 2
    assert {item["problem_id"] for item in result} == {"P1001", "P1002"}
    assert all(item["status"] == "AC" for item in result)


def test_luogu_incremental_archive_sync_skips_existing_ac_problem():
    db = build_session()
    db.add(
        Submission(
            oj_source="luogu",
            problem_id="P1001",
            problem_name="A+B Problem",
            difficulty="入门",
            tags='["math"]',
            status="AC",
            submit_time=datetime.now(timezone.utc),
            runtime=1,
            memory=1,
        )
    )
    db.commit()

    fetcher = OJFetcher(db)
    fetcher.config.luogu_cookie = "valid-cookie"
    fetcher._resolve_luogu_uid = MethodType(lambda self, uid=None, username=None: "123456", fetcher)
    fetcher._fetch_luogu_practice_solved = MethodType(
        lambda self, uid: [
            {"problem_id": "P1001", "problem_name": "A+B Problem"},
            {"problem_id": "P1002", "problem_name": "过河卒"},
        ],
        fetcher,
    )
    fetcher._fetch_all_luogu_records = MethodType(lambda self, uid, force_full=True: [], fetcher)
    fetcher._fetch_luogu_problem_meta = MethodType(
        lambda self, pid: {"difficulty": "入门", "tags": ["math"]},
        fetcher,
    )

    result = fetcher.fetch_luogu_submissions(uid="123456", force_full=False)
    assert len(result) == 2
    assert {item["problem_id"] for item in result} == {"P1001", "P1002"}


def test_luogu_sync_requires_cookie():
    db = build_session()
    fetcher = OJFetcher(db)
    fetcher.config.luogu_uid = "123456"
    fetcher.config.luogu_cookie = None

    try:
        fetcher.fetch_luogu_submissions(uid="123456")
    except ValueError as exc:
        assert "valid Luogu cookie" in str(exc)
    else:
        raise AssertionError("Expected Luogu sync to require cookie")


def test_normalize_tags_preserves_multiple_knowledge_points():
    tags = normalize_tags(["dp", "graphs", "shortest paths", "implementation", "模拟", "最短路"])
    assert tags == ["动态规划", "图论", "最短路", "模拟"]


def test_normalize_tags_ignores_metadata_and_only_falls_back_when_needed():
    assert normalize_tags(["动态规划", "NOIP", "2012", "模板"]) == ["动态规划"]
    assert normalize_tags(["蓝桥杯", "2024", "NOIP"]) == []
    assert normalize_tags(["冷门专题"]) == ["冷门专题"]


def test_normalize_tags_drops_nowcoder_platform_label():
    assert normalize_tags(["牛客", "dp"]) == ["动态规划"]
    assert normalize_tags(["牛客"]) == []


def test_tags_for_knowledge_stats_strips_stored_platform_tags():
    assert tags_for_knowledge_stats(["牛客", "动态规划"]) == ["动态规划"]
    assert tags_for_knowledge_stats(["Nowcoder"]) == []
    assert tags_for_knowledge_stats(["牛客·0–400", "数学"]) == ["数学"]


def test_luogu_record_payload_parsing_and_numeric_status():
    db = build_session()
    fetcher = OJFetcher(db)
    payload = {
        "code": 200,
        "currentTemplate": "RecordList",
        "currentData": {
            "records": {
                "result": [
                    {
                        "id": 271614846,
                        "status": 12,
                        "submitTime": 1775134574,
                        "time": 169,
                        "memory": 8248,
                        "problem": {"pid": "P6863", "title": "上下求索"},
                    }
                ]
            }
        },
    }

    records = fetcher._extract_luogu_json_records(payload)
    assert len(records) == 1
    assert records[0]["problem_id"] == "P6863"
    assert fetcher._normalize_status(records[0]["status"]) == "AC"


def test_luogu_problem_meta_falls_back_from_requests_to_urllib():
    db = build_session()
    fetcher = OJFetcher(db)
    fetcher._load_luogu_tag_map = MethodType(lambda self: {1: "模拟", 3: "动态规划 DP"}, fetcher)
    fetcher._get = MethodType(lambda self, url, **kwargs: (_ for _ in ()).throw(requests.HTTPError("403")), fetcher)
    fetcher._get_luogu_html_via_urllib = MethodType(
        lambda self, path: (
            '<script id="lentille-context" type="application/json">'
            '{"data":{"problem":{"pid":"P1001","difficulty":1,"tags":[1,3]}}}'
            '</script>'
        ),
        fetcher,
    )

    meta = fetcher._fetch_luogu_problem_meta("P1001")
    assert meta["difficulty"] == "入门"
    assert "构造与模拟" in meta["tags"] or "动态规划" in meta["tags"]


def test_luogu_problem_meta_prefers_content_only_json():
    db = build_session()
    fetcher = OJFetcher(db)
    fetcher._load_luogu_tag_map = MethodType(lambda self: {1: "模拟", 3: "动态规划 DP"}, fetcher)
    fetcher._get_luogu_json = MethodType(
        lambda self, path: {
            "data": {
                "problem": {
                    "pid": "P1001",
                    "title": "A+B Problem",
                    "difficulty": 1,
                    "tags": [1, 3],
                }
            }
        },
        fetcher,
    )

    meta = fetcher._fetch_luogu_problem_meta("P1001")
    assert meta["title"] == "A+B Problem"
    assert meta["difficulty"] == "入门"
    assert meta["tags"] == ["模拟", "动态规划"]


def test_luogu_sync_summary_keeps_diagnostics():
    db = build_session()
    fetcher = OJFetcher(db)
    fetcher.config.luogu_cookie = "valid-cookie"
    fetcher._last_luogu_diagnostics = {"resolved_uid": "123", "solved_count": 2, "record_count": 2, "matched_ac_time_count": 1}
    inserted, skipped, unknown, updated = fetcher._save_submissions(
        [
            {
                "oj_source": "luogu",
                "problem_id": "P1001",
                "problem_name": "A+B Problem",
                "difficulty": "1",
                "tags": ["数学"],
                "status": "AC",
                "submit_time": None,
                "runtime": None,
                "memory": None,
            }
        ]
    )
    assert inserted == 1
    assert skipped == 0
    assert unknown == 1
    assert updated == 0


def test_luogu_save_updates_existing_missing_time():
    db = build_session()
    db.add(
        Submission(
            oj_source="luogu",
            problem_id="P1001",
            problem_name="A+B Problem",
            difficulty="1",
            tags='["数学"]',
            status="AC",
            submit_time=None,
            runtime=None,
            memory=None,
        )
    )
    db.commit()

    fetcher = OJFetcher(db)
    inserted, skipped, unknown, updated = fetcher._save_submissions(
        [
            {
                "oj_source": "luogu",
                "problem_id": "P1001",
                "problem_name": "A+B Problem",
                "difficulty": "1",
                "tags": ["数学"],
                "status": "AC",
                "submit_time": datetime.fromtimestamp(1710000000, tz=timezone.utc),
                "runtime": 10,
                "memory": 100,
            }
        ]
    )
    row = db.execute(select(Submission).where(Submission.problem_id == "P1001")).scalar_one()
    assert inserted == 0
    assert updated == 1
    assert row.submit_time is not None


def test_tag_distribution_skips_untagged_and_unsolved_list_works():
    db = build_session()
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            Submission(
                oj_source="luogu",
                problem_id="P1001",
                problem_name="A+B Problem",
                difficulty="1",
                tags="[]",
                status="AC",
                submit_time=now,
                runtime=1,
                memory=1,
            ),
            Submission(
                oj_source="codeforces",
                problem_id="100A",
                problem_name="Problem A",
                difficulty="1200",
                tags='["动态规划"]',
                status="WA",
                submit_time=now,
                runtime=1,
                memory=1,
            ),
        ]
    )
    db.commit()

    tags = get_tag_distribution(db)
    unsolved = list_unsolved_problems(db)
    assert tags == [{"tag": "未标注", "count": 1}]
    assert len(unsolved) == 1
    assert unsolved[0]["problem_id"] == "100A"


def test_luogu_fetch_includes_unsolved_latest_record():
    db = build_session()
    fetcher = OJFetcher(db)
    fetcher.config.luogu_cookie = "valid-cookie"
    fetcher._resolve_luogu_uid = MethodType(lambda self, uid=None, username=None: "123456", fetcher)
    fetcher._fetch_luogu_practice_solved = MethodType(
        lambda self, uid: [{"problem_id": "P1001", "problem_name": "A+B Problem"}],
        fetcher,
    )
    fetcher._fetch_all_luogu_records = MethodType(
        lambda self, uid, force_full=True: [
            {"problem_id": "P1001", "problem_name": "A+B Problem", "status": "AC", "submit_time": 1710000000},
            {"problem_id": "P1002", "problem_name": "过河卒", "status": "WA", "submit_time": 1710000100},
        ],
        fetcher,
    )
    fetcher._fetch_luogu_problem_meta = MethodType(
        lambda self, pid: {"difficulty": "1", "tags": ["动态规划"]},
        fetcher,
    )

    result = fetcher.fetch_luogu_submissions(uid="123456", force_full=True)
    assert {item["problem_id"] for item in result} == {"P1001", "P1002"}
    unsolved = next(item for item in result if item["problem_id"] == "P1002")
    assert unsolved["status"] == "WA"


def test_luogu_save_updates_unknown_unsolved_status_and_tags():
    db = build_session()
    db.add(
        Submission(
            oj_source="luogu",
            problem_id="P1002",
            problem_name="过河卒",
            difficulty="1",
            tags="[]",
            status="UNKNOWN",
            submit_time=datetime.fromtimestamp(1710000100, tz=timezone.utc),
            runtime=None,
            memory=None,
        )
    )
    db.commit()

    fetcher = OJFetcher(db)
    inserted, skipped, unknown, updated = fetcher._save_submissions(
        [
            {
                "oj_source": "luogu",
                "problem_id": "P1002",
                "problem_name": "过河卒",
                "difficulty": "2",
                "tags": ["动态规划"],
                "status": "WA",
                "submit_time": datetime.fromtimestamp(1710000100, tz=timezone.utc),
                "runtime": 12,
                "memory": 128,
            }
        ]
    )
    row = db.execute(select(Submission).where(Submission.problem_id == "P1002")).scalar_one()
    assert inserted == 0
    assert updated == 1
    assert skipped == 0
    assert unknown == 0
    assert row.status == "WA"
    assert row.tags == '["动态规划"]'


def test_recent_sync_runs_include_local_text_fields():
    db = build_session()
    fetcher = OJFetcher(db)
    run = fetcher._start_sync_run("luogu", True)
    fetcher._finish_sync_run(
        run,
        {"fetched": 1, "inserted": 1, "skipped": 0, "failed_sources": [], "sources": {}},
    )
    rows = list_recent_sync_runs(db, limit=1)
    assert "started_at_text" in rows[0]


def test_recent_sync_runs_convert_naive_utc_to_beijing_time():
    db = build_session()
    fetcher = OJFetcher(db)
    run = fetcher._start_sync_run("luogu", True)
    run.started_at = datetime(2026, 4, 2, 14, 47, 12)
    run.finished_at = datetime(2026, 4, 2, 14, 49, 3)
    db.add(run)
    db.commit()

    rows = list_recent_sync_runs(db, limit=1)
    assert rows[0]["started_at_text"] == "2026/04/02 22:47:12"
    assert rows[0]["finished_at_text"] == "2026/04/02 22:49:03"


def test_period_stats_and_tag_problem_listing():
    db = build_session()
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            Submission(
                oj_source="codeforces",
                problem_id="300A",
                problem_name="CF A",
                difficulty="1200",
                tags='["动态规划"]',
                status="AC",
                submit_time=now,
                runtime=10,
                memory=10,
            ),
            Submission(
                oj_source="luogu",
                problem_id="P1001",
                problem_name="A+B Problem",
                difficulty="入门",
                tags='["动态规划","数学"]',
                status="AC",
                submit_time=now,
                runtime=10,
                memory=10,
            ),
        ]
    )
    db.commit()

    stats = get_period_stats(db, "day", now=now)
    problems = list_tag_problems(db, "动态规划")

    assert stats["ac_count"] == 2
    assert stats["attempt_count"] == 2
    assert len(problems) == 2


def test_existing_tag_options_and_non_luogu_updates():
    db = build_session()
    existing = Submission(
        oj_source="codeforces",
        problem_id="100A",
        problem_name="Problem A",
        difficulty="1200",
        tags='["动态规划"]',
        status="AC",
        submit_time=datetime.fromtimestamp(1710000000, tz=timezone.utc),
        runtime=10,
        memory=10,
    )
    db.add(existing)
    db.commit()

    fetcher = OJFetcher(db)
    inserted, skipped, unknown, updated = fetcher._save_submissions(
        [
            {
                "oj_source": "codeforces",
                "problem_id": "100A",
                "problem_name": "Problem A",
                "difficulty": "1300",
                "tags": ["动态规划", "最短路"],
                "status": "AC",
                "submit_time": datetime.fromtimestamp(1710000000, tz=timezone.utc),
                "runtime": 11,
                "memory": 12,
            }
        ]
    )

    assert inserted == 0
    assert skipped == 0
    assert unknown == 0
    assert updated == 1
    options = list_existing_tags(db)
    assert any(item["tag"] == "动态规划" for item in options)
    assert any(item["tag"] == "最短路" for item in options)
