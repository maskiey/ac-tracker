from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database import Submission, SyncRun
from app.services.difficulty_display import format_difficulty_display
from app.services.tags import knowledge_tags_with_fallback


BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _as_beijing(dt: datetime | None) -> datetime | None:
    normalized = _as_utc(dt)
    return normalized.astimezone(BEIJING_TZ) if normalized else None


_MIN_UTC = datetime.min.replace(tzinfo=timezone.utc)


def _prefer_ac_submissions(rows: Iterable[Submission]) -> list[Submission]:
    """同一题多条 AC 时保留直连记录，否则保留一条（与入库时 VJ 退让策略一致）。"""
    buckets: dict[tuple[str, str], list[Submission]] = defaultdict(list)
    for row in rows:
        if row.status != "AC":
            continue
        buckets[(row.oj_source, row.problem_id)].append(row)
    out: list[Submission] = []
    for group in buckets.values():
        out.append(
            max(
                group,
                key=lambda r: (
                    not getattr(r, "via_vjudge", False),
                    r.submit_time or _MIN_UTC,
                    r.id,
                ),
            )
        )
    return out


def _period_bounds(period: str, current: datetime | None = None) -> tuple[datetime, datetime]:
    now = (current or _utc_now()).astimezone(BEIJING_TZ)
    period = period.lower()

    if period == "day":
        start_local = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
        end_local = start_local + timedelta(days=1)
    elif period == "week":
        start_date = now.date() - timedelta(days=now.weekday())
        start_local = datetime.combine(start_date, time.min, tzinfo=now.tzinfo)
        end_local = start_local + timedelta(days=7)
    elif period == "month":
        start_local = datetime(now.year, now.month, 1, tzinfo=now.tzinfo)
        if now.month == 12:
            end_local = datetime(now.year + 1, 1, 1, tzinfo=now.tzinfo)
        else:
            end_local = datetime(now.year, now.month + 1, 1, tzinfo=now.tzinfo)
    elif period == "year":
        start_local = datetime(now.year, 1, 1, tzinfo=now.tzinfo)
        end_local = datetime(now.year + 1, 1, 1, tzinfo=now.tzinfo)
    else:
        raise ValueError(f"Unsupported period: {period}")

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def get_year_heatmap(db: Session, year: int) -> list[dict]:
    start = datetime(year, 1, 1, tzinfo=BEIJING_TZ).astimezone(timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=BEIJING_TZ).astimezone(timezone.utc)

    stmt = (
        select(Submission)
        .where(
            Submission.status == "AC",
            Submission.submit_time.is_not(None),
            Submission.submit_time >= start,
            Submission.submit_time < end,
        )
        .order_by(Submission.submit_time.asc())
    )
    rows = db.execute(stmt).scalars().all()
    rows = _prefer_ac_submissions(rows)

    bucket: dict[str, dict] = {}
    for row in rows:
        submit_time = _as_beijing(row.submit_time)
        if submit_time is None:
            continue
        date_key = submit_time.date().isoformat()
        day = bucket.setdefault(date_key, {"date": date_key, "ac_count": 0, "problems": []})
        day["ac_count"] += 1
        day["problems"].append(
            {
                "problem_id": row.problem_id,
                "problem_name": row.problem_name,
                "oj_source": row.oj_source,
                "difficulty": format_difficulty_display(row.oj_source, row.difficulty),
                "status": row.status,
                "submit_time": submit_time.isoformat(),
            }
        )

    return sorted(bucket.values(), key=lambda x: x["date"])


def get_weekly_stats(db: Session, now: datetime | None = None) -> dict:
    return get_period_stats(db, "week", now=now)


def get_period_stats(db: Session, period: str, now: datetime | None = None) -> dict:
    start, end = _period_bounds(period, now)
    stmt = select(Submission).where(
        Submission.submit_time.is_not(None),
        Submission.submit_time >= start,
        Submission.submit_time < end,
    )
    rows = db.execute(stmt).scalars().all()

    attempt_count = len(rows)
    ac_count = sum(1 for row in rows if row.status == "AC")
    accuracy = round((ac_count / attempt_count) * 100, 2) if attempt_count else 0.0

    return {
        "period": period,
        "start": start.astimezone(BEIJING_TZ).date().isoformat(),
        "end": (end - timedelta(days=1)).astimezone(BEIJING_TZ).date().isoformat(),
        "ac_count": ac_count,
        "attempt_count": attempt_count,
        "accuracy": accuracy,
    }


