from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Dict, Optional

from dotenv import dotenv_values, load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.cookie_merge import (
    cookie_get,
    cookie_to_kv_lines,
    kv_lines_excluding,
    merge_kv_cookie,
    merge_luogu_cookie,
    parse_cookie_header,
)
from app.version import APP_VERSION
from app.database import SessionLocal, init_db
from app.fetcher import FetcherConfig, OJFetcher
from app.schemas import ConfigPayload, SyncRequest
from app.services.app_meta import get_about_payload, get_update_check_payload
from app.services.report import generate_weekly_report
from app.services.stats import (
    get_daily_problem_lookup,
    get_dashboard_summary,
    get_period_stats,
    get_source_breakdown,
    get_tag_distribution,
    get_weekly_stats,
    get_year_heatmap,
    list_existing_tags,
    list_recent_sync_runs,
    list_tag_problems,
    list_unsolved_problems,
    repair_stuck_sync_runs,
)


BASE_DIR = Path(__file__).resolve().parent


def _env_path() -> Path:
    override = os.getenv("ACM_TRACKER_ENV_FILE")
    if override:
        return Path(override)
    return BASE_DIR.parent / ".env"


ENV_PATH = _env_path()
load_dotenv(ENV_PATH)

app = FastAPI(title="AC Tracker · 刷题轨迹", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
poller_thread: Optional[threading.Thread] = None
poller_stop_event = threading.Event()


def load_runtime_config() -> Dict[str, str]:
    values = dotenv_values(ENV_PATH)
    return {str(key): str(value) for key, value in values.items() if value is not None}


def persist_runtime_config(payload: ConfigPayload) -> None:
    existing = load_runtime_config()
    updates = {
        "CODEFORCES_HANDLE": payload.codeforces_handle or "",
        "CODEFORCES_COOKIE": merge_kv_cookie(payload.codeforces_cookie_kv),
        "LUOGU_UID": payload.luogu_uid or "",
        "LUOGU_USERNAME": payload.luogu_username or "",
        "LUOGU_COOKIE": merge_luogu_cookie(
            payload.luogu_ck_client_id,
            payload.luogu_ck_uid,
            payload.luogu_cookie_kv,
        ),
        "NOWCODER_UID": payload.nowcoder_uid or "",
        "NOWCODER_COOKIE": merge_kv_cookie(payload.nowcoder_cookie_kv),
        "ATCODER_USERNAME": payload.atcoder_username or "",
        "SYNC_INTERVAL_MINUTES": str(max(payload.sync_interval_minutes, 0)),
        # 已移除 QOJ / VJ 同步；写入空值以清理旧 .env
        "QOJ_USERNAME": "",
        "QOJ_BASE_URL": "",
        "QOJ_COOKIE": "",
        "VJUDGE_USERNAME": "",
    }
    merged = {**existing, **updates}
    lines = [f"{key}={value}" for key, value in merged.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key, value in merged.items():
        os.environ[key] = value


def public_config() -> dict:
    values = load_runtime_config()
    lg_parts = parse_cookie_header(values.get("LUOGU_COOKIE", ""))
    cf_cookie = values.get("CODEFORCES_COOKIE", "")
    nc_cookie = values.get("NOWCODER_COOKIE", "")
    return {
        "codeforces_handle": values.get("CODEFORCES_HANDLE", ""),
        "codeforces_cookie_kv": cookie_to_kv_lines(cf_cookie),
        "luogu_uid": values.get("LUOGU_UID", ""),
        "luogu_username": values.get("LUOGU_USERNAME", ""),
        "luogu_ck_client_id": cookie_get(lg_parts, "__client_id"),
        "luogu_ck_uid": cookie_get(lg_parts, "_uid"),
        "luogu_cookie_kv": kv_lines_excluding(lg_parts, ("__client_id", "_uid")),
        "sync_interval_minutes": int(values.get("SYNC_INTERVAL_MINUTES", "0") or 0),
        "nowcoder_uid": values.get("NOWCODER_UID", ""),
        "nowcoder_cookie_kv": cookie_to_kv_lines(nc_cookie),
        "atcoder_username": values.get("ATCODER_USERNAME", ""),
        "configured_sources": [
            source
            for source, enabled in (
                ("codeforces", bool(values.get("CODEFORCES_HANDLE", "").strip())),
                (
                    "luogu",
                    bool(values.get("LUOGU_COOKIE", "").strip())
                    and bool(values.get("LUOGU_UID", "").strip() or values.get("LUOGU_USERNAME", "").strip()),
                ),
                ("nowcoder", bool(values.get("NOWCODER_UID", "").strip())),
                ("atcoder", bool(values.get("ATCODER_USERNAME", "").strip())),
            )
            if enabled
        ],
        "has_codeforces_cookie": bool(values.get("CODEFORCES_COOKIE")),
        "has_luogu_cookie": bool(values.get("LUOGU_COOKIE")),
        "has_nowcoder_cookie": bool(values.get("NOWCODER_COOKIE")),
    }


def sync_once(
    source: Optional[str] = None,
    force_full: bool = False,
    *,
    only_configured: bool = False,
) -> dict:
    db = SessionLocal()
    try:
        fetcher = OJFetcher(db, FetcherConfig.from_env())
        return fetcher.sync_all(
            source=source,
            force_full=force_full,
            only_configured=only_configured,
        )
    finally:
        db.close()


def poller_loop() -> None:
    while not poller_stop_event.is_set():
        interval = max(FetcherConfig.from_env().sync_interval_minutes, 0)
        if interval <= 0:
            poller_stop_event.wait(30)
            continue
        try:
            sync_once(force_full=False, only_configured=True)
        except Exception:
            pass
        poller_stop_event.wait(interval * 60)


def ensure_poller_running() -> None:
    global poller_thread
    if poller_thread and poller_thread.is_alive():
        return
    poller_stop_event.clear()
    poller_thread = threading.Thread(target=poller_loop, daemon=True, name="acm-sync-poller")
    poller_thread.start()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        repair_stuck_sync_runs(db)
    finally:
        db.close()
    ensure_poller_running()


@app.on_event("shutdown")
def on_shutdown() -> None:
    poller_stop_event.set()


def render_index(request: Request, default_view: str = "overview"):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "default_year": os.getenv("DEFAULT_HEATMAP_YEAR"),
            "codeforces_handle": os.getenv("CODEFORCES_HANDLE", ""),
            "luogu_uid": os.getenv("LUOGU_UID", ""),
            "default_view": default_view,
        },
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render_index(request, "overview")


@app.get("/heatmap")
def heatmap_page() -> RedirectResponse:
    """热力图已并入主页总览，旧链接重定向到锚点。"""
    return RedirectResponse(url="/#heatmap-section", status_code=307)


@app.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(request: Request):
    return render_index(request, "knowledge")


@app.get("/problems", response_class=HTMLResponse)
def problems_page(request: Request):
    return render_index(request, "problems")


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return render_index(request, "settings")


@app.get("/sync")
def sync_page_redirect() -> RedirectResponse:
    """旧路径「同步」已并入「设置」。"""
    return RedirectResponse(url="/settings", status_code=307)


@app.get("/api/health")
def health():
    return {"success": True, "data": {"status": "ok"}}


@app.get("/api/app/about")
def api_app_about():
    return {"success": True, "data": get_about_payload()}


@app.get("/api/app/update-check")
def api_app_update_check():
    return {"success": True, "data": get_update_check_payload()}


@app.post("/api/sync")
def sync_submissions(payload: SyncRequest, db: Session = Depends(get_db)):
    try:
        fetcher = OJFetcher(db, FetcherConfig.from_env())
        result = fetcher.sync_all(
            source=payload.source,
            force_full=payload.force_full,
            only_configured=payload.only_configured,
        )
        return {"success": True, "data": result}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/sync/repair-stuck")
def sync_repair_stuck(db: Session = Depends(get_db)):
    n = repair_stuck_sync_runs(db)
    return {"success": True, "data": {"repaired": n}}


@app.get("/api/heatmap")
def heatmap(year: Optional[int] = Query(default=None), db: Session = Depends(get_db)):
    selected_year = year or int(os.getenv("DEFAULT_HEATMAP_YEAR", "0") or 0)
    if not selected_year:
        from datetime import datetime

        selected_year = datetime.now().year
    data = get_year_heatmap(db, selected_year)
    return {"success": True, "data": data}


@app.get("/api/stats/weekly")
def weekly_stats(db: Session = Depends(get_db)):
    return {"success": True, "data": get_weekly_stats(db)}


@app.get("/api/stats/period")
def period_stats(period: str = Query(default="week"), db: Session = Depends(get_db)):
    try:
        data = get_period_stats(db, period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": data}


@app.get("/api/stats/tags")
def tag_stats(oj: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    return {"success": True, "data": get_tag_distribution(db, oj_source=oj)}


@app.get("/api/tags/options")
def tag_options(
    q: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=500),
    oj: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    return {"success": True, "data": list_existing_tags(db, query=q, limit=limit, oj_source=oj)}


@app.get("/api/problems/by-tag")
def problems_by_tag(tag: str = Query(...), oj: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    return {"success": True, "data": list_tag_problems(db, tag, oj_source=oj)}


@app.get("/api/problems/by-date")
def problems_by_date(date: str = Query(...), db: Session = Depends(get_db)):
    return {"success": True, "data": get_daily_problem_lookup(db, date)}


@app.get("/api/problems/unsolved")
def unsolved_problems(oj: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    return {"success": True, "data": list_unsolved_problems(db, oj_source=oj)}


@app.get("/api/stats/sources")
def source_stats(db: Session = Depends(get_db)):
    return {"success": True, "data": get_source_breakdown(db)}


@app.get("/api/report/weekly")
def weekly_report(db: Session = Depends(get_db)):
    stats = get_weekly_stats(db)
    tags = get_tag_distribution(db)
    report = generate_weekly_report(stats, tags)
    return {"success": True, "data": report}


@app.get("/api/config")
def read_config():
    return {"success": True, "data": public_config()}


@app.post("/api/config")
def save_config(payload: ConfigPayload):
    persist_runtime_config(payload)
    ensure_poller_running()
    return {"success": True, "data": public_config()}


@app.get("/api/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    return {"success": True, "data": get_dashboard_summary(db)}


@app.get("/api/sync/runs")
def sync_runs(limit: int = Query(default=10, ge=1, le=50), db: Session = Depends(get_db)):
    return {"success": True, "data": list_recent_sync_runs(db, limit=limit)}


@app.get("/api/debug/luogu")
def debug_luogu(
    uid: Optional[str] = Query(default=None),
    username: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    fetcher = OJFetcher(db, FetcherConfig.from_env())
    resolved_uid = fetcher._resolve_luogu_uid(uid=uid, username=username)
    if not resolved_uid:
        raise HTTPException(status_code=404, detail="Unable to resolve Luogu UID")
    solved = fetcher._fetch_luogu_practice_solved(resolved_uid)
    return {
        "success": True,
        "data": {
            "resolved_uid": resolved_uid,
            "solved_count": len(solved),
            "sample": solved[:10],
        },
    }
