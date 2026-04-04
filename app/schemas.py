from __future__ import annotations

from pydantic import BaseModel, Field


class SyncRequest(BaseModel):
    source: str | None = Field(
        default=None,
        description="codeforces, luogu, nowcoder, atcoder, or omitted for all",
    )
    force_full: bool = False


class ConfigPayload(BaseModel):
    codeforces_handle: str | None = None
    codeforces_cookie_kv: str | None = None
    luogu_uid: str | None = None
    luogu_username: str | None = None
    luogu_ck_client_id: str | None = None
    luogu_ck_uid: str | None = None
    luogu_cookie_kv: str | None = None
    nowcoder_uid: str | None = None
    nowcoder_cookie_kv: str | None = None
    atcoder_username: str | None = None
    sync_interval_minutes: int = 0


class ProblemDetail(BaseModel):
    problem_id: str
    problem_name: str
    oj_source: str
    difficulty: str | None = None
    status: str
    submit_time: str | None = None


class HeatmapDay(BaseModel):
    date: str
    ac_count: int
    problems: list[ProblemDetail]


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
    highlights: list[str]
    weaknesses: list[str]
    suggestion: str


class SyncRunItem(BaseModel):
    id: int
    source: str
    mode: str
    status: str
    started_at: str
    finished_at: str | None = None
    fetched_count: int
    inserted_count: int
    skipped_count: int
    failed_sources: list[str]
    detail: dict