def get_tag_distribution(db: Session, limit: int = 12, oj_source: str | None = None) -> list[dict]:
    stmt = select(Submission).where(Submission.status == "AC")
    if oj_source:
        stmt = stmt.where(Submission.oj_source == oj_source.strip())
    stmt = stmt.order_by(desc(Submission.submit_time))
    rows = db.execute(stmt).scalars().all()
    rows = _prefer_ac_submissions(rows)

    counter: Counter[str] = Counter()
    for row in rows:
        for tag in knowledge_tags_with_fallback(row.tag_list()):
            counter[tag] += 1

    return [{"tag": tag, "count": count} for tag, count in counter.most_common(limit)]


def list_tag_problems(db: Session, tag: str, limit: int = 200, oj_source: str | None = None) -> list[dict]:
    stmt = select(Submission).where(Submission.status == "AC")
    if oj_source:
        stmt = stmt.where(Submission.oj_source == oj_source.strip())
    stmt = stmt.order_by(
        Submission.via_vjudge.asc(),
        desc(Submission.submit_time),
        desc(Submission.id),
    )
    rows = db.execute(stmt).scalars().all()

    seen: set[tuple[str, str]] = set()
    result: list[dict] = []
    for row in rows:
        if tag not in knowledge_tags_with_fallback(row.tag_list()):
            continue
        key = (row.oj_source, row.problem_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "oj_source": row.oj_source,
                "problem_id": row.problem_id,
                "problem_name": row.problem_name,
                "difficulty": format_difficulty_display(row.oj_source, row.difficulty),
                "status": row.status,
                "submit_time": _as_beijing(row.submit_time).isoformat() if row.submit_time else None,
                "tags": knowledge_tags_with_fallback(row.tag_list()),
            }
        )
        if len(result) >= limit:
            break
    return result


def get_daily_problem_lookup(db: Session, date_str: str) -> list[dict]:
    target_date = datetime.fromisoformat(date_str).date()
    stmt = select(Submission).where(Submission.status == "AC")
    rows = db.execute(stmt).scalars().all()
    rows = _prefer_ac_submissions(rows)

    problems = []
    for row in rows:
        if row.submit_time is None:
            continue
        submit_time = _as_beijing(row.submit_time)
        if submit_time and submit_time.date() == target_date:
            problems.append(
                {
                    "problem_id": row.problem_id,
                    "problem_name": row.problem_name,
                    "oj_source": row.oj_source,
                    "difficulty": format_difficulty_display(row.oj_source, row.difficulty),
                    "status": row.status,
                    "submit_time": submit_time.isoformat(),
                }
            )
    return problems


def list_unsolved_problems(db: Session, limit: int = 200, oj_source: str | None = None) -> list[dict]:
    stmt = select(Submission).order_by(desc(Submission.submit_time), desc(Submission.id))
    rows = db.execute(stmt).scalars().all()

    oj_filter = oj_source.strip() if oj_source else None

    solved_keys = {
        (row.oj_source, row.problem_id)
        for row in rows
        if row.status == "AC" and (not oj_filter or row.oj_source == oj_filter)
    }
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if oj_filter and row.oj_source != oj_filter:
            continue
        key = (row.oj_source, row.problem_id)
        if key in solved_keys or key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "oj_source": row.oj_source,
                "problem_id": row.problem_id,
                "problem_name": row.problem_name,
                "difficulty": format_difficulty_display(row.oj_source, row.difficulty),
                "status": row.status,
                "submit_time": _as_beijing(row.submit_time).isoformat() if row.submit_time else None,
                "tags": knowledge_tags_with_fallback(row.tag_list()),
            }
        )
        if len(result) >= limit:
            break
    return result


