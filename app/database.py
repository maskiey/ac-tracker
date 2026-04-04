from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent


def _data_dir() -> Path:
    override = os.getenv("ACM_TRACKER_DATA_DIR")
    if override:
        d = Path(override)
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = BASE_DIR / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_DIR = _data_dir()
DEFAULT_DB_PATH = DATA_DIR / "submissions.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")


class Base(DeclarativeBase):
    pass


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint(
            "oj_source",
            "problem_id",
            "status",
            "submit_time",
            name="uq_submission_dedup",
        ),
        Index("ix_submission_source_problem", "oj_source", "problem_id"),
        Index("ix_submission_submit_time", "submit_time"),
        Index("ix_submission_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    oj_source: Mapped[str] = mapped_column(String(32), nullable=False)
    problem_id: Mapped[str] = mapped_column(String(64), nullable=False)
    problem_name: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    runtime: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    memory: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    """聚合评测来源写入为 True；同题已有直连 AC 时不写入或随后被清理。"""
    via_vjudge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def tag_list(self) -> list[str]:
        if not self.tags:
            return []
        try:
            value = json.loads(self.tags)
            if isinstance(value, list):
                return [str(item) for item in value if item]
        except json.JSONDecodeError:
            pass
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("ix_sync_run_started_at", "started_at"),
        Index("ix_sync_run_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="all")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="incremental")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_sources: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_nullable_submit_time()
    _migrate_via_vjudge_column()


def _migrate_nullable_submit_time() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "submissions" not in inspector.get_table_names():
        return

    columns = inspector.get_columns("submissions")
    submit_time_column = next((column for column in columns if column["name"] == "submit_time"), None)
    if submit_time_column is None or submit_time_column.get("nullable", True):
        return

    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE submissions RENAME TO submissions_old")
        Base.metadata.create_all(bind=conn)
        conn.execute(
            text(
                """
                INSERT INTO submissions (
                    id, oj_source, problem_id, problem_name, difficulty,
                    tags, status, submit_time, runtime, memory
                )
                SELECT
                    id, oj_source, problem_id, problem_name, difficulty,
                    tags, status, submit_time, runtime, memory
                FROM submissions_old
                """
            )
        )
        conn.exec_driver_sql("DROP TABLE submissions_old")


def _migrate_via_vjudge_column() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "submissions" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("submissions")}
    if "via_vjudge" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE submissions ADD COLUMN via_vjudge BOOLEAN NOT NULL DEFAULT 0"))
