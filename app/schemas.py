from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SyncRequest(BaseModel):
    source: Optional[str] = Field(
        default=None,
        description="codeforces, luogu, nowcoder, atcoder, or omitted for all",
    )
    force_full: bool = False


class ConfigPayload(BaseModel):
    codeforces_handle: Optional[str] = None
    codeforces_cookie_kv: Optional[str] = None
    luogu_uid: Optional[str] = None
    luogu_username: Optional[str] = None
    luogu_ck_client_id: Optional[str] = None
    luogu_ck_uid: Optional[str] = None
    luogu_cookie_kv: Optional[str] = None
    nowcoder_uid: Optional[str] = None
    nowcoder_cookie_kv: Optional[str] = None
    atcoder_username: Optional[str] = None
    sync_interval_minutes: int = 0


class ProblemDetail(BaseModel):
    problem_id: str
    problem_name: str
    oj_source: str
    difficulty: Optional[str] = None
    status: str
    submit_time: Optional[str] = None


class HeatmapDay(BaseModel):
    date: str
    ac_count: int
    problems: List[ProblemDetail]


class WeeklyStats(BaseModel):
    week_start: str
    week_end: str
    ac_count: int
    attempt_count: int
    accuracy: float


class TagStat(BaseModel):
    tag: str
    count: int


class WeeklyReport(BaseModel):
    summary: str
    highlights: List[str]
    weaknesses: List[str]
    suggestion: str


class SyncRunItem(BaseModel):
    id: int
    source: str
    mode: str
    status: str
    started_at: str
    finished_at: Optional[str] = None
    fetched_count: int
    inserted_count: int
    skipped_count: int
    failed_sources: List[str]
    detail: Dict[str, Any]
