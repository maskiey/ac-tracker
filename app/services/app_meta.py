from __future__ import annotations

import os
import threading
import time
from typing import Any

import requests
from packaging.version import InvalidVersion, Version

from app.version import (
    APP_NAME_FULL,
    APP_VERSION,
    GITHUB_RELEASES_LATEST_URL,
    GITHUB_REPO_URL,
    GITHUB_API_LATEST_RELEASE,
)

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {}

# 减轻对 GitHub API 的压力（未认证约 60 次/小时/出口 IP）
_UPDATE_CHECK_TTL_SEC = 300.0


def _parse_version(s: str | None) -> Version | None:
    if not s:
        return None
    s = s.strip().lstrip("vV")
    if not s:
        return None
    try:
        return Version(s)
    except InvalidVersion:
        return None


def _fetch_latest_release_tag() -> tuple[str | None, str | None]:
    """返回 (tag_name 如 v1.0.12, 错误说明)。成功时错误为 None。"""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"AC-Tracker/{APP_VERSION}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        r = requests.get(GITHUB_API_LATEST_RELEASE, headers=headers, timeout=10)
        if r.status_code == 404:
            return None, "releases_not_found"
        r.raise_for_status()
        data = r.json()
        tag = data.get("tag_name") or data.get("name")
        if not tag:
            return None, "no_tag_in_response"
        return str(tag), None
    except requests.RequestException as exc:
        return None, str(exc)[:240]


def get_update_check_payload() -> dict[str, Any]:
    """供 /api/app/update-check 使用；带短时缓存。"""
    if os.getenv("ACM_TRACKER_DISABLE_UPDATE_CHECK", "").strip().lower() in ("1", "true", "yes", "on"):
        return {
            "update_check_enabled": False,
            "current_version": APP_VERSION,
            "update_available": False,
        }

    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get("update")
        if cached and now - float(cached.get("_ts", 0)) < _UPDATE_CHECK_TTL_SEC:
            out = {k: v for k, v in cached.items() if k != "_ts"}
            return out

    tag, err = _fetch_latest_release_tag()
    current_v = _parse_version(APP_VERSION)
    remote_v = _parse_version(tag)

    update_available = bool(
        current_v and remote_v and remote_v > current_v
    )

    latest_display = tag.lstrip("vV") if tag else None

    payload: dict[str, Any] = {
        "update_check_enabled": True,
        "current_version": APP_VERSION,
        "latest_version": latest_display,
        "latest_tag": tag,
        "release_url": GITHUB_RELEASES_LATEST_URL,
        "update_available": update_available,
        "check_error": err is not None,
        "check_message": err,
    }

    with _CACHE_LOCK:
        _CACHE["update"] = {**payload, "_ts": now}

    return payload


def get_about_payload() -> dict[str, Any]:
    return {
        "name": APP_NAME_FULL,
        "version": APP_VERSION,
        "repo_url": GITHUB_REPO_URL,
        "releases_url": GITHUB_RELEASES_LATEST_URL,
        "license": "MIT",
        "license_url": f"{GITHUB_REPO_URL}/blob/main/LICENSE",
        "description": "自托管刷题记录可视化：本地 SQLite，多平台同步，热力图与统计。",
        "third_party": [
            {"name": "FastAPI / Starlette / Uvicorn", "note": "服务端框架"},
            {"name": "SQLAlchemy", "note": "数据库 ORM"},
            {"name": "Apache ECharts", "note": "图表（jsDelivr CDN）"},
            {"name": "各 OJ 公开接口与页面", "note": "数据来源；本项目与官方站点无隶属关系"},
        ],
    }