def get_source_breakdown(db: Session) -> list[dict]:
    stmt = select(Submission)
    rows = db.execute(stmt).scalars().all()
    counter = defaultdict(int)
    for row in rows:
        counter[row.oj_source] += 1
    return [{"source": source, "count": count} for source, count in sorted(counter.items())]


def repair_stuck_sync_runs(db: Session) -> int:
    """将未正常结束的 running 记录标为 interrupted（进程崩溃或请求超时后仍留在库中）。"""
    stmt = select(SyncRun).where(SyncRun.status == "running", SyncRun.finished_at.is_(None))
    rows = db.execute(stmt).scalars().all()
    now = _utc_now()
    for row in rows:
        row.status = "interrupted"
        row.finished_at = now
    if rows:
        db.commit()
    return len(rows)


def get_dashboard_summary(db: Session) -> dict:
    stmt = select(Submission).order_by(desc(Submission.submit_time))
    rows = db.execute(stmt).scalars().all()
    total_submissions = len(rows)
    total_ac = sum(1 for row in rows if row.status == "AC")
    active_days = len({_as_beijing(row.submit_time).date().isoformat() for row in rows if row.submit_time})

    sync_stmt = (
        select(SyncRun).where(SyncRun.finished_at.isnot(None)).order_by(desc(SyncRun.finished_at)).limit(1)
    )
    last_sync = db.execute(sync_stmt).scalar_one_or_none()
    last_sync_finished = _as_beijing(last_sync.finished_at) if last_sync else None

    return {
        "total_submissions": total_submissions,
        "total_ac": total_ac,
        "active_days": active_days,
        "last_sync_at": last_sync_finished.isoformat() if last_sync_finished else None,
        "last_sync_text": last_sync_finished.strftime("%Y/%m/%d %H:%M:%S") if last_sync_finished else None,
        "last_sync_status": last_sync.status if last_sync else None,
    }


def list_recent_sync_runs(db: Session, limit: int = 10) -> list[dict]:
    stmt = select(SyncRun).order_by(desc(SyncRun.started_at)).limit(limit)
    rows = db.execute(stmt).scalars().all()
    result = []
    for row in rows:
        started_at = _as_beijing(row.started_at)
        finished_at = _as_beijing(row.finished_at)
        result.append(
            {
                "id": row.id,
                "source": row.source,
                "mode": row.mode,
                "status": row.status,
                "started_at": started_at.isoformat() if started_at else None,
                "finished_at": finished_at.isoformat() if finished_at else None,
                "started_at_text": started_at.strftime("%Y/%m/%d %H:%M:%S") if started_at else None,
                "finished_at_text": finished_at.strftime("%Y/%m/%d %H:%M:%S") if finished_at else None,
                "fetched_count": row.fetched_count,
                "inserted_count": row.inserted_count,
                "skipped_count": row.skipped_count,
                "failed_sources": __import__("json").loads(row.failed_sources or "[]"),
                "detail": __import__("json").loads(row.detail or "{}"),
            }
        )
    return result


def list_existing_tags(db: Session, query: str = "", limit: int = 200, oj_source: str | None = None) -> list[dict]:
    stmt = select(Submission)
    rows = db.execute(stmt).scalars().all()

    counter: Counter[str] = Counter()
    needle = query.strip().lower()
    oj_filter = oj_source.strip() if oj_source else None
    ac_for_pref = [r for r in rows if r.status == "AC" and (not oj_filter or r.oj_source == oj_filter)]
    preferred_ac_keys = {(r.oj_source, r.problem_id) for r in _prefer_ac_submissions(ac_for_pref)}
    for row in rows:
        if oj_filter and row.oj_source != oj_filter:
            continue
        if row.status == "AC" and (row.oj_source, row.problem_id) not in preferred_ac_keys:
            continue
        for tag in knowledge_tags_with_fallback(row.tag_list()):
            if needle and needle not in tag.lower():
                continue
            counter[tag] += 1

    return [{"tag": tag, "count": count} for tag, count in counter.most_common(limit)]
