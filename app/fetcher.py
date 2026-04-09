from __future__ import annotations

import json
import os
import re
import time
import threading
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from urllib3.util.retry import Retry

from app.database import Submission, SyncRun
from app.services.tags import normalize_tags, tags_for_knowledge_stats


CF_API_BASE = "https://codeforces.com/api"
LUOGU_BASE = "https://www.luogu.com.cn"
# 洛谷题目 difficulty 字段为整数时与题库标签一致（与官网展示一致）
LUOGU_DIFFICULTY_LABEL: dict[int, str] = {
    0: "暂无评定",
    1: "入门",
    2: "普及-",
    3: "普及/提高-",
    4: "普及+/提高",
    5: "提高+/省选-",
    6: "省选/NOI-",
    7: "NOI/NOI+",
    8: "NOI/NOI+",
}
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

STATUS_MAP = {
    "OK": "AC",
    "Accepted": "AC",
    "AC": "AC",
    "Unaccepted": "WA",
    "Partial Correct": "WA",
    "WA": "WA",
    "TLE": "TLE",
    "MLE": "MLE",
    "RE": "RE",
    "CE": "CE",
    "OLE": "OLE",
    "PE": "PE",
    "WRONG_ANSWER": "WA",
    "Wrong answer": "WA",
    "TIME_LIMIT_EXCEEDED": "TLE",
    "Time limit exceeded": "TLE",
    "MEMORY_LIMIT_EXCEEDED": "MLE",
    "Memory limit exceeded": "MLE",
    "RUNTIME_ERROR": "RE",
    "Runtime error": "RE",
    "COMPILATION_ERROR": "CE",
    "Compilation error": "CE",
    "OUTPUT_LIMIT_EXCEEDED": "OLE",
    "Output limit exceeded": "OLE",
    "PRESENTATION_ERROR": "PE",
    "Presentation error": "PE",
    "12": "AC",
    "14": "WA",
}


@dataclass
class FetcherConfig:
    codeforces_handle: str | None = None
    luogu_uid: str | None = None
    luogu_username: str | None = None
    codeforces_cookie: str | None = None
    luogu_cookie: str | None = None
    nowcoder_uid: str | None = None
    nowcoder_cookie: str | None = None
    atcoder_username: str | None = None
    sync_interval_minutes: int = 0
    user_agent: str = DEFAULT_UA
    timeout: int = 20

    @classmethod
    def from_env(cls) -> "FetcherConfig":
        return cls(
            codeforces_handle=os.getenv("CODEFORCES_HANDLE"),
            luogu_uid=os.getenv("LUOGU_UID"),
            luogu_username=os.getenv("LUOGU_USERNAME"),
            codeforces_cookie=os.getenv("CODEFORCES_COOKIE"),
            luogu_cookie=os.getenv("LUOGU_COOKIE"),
            nowcoder_uid=os.getenv("NOWCODER_UID"),
            nowcoder_cookie=os.getenv("NOWCODER_COOKIE"),
            atcoder_username=os.getenv("ATCODER_USERNAME"),
            sync_interval_minutes=int(os.getenv("SYNC_INTERVAL_MINUTES", "0")),
            user_agent=os.getenv("FETCHER_USER_AGENT", DEFAULT_UA),
            timeout=int(os.getenv("FETCHER_TIMEOUT", "20")),
        )


class OJFetcher:
    _sync_lock = threading.Lock()

    def __init__(self, db: Session, config: FetcherConfig | None = None):
        self.db = db
        self.config = config or FetcherConfig.from_env()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.config.user_agent,
                "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
                "Referer": LUOGU_BASE,
            }
        )
        retry = Retry(
            total=3,
            backoff_factor=0.8,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._cf_problem_cache: dict[str, dict[str, Any]] | None = None
        self._luogu_problem_cache: dict[str, dict[str, Any]] = {}
        self._luogu_tag_map: dict[int, str] | None = None
        self._last_luogu_diagnostics: dict[str, Any] = {}

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        headers = kwargs.setdefault("headers", {})
        cookie_parts = []
        if "codeforces.com" in url and self.config.codeforces_cookie:
            cookie_parts.append(self.config.codeforces_cookie)
        if "luogu.com.cn" in url and self.config.luogu_cookie:
            cookie_parts.append(self.config.luogu_cookie)
        if cookie_parts and "Cookie" not in headers:
            headers["Cookie"] = "; ".join(part.strip("; ") for part in cookie_parts if part)
        response = self.session.get(url, timeout=self.config.timeout, **kwargs)
        response.raise_for_status()
        return response

    def _get_luogu_json(self, path: str) -> dict[str, Any]:
        response = self._get(
            f"{LUOGU_BASE}{path}",
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{LUOGU_BASE}/",
                "X-Lentille-Request": "content-only",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        return response.json()

    def _get_luogu_html_via_urllib(self, path: str) -> str:
        headers = {
            "User-Agent": self.config.user_agent,
            "Referer": f"{LUOGU_BASE}/",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        }
        if self.config.luogu_cookie:
            headers["Cookie"] = self.config.luogu_cookie
        request = urllib.request.Request(f"{LUOGU_BASE}{path}", headers=headers)
        with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
            return response.read().decode("utf-8", "ignore")

    def _normalize_status(self, value: Any) -> str:
        if value in (None, ""):
            return "UNKNOWN"
        if isinstance(value, int):
            return STATUS_MAP.get(str(value), "WA")
        text = str(value)
        if text.isdigit():
            return STATUS_MAP.get(text, "WA")
        return STATUS_MAP.get(text, STATUS_MAP.get(text.upper(), "UNKNOWN"))

    def _get_last_submission_time(self, source: str) -> datetime | None:
        stmt = (
            select(Submission.submit_time)
            .where(Submission.oj_source == source)
            .order_by(Submission.submit_time.desc())
            .limit(1)
        )
        value = self.db.execute(stmt).scalar_one_or_none()
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _purge_vjudge_shadowed(self, pairs: set[tuple[str, str]]) -> None:
        """直连已 AC 的题目删除同题的 VJ 占位记录。"""
        for oj, pid in pairs:
            self.db.execute(
                delete(Submission).where(
                    Submission.oj_source == oj,
                    Submission.problem_id == pid,
                    Submission.status == "AC",
                    Submission.via_vjudge.is_(True),
                )
            )

    def _get_existing_ac_problem_ids(self, source: str) -> set[str]:
        stmt = select(Submission.problem_id).where(
            Submission.oj_source == source,
            Submission.status == "AC",
        )
        return {row[0] for row in self.db.execute(stmt).all()}

    def _load_cf_problemset(self) -> dict[str, dict[str, Any]]:
        if self._cf_problem_cache is not None:
            return self._cf_problem_cache

        response = self._get(f"{CF_API_BASE}/problemset.problems", params={"lang": "en"})
        payload = response.json()
        if payload.get("status") != "OK":
            raise ValueError(f"Codeforces problemset error: {payload.get('comment', 'unknown error')}")

        cache: dict[str, dict[str, Any]] = {}
        for problem in payload["result"]["problems"]:
            key = self._cf_problem_key(problem.get("contestId"), problem.get("index"))
            cache[key] = problem
        self._cf_problem_cache = cache
        return cache

    @staticmethod
    def _cf_problem_key(contest_id: Any, index: Any) -> str:
        return f"{contest_id or 'gym'}-{index or ''}"

    def fetch_codeforces_submissions(self, handle: str | None = None) -> list[dict]:
        handle = handle or self.config.codeforces_handle
        if not handle:
            return []

        problemset = self._load_cf_problemset()
        response = self._get(
            f"{CF_API_BASE}/user.status",
            params={"handle": handle, "from": 1, "count": 1000},
        )
        payload = response.json()
        if payload.get("status") != "OK":
            raise ValueError(f"Codeforces user.status error: {payload.get('comment', 'unknown error')}")

        records = []
        for item in payload["result"]:
            problem = item.get("problem", {})
            merged_problem = problemset.get(
                self._cf_problem_key(problem.get("contestId"), problem.get("index")),
                {},
            )
            records.append(
                {
                    "oj_source": "codeforces",
                    "external_submission_id": str(item.get("id")) if item.get("id") is not None else None,
                    "problem_id": f"{problem.get('contestId', 'gym')}{problem.get('index', '')}",
                    "problem_name": problem.get("name") or merged_problem.get("name") or "Unknown Problem",
                    "difficulty": (
                        str(merged_problem.get("rating"))
                        if merged_problem.get("rating") is not None
                        else None
                    ),
                    "tags": normalize_tags(merged_problem.get("tags", []) or problem.get("tags", [])),
                    "status": self._normalize_status(item.get("verdict")),
                    "submit_time": datetime.fromtimestamp(
                        item.get("creationTimeSeconds", 0), tz=timezone.utc
                    ),
                    "runtime": item.get("timeConsumedMillis"),
                    "memory": item.get("memoryConsumedBytes"),
                }
            )
        return records

    @staticmethod
    def _format_luogu_site_difficulty(raw: Any) -> str | None:
        if raw is None:
            return None
        if isinstance(raw, bool):
            return str(raw)
        if isinstance(raw, int):
            return LUOGU_DIFFICULTY_LABEL.get(raw, str(raw))
        s = str(raw).strip()
        if not s:
            return None
        if s.isdigit():
            return LUOGU_DIFFICULTY_LABEL.get(int(s), s)
        return s

    def _extract_json_blob(self, text: str) -> dict[str, Any] | None:
        patterns = [
            r"<script id=\"lentille-context\" type=\"application/json\">(?P<data>\{.+?\})</script>",
            r"JSON\.parse\(decodeURIComponent\(\"(?P<data>.+?)\"\)\)",
            r"decodeURIComponent\(\"(?P<data>.+?)\"\)",
            r"window\.__INITIAL_STATE__\s*=\s*(?P<data>\{.+?\})\s*;",
            r"__NEXT_DATA__\"\s*type=\"application/json\">(?P<data>\{.+?\})</script>",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            raw = match.group("data")
            try:
                if "decodeURIComponent" in pattern:
                    raw = unquote(bytes(raw, "utf-8").decode("unicode_escape"))
                return json.loads(raw)
            except json.JSONDecodeError:
                continue
        return None

    def _fetch_luogu_problem_meta(self, problem_id: str) -> dict[str, Any]:
        if problem_id in self._luogu_problem_cache:
            return self._luogu_problem_cache[problem_id]

        html = ""
        soup: BeautifulSoup | None = None
        meta = {"difficulty": None, "tags": [], "title": None}
        script_state = None

        try:
            script_state = self._get_luogu_json(f"/problem/{problem_id}?_contentOnly=1")
        except Exception:
            try:
                response = self._get(f"{LUOGU_BASE}/problem/{problem_id}")
                html = response.text
            except requests.RequestException:
                html = self._get_luogu_html_via_urllib(f"/problem/{problem_id}")
            soup = BeautifulSoup(html, "html.parser")
            script_state = self._extract_json_blob(html)

        if script_state:
            problem_data = script_state.get("data", {}).get("problem", {})
            if isinstance(problem_data, dict):
                if problem_data.get("title"):
                    meta["title"] = str(problem_data.get("title"))
                if problem_data.get("difficulty") is not None:
                    meta["difficulty"] = self._format_luogu_site_difficulty(problem_data.get("difficulty"))
                raw_tags = problem_data.get("tags", [])
                if raw_tags:
                    tag_map = self._load_luogu_tag_map()
                    translated = []
                    for raw_tag in raw_tags:
                        if isinstance(raw_tag, int):
                            translated_tag = tag_map.get(raw_tag)
                            if translated_tag:
                                translated.append(translated_tag)
                        else:
                            translated.append(str(raw_tag))
                    meta["tags"] = translated

        if meta["difficulty"] is None and html:
            if soup is None:
                soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ", strip=True)
            diff_match = re.search(r"难度[:：]\s*([^\s]+)", text)
            if diff_match:
                meta["difficulty"] = self._format_luogu_site_difficulty(diff_match.group(1))

        meta["tags"] = normalize_tags(meta.get("tags", []))

        self._luogu_problem_cache[problem_id] = meta
        return meta

    def _load_luogu_tag_map(self) -> dict[int, str]:
        if self._luogu_tag_map is not None:
            return self._luogu_tag_map

        payload = self._get_luogu_json("/_lfe/tags/zh-CN")
        tags = payload.get("tags", []) if isinstance(payload, dict) else []
        self._luogu_tag_map = {
            int(item["id"]): str(item["name"])
            for item in tags
            if (
                isinstance(item, dict)
                and item.get("id") is not None
                and item.get("name")
                and item.get("type") == 2
            )
        }
        return self._luogu_tag_map

    def _resolve_luogu_uid(self, uid: str | None = None, username: str | None = None) -> str | None:
        if uid:
            return str(uid)
        if not username:
            return None
        try:
            payload = self._get_luogu_json(f"/api/user/search?keyword={username}")
        except Exception:
            return None

        users = payload.get("users") or payload.get("data", {}).get("users") or []
        if not users:
            return None
        matched = None
        for user in users:
            user_name = user.get("name") or user.get("username")
            if user_name == username:
                matched = user
                break
        first = matched or users[0]
        resolved_uid = first.get("uid") or first.get("id")
        return str(resolved_uid) if resolved_uid is not None else None

    def _parse_luogu_records_from_html(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        rows = []
        for anchor in soup.select("a[href*='/record/']"):
            row_text = anchor.parent.get_text(" ", strip=True)
            href = anchor.get("href", "")
            problem_match = re.search(r"/problem/([A-Z]?\d+)", row_text)
            record_match = re.search(r"/record/(\d+)", href)
            if not record_match:
                continue
            status = "AC" if "Accepted" in row_text or "AC" in row_text else "UNKNOWN"
            rows.append(
                {
                    "record_id": record_match.group(1),
                    "external_submission_id": record_match.group(1),
                    "problem_id": problem_match.group(1) if problem_match else "Unknown",
                    "problem_name": anchor.get_text(strip=True) or "Unknown Problem",
                    "status": status,
                    "submit_time": None,
                    "runtime": None,
                    "memory": None,
                }
            )
        return rows

    def _extract_luogu_records_payload(self, response: requests.Response) -> list[dict[str, Any]]:
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            payload = response.json()
            if payload.get("instance") == "auth" or payload.get("template") == "login":
                raise PermissionError("Valid Luogu cookie required for record access")
            return self._extract_luogu_json_records(payload)

        raw_records = self._extract_luogu_embedded_records(response.text)
        if raw_records:
            return raw_records
        return self._parse_luogu_records_from_html(response.text)

    def _extract_luogu_practice_items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        candidates = (
            data.get("passed")
            or data.get("passedProblems")
            or data.get("user", {}).get("passedProblems", [])
            or payload.get("currentData", {}).get("passedProblems", [])
        )
        items = []
        for item in candidates or []:
            if not isinstance(item, dict):
                continue
            pid = item.get("pid") or item.get("problem", {}).get("pid") or item.get("id")
            if not pid:
                continue
            items.append(
                {
                    "problem_id": str(pid),
                    "problem_name": item.get("title")
                    or item.get("name")
                    or item.get("problem", {}).get("title")
                    or item.get("problem_name"),
                    "difficulty": item.get("difficulty"),
                    "tags": item.get("tags", []),
                    "submit_time": item.get("passedAt")
                    or item.get("submitTime")
                    or item.get("latestSubmitTime")
                    or item.get("latestSubmissionTime")
                    or item.get("time"),
                    "runtime": item.get("runtime") or item.get("time_ms"),
                    "memory": item.get("memory") or item.get("memory_kb"),
                }
            )
        return items

    def _fetch_luogu_practice_solved(self, uid: str) -> list[dict[str, Any]]:
        payload = self._get_luogu_json(f"/user/{uid}/practice")
        items = self._extract_luogu_practice_items(payload)
        if items:
            return items

        fallback_payload = self._get_luogu_json(f"/user/{uid}")
        return self._extract_luogu_practice_items(fallback_payload)

    def _fetch_luogu_record_page(self, user_identifier: str, page: int) -> list[dict[str, Any]]:
        try:
            payload = self._get_luogu_json(f"/record/list?user={user_identifier}&page={page}&_contentOnly=1")
            records = self._extract_luogu_json_records(payload)
            if records:
                return records
        except Exception:
            pass

        candidates = [f"{LUOGU_BASE}/record/list?user={user_identifier}&page={page}"]
        for url in candidates:
            try:
                response = self._get(url)
                records = self._extract_luogu_records_payload(response)
                if records:
                    return records
            except requests.RequestException:
                pass

        try:
            html = self._get_luogu_html_via_urllib(f"/record/list?user={user_identifier}&page={page}")
            records = self._extract_luogu_embedded_records(html)
            if records:
                return records
        except Exception:
            pass
        return []

    def _fetch_luogu_user_page_records(self, user_identifier: str) -> list[dict[str, Any]]:
        try:
            response = self._get(f"{LUOGU_BASE}/user/{user_identifier}")
        except requests.RequestException:
            return []
        return self._extract_luogu_records_payload(response)

    def _fetch_all_luogu_records(
        self,
        user_identifier: str,
        force_full: bool,
    ) -> list[dict[str, Any]]:
        last_time = None if force_full else self._get_last_submission_time("luogu")
        all_records: list[dict[str, Any]] = []
        seen_external_ids: set[str] = set()
        page = 1
        max_pages = 200

        while page <= max_pages:
            page_records = self._fetch_luogu_record_page(user_identifier, page)
            if not page_records and page == 1:
                page_records = self._fetch_luogu_user_page_records(user_identifier)
            if not page_records:
                break

            normalized_page = []
            reached_old_record = False
            for item in page_records:
                submit_time = self._coerce_datetime(
                    item.get("submit_time") or item.get("time"),
                    allow_none=True,
                )
                external_id = str(
                    item.get("external_submission_id") or item.get("record_id") or item.get("id") or ""
                ).strip()
                if external_id and external_id in seen_external_ids:
                    continue
                if external_id:
                    seen_external_ids.add(external_id)

                normalized_page.append({**item, "submit_time": submit_time})
                if last_time and submit_time and submit_time <= last_time:
                    reached_old_record = True

            all_records.extend(normalized_page)

            if reached_old_record and not force_full:
                break
            if len(page_records) < 20 and page > 1:
                break
            page += 1

        if last_time and not force_full:
            return [record for record in all_records if record["submit_time"] and record["submit_time"] > last_time]
        return all_records

    def fetch_luogu_submissions(
        self,
        uid: str | None = None,
        username: str | None = None,
        force_full: bool = False,
    ) -> list[dict]:
        if not self.config.luogu_cookie:
            raise ValueError("Luogu sync requires a valid Luogu cookie")
        uid = uid or self.config.luogu_uid
        username = username or self.config.luogu_username
        resolved_uid = self._resolve_luogu_uid(uid=uid, username=username)
        if not resolved_uid:
            return []

        solved_items = self._fetch_luogu_practice_solved(resolved_uid)
        if not solved_items:
            return []

        solved_ids = {str(item.get("problem_id")) for item in solved_items if item.get("problem_id")}
        record_items = self._fetch_all_luogu_records(resolved_uid, force_full=True)
        first_ac_lookup: dict[str, dict[str, Any]] = {}
        latest_unsolved_lookup: dict[str, dict[str, Any]] = {}
        for item in record_items:
            problem_id = str(item.get("problem_id") or item.get("pid") or "")
            if not problem_id:
                continue
            raw_status = item.get("status")
            status = self._normalize_status(raw_status) if raw_status != "AC" else "AC"
            if status == "UNKNOWN" and item.get("score") not in (None, ""):
                try:
                    score = float(item.get("score"))
                except (TypeError, ValueError):
                    score = None
                if score == 100:
                    status = "AC"
                elif score is not None and score < 100:
                    status = "WA"
            submit_time = self._coerce_datetime(
                item.get("submit_time") or item.get("time"),
                allow_none=True,
            )
            if status == "AC":
                current = first_ac_lookup.get(problem_id)
                if current is None or (
                    submit_time is not None and current["submit_time"] is not None and submit_time < current["submit_time"]
                ) or (
                    current["submit_time"] is None and submit_time is not None
                ):
                    first_ac_lookup[problem_id] = {
                        "submit_time": submit_time,
                        "runtime": item.get("runtime") or item.get("time_ms"),
                        "memory": item.get("memory") or item.get("memory_kb"),
                        "external_submission_id": str(
                            item.get("external_submission_id") or item.get("record_id") or ""
                        )
                        or None,
                    }
            elif problem_id not in solved_ids:
                current_unsolved = latest_unsolved_lookup.get(problem_id)
                if current_unsolved is None or (
                    submit_time is not None and current_unsolved["submit_time"] is not None and submit_time > current_unsolved["submit_time"]
                ) or (
                    current_unsolved["submit_time"] is None and submit_time is not None
                ):
                    latest_unsolved_lookup[problem_id] = {
                        "submit_time": submit_time,
                        "runtime": item.get("runtime") or item.get("time_ms"),
                        "memory": item.get("memory") or item.get("memory_kb"),
                        "difficulty": item.get("difficulty"),
                        "status": status,
                        "problem_name": item.get("problem_name"),
                    }

        self._last_luogu_diagnostics = {
            "resolved_uid": resolved_uid,
            "solved_count": len(solved_items),
            "record_count": len(record_items),
            "matched_ac_time_count": len(first_ac_lookup),
            "unsolved_record_count": len(latest_unsolved_lookup),
        }

        cleaned = []
        for item in solved_items:
            problem_id = str(item.get("problem_id") or "Unknown")

            record_meta = first_ac_lookup.get(problem_id, {})
            meta = {}
            if problem_id != "Unknown":
                try:
                    meta = self._fetch_luogu_problem_meta(problem_id)
                except Exception:
                    meta = {}
            cleaned.append(
                {
                    "oj_source": "luogu",
                    "external_submission_id": record_meta.get("external_submission_id"),
                    "problem_id": problem_id,
                    "problem_name": item.get("problem_name") or meta.get("title") or "Unknown Problem",
                    "difficulty": item.get("difficulty") or meta.get("difficulty"),
                    "tags": normalize_tags([*(item.get("tags") or []), *(meta.get("tags", []) or [])]),
                    "status": "AC",
                    "submit_time": record_meta.get("submit_time")
                    or self._coerce_datetime(item.get("submit_time"), allow_none=True),
                    "runtime": record_meta.get("runtime") or item.get("runtime"),
                    "memory": record_meta.get("memory") or item.get("memory"),
                }
            )

        for problem_id, record_meta in latest_unsolved_lookup.items():
            meta = {}
            try:
                meta = self._fetch_luogu_problem_meta(problem_id)
            except Exception:
                meta = {}
            cleaned.append(
                {
                    "oj_source": "luogu",
                    "external_submission_id": record_meta.get("external_submission_id"),
                    "problem_id": problem_id,
                    "problem_name": record_meta.get("problem_name") or meta.get("title") or "Unknown Problem",
                    "difficulty": record_meta.get("difficulty") or meta.get("difficulty"),
                    "tags": normalize_tags(meta.get("tags", [])),
                    "status": record_meta.get("status") or "UNKNOWN",
                    "submit_time": record_meta.get("submit_time"),
                    "runtime": record_meta.get("runtime"),
                    "memory": record_meta.get("memory"),
                }
            )
        return cleaned

    def _extract_luogu_json_records(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = []
        current_data = payload.get("currentData", {}) if isinstance(payload, dict) else {}
        if isinstance(current_data, dict):
            records = current_data.get("records", {})
            if isinstance(records, dict) and isinstance(records.get("result"), list):
                candidates = records.get("result", [])

        for key in ("records", "submissions", "list", "data"):
            if candidates:
                break
            value = payload.get(key)
            if isinstance(value, list):
                candidates = value
                break
            if isinstance(value, dict):
                for inner_key in ("records", "result", "list"):
                    inner = value.get(inner_key)
                    if isinstance(inner, list):
                        candidates = inner
                        break
        normalized = []
        for item in candidates:
            problem = item.get("problem", {}) if isinstance(item, dict) else {}
            normalized.append(
                {
                    "external_submission_id": item.get("id") or item.get("recordId"),
                    "problem_id": item.get("problem_id") or problem.get("pid") or problem.get("id"),
                    "problem_name": item.get("problem_name") or problem.get("title") or problem.get("name"),
                    "status": item.get("status") or item.get("judgeStatus"),
                    "submit_time": item.get("submit_time") or item.get("submitTime") or item.get("submitTimeStr") or item.get("time") or item.get("submitTime"),
                    "runtime": item.get("runtime") or item.get("time"),
                    "memory": item.get("memory") or item.get("memoryUsage"),
                    "difficulty": problem.get("difficulty"),
                    "score": item.get("score"),
                }
            )
        return normalized

    def _extract_luogu_embedded_records(self, html: str) -> list[dict[str, Any]]:
        state = self._extract_json_blob(html)
        if not state:
            return []

        candidates: list[dict[str, Any]] = []

        def walk(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        if {"status", "problem"} & set(item.keys()):
                            candidates.append(item)
                        walk(item)
            elif isinstance(value, dict):
                for nested in value.values():
                    walk(nested)

        walk(state)
        if not candidates:
            return []
        return self._extract_luogu_json_records({"records": candidates})

    @staticmethod
    def _coerce_datetime(value: Any, allow_none: bool = False) -> datetime | None:
        if value in (None, ""):
            return None if allow_none else datetime.now(timezone.utc)
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return None if allow_none else datetime.now(timezone.utc)

    def _is_source_configured(self, source: str) -> bool:
        """Whether this OJ has enough config to run a fetch (matches public_config / fetch guards)."""
        s = (source or "").strip().lower()
        if s == "codeforces":
            return bool((self.config.codeforces_handle or "").strip())
        if s == "luogu":
            if not (self.config.luogu_cookie or "").strip():
                return False
            uid = (self.config.luogu_uid or "").strip()
            username = (self.config.luogu_username or "").strip()
            return bool(uid or username)
        if s == "nowcoder":
            return bool((self.config.nowcoder_uid or "").strip())
        if s == "atcoder":
            return bool((self.config.atcoder_username or "").strip())
        return False

    def _filter_incremental(self, source: str, records: list[dict], force_full: bool) -> list[dict]:
        if force_full:
            return records
        if source == "luogu":
            return records
        last_time = self._get_last_submission_time(source)
        if not last_time:
            return records
        return [record for record in records if record["submit_time"] > last_time]

    def _fill_tags_from_editorial(self, records: list[dict]) -> int:
        """对无有效知识点标签的题目，抓取题面/题解文本并推断标签。"""
        from app.extra_oj import _atcoder_fallback_tags
        from app.services.editorial_fetch import fetch_editorial_plaintext_for_problem
        from app.services.tags import (
            infer_tags_from_editorial_text,
            normalize_tags,
            tags_for_knowledge_stats,
        )

        if not records:
            return 0

        keys: list[tuple[str, str]] = []
        seen_k: set[tuple[str, str]] = set()
        for r in records:
            oj = str(r.get("oj_source") or "").strip()
            pid = str(r.get("problem_id") or "").strip()
            if not oj or not pid:
                continue
            tags = r.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            if tags_for_knowledge_stats(tags):
                continue
            k = (oj, pid)
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)

        if not keys:
            return 0

        cache: dict[tuple[str, str], list[str]] = {}
        filled_problems = 0
        for oj, pid in keys:
            sample = next(
                (
                    r
                    for r in records
                    if str(r.get("oj_source")) == oj and str(r.get("problem_id") or "").strip() == pid
                ),
                None,
            )
            title = (sample.get("problem_name") if sample else "") or ""
            blob = fetch_editorial_plaintext_for_problem(self, oj, pid, title)
            # 标题再并一次：题面抓取失败或公式站点多时仍可从「××的××」等标题猜知识点
            combined = f"{blob}\n{title}".strip() if title else blob
            tags = infer_tags_from_editorial_text(combined)
            if oj == "atcoder":
                tags = normalize_tags([*tags, *_atcoder_fallback_tags(pid)])
            else:
                tags = normalize_tags(tags)
            cache[(oj, pid)] = tags
            if tags_for_knowledge_stats(tags):
                filled_problems += 1
            time.sleep(0.05)

        for r in records:
            oj = str(r.get("oj_source") or "").strip()
            pid = str(r.get("problem_id") or "").strip()
            k = (oj, pid)
            if k not in cache:
                continue
            cur = r.get("tags") or []
            if not isinstance(cur, list):
                cur = []
            if tags_for_knowledge_stats(cur):
                continue
            r["tags"] = cache[k]
        return filled_problems

    def _save_luogu_records(self, records: list[dict]) -> tuple[int, int, int, int]:
        if not records:
            return 0, 0, 0, 0

        problem_ids = [str(record["problem_id"]) for record in records if record.get("problem_id")]
        existing_stmt = select(Submission).where(
            Submission.oj_source == "luogu",
            Submission.problem_id.in_(problem_ids),
        )
        existing_rows = self.db.execute(existing_stmt).scalars().all()
        existing_ac_map: dict[str, Submission] = {}
        existing_unsolved_map: dict[tuple[str, str], Submission] = {}
        existing_unsolved_by_problem: dict[str, Submission] = {}
        for row in existing_rows:
            if row.status == "AC":
                existing_ac_map.setdefault(row.problem_id, row)
            else:
                existing_unsolved_map.setdefault((row.problem_id, row.status), row)
                existing_unsolved_by_problem.setdefault(row.problem_id, row)

        inserts = []
        inserted_unknown = 0
        updated = 0
        skipped = 0

        for record in records:
            problem_id = str(record["problem_id"])
            tags_json = json.dumps(record.get("tags", []), ensure_ascii=False)
            if record.get("status") == "AC":
                existing = existing_ac_map.get(problem_id)
                if existing:
                    changed = False
                    if record.get("submit_time") and (
                        existing.submit_time is None or existing.submit_time != record["submit_time"]
                    ):
                        existing.submit_time = record["submit_time"]
                        changed = True
                    if record.get("difficulty") and existing.difficulty != record["difficulty"]:
                        existing.difficulty = record["difficulty"]
                        changed = True
                    if record.get("problem_name") and existing.problem_name != record["problem_name"]:
                        existing.problem_name = record["problem_name"]
                        changed = True
                    if record.get("runtime") is not None and existing.runtime != record["runtime"]:
                        existing.runtime = record["runtime"]
                        changed = True
                    if record.get("memory") is not None and existing.memory != record["memory"]:
                        existing.memory = record["memory"]
                        changed = True
                    if tags_json != existing.tags:
                        existing.tags = tags_json
                        changed = True
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                    continue
            else:
                existing = existing_unsolved_map.get((problem_id, str(record.get("status"))))
                if existing is None:
                    existing = existing_unsolved_by_problem.get(problem_id)
                if existing:
                    changed = False
                    normalized_status = str(record.get("status") or existing.status)
                    if existing.status != normalized_status:
                        existing.status = normalized_status
                        changed = True
                    if record.get("submit_time") and (
                        existing.submit_time is None or existing.submit_time != record["submit_time"]
                    ):
                        existing.submit_time = record["submit_time"]
                        changed = True
                    if record.get("difficulty") and existing.difficulty != record["difficulty"]:
                        existing.difficulty = record["difficulty"]
                        changed = True
                    if record.get("problem_name") and existing.problem_name != record["problem_name"]:
                        existing.problem_name = record["problem_name"]
                        changed = True
                    if record.get("runtime") is not None and existing.runtime != record["runtime"]:
                        existing.runtime = record["runtime"]
                        changed = True
                    if record.get("memory") is not None and existing.memory != record["memory"]:
                        existing.memory = record["memory"]
                        changed = True
                    if tags_json != existing.tags:
                        existing.tags = tags_json
                        changed = True
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                    continue

            if record.get("submit_time") is None:
                inserted_unknown += 1
            inserts.append(
                {
                    **{key: value for key, value in record.items() if key != "external_submission_id"},
                    "tags": tags_json,
                    "via_vjudge": False,
                }
            )

        inserted = 0
        if inserts:
            stmt = sqlite_insert(Submission).values(inserts)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["oj_source", "problem_id", "status", "submit_time"]
            )
            result = self.db.execute(stmt)
            inserted = result.rowcount if result.rowcount is not None and result.rowcount >= 0 else 0
            skipped += max(len(inserts) - inserted, 0)

        direct_pairs = {
            ("luogu", str(r["problem_id"]))
            for r in records
            if r.get("status") == "AC" and r.get("problem_id")
        }
        if direct_pairs:
            self._purge_vjudge_shadowed(direct_pairs)

        self.db.commit()
        unknown_after_save = sum(1 for record in records if record.get("submit_time") is None)
        return inserted, skipped, unknown_after_save, updated

    def _save_submissions(self, records: list[dict]) -> tuple[int, int, int, int]:
        if not records:
            return 0, 0, 0, 0

        if all(record.get("oj_source") == "luogu" for record in records):
            return self._save_luogu_records(records)

        keys = [
            (
                str(record.get("oj_source")),
                str(record.get("problem_id")),
                str(record.get("status")),
                record.get("submit_time"),
            )
            for record in records
            if record.get("problem_id") and record.get("status")
        ]
        existing_stmt = select(Submission).where(
            Submission.oj_source.in_([item[0] for item in keys]),
            Submission.problem_id.in_([item[1] for item in keys]),
        )
        existing_rows = self.db.execute(existing_stmt).scalars().all()
        existing_map = {
            (
                row.oj_source,
                row.problem_id,
                row.status,
                row.submit_time if row.submit_time is None or row.submit_time.tzinfo else row.submit_time.replace(tzinfo=timezone.utc),
            ): row
            for row in existing_rows
        }

        payload = []
        unknown_time_count = 0
        updated = 0
        skipped = 0
        for record in records:
            if record.get("via_vjudge") and record.get("status") == "AC" and record.get("problem_id"):
                has_direct = self.db.execute(
                    select(Submission.id).where(
                        Submission.oj_source == str(record.get("oj_source")),
                        Submission.problem_id == str(record.get("problem_id")),
                        Submission.status == "AC",
                        Submission.via_vjudge.is_(False),
                    ).limit(1)
                ).scalar_one_or_none()
                if has_direct is not None:
                    skipped += 1
                    continue
            if record.get("submit_time") is None:
                unknown_time_count += 1
            tags_json = json.dumps(record.get("tags", []), ensure_ascii=False)
            key = (
                str(record.get("oj_source")),
                str(record.get("problem_id")),
                str(record.get("status")),
                record.get("submit_time")
                if record.get("submit_time") is None or record.get("submit_time").tzinfo
                else record.get("submit_time").replace(tzinfo=timezone.utc),
            )
            existing = existing_map.get(key)
            if existing:
                changed = False
                if record.get("difficulty") and existing.difficulty != record["difficulty"]:
                    existing.difficulty = record["difficulty"]
                    changed = True
                if record.get("problem_name") and existing.problem_name != record["problem_name"]:
                    existing.problem_name = record["problem_name"]
                    changed = True
                if record.get("runtime") is not None and existing.runtime != record["runtime"]:
                    existing.runtime = record["runtime"]
                    changed = True
                if record.get("memory") is not None and existing.memory != record["memory"]:
                    existing.memory = record["memory"]
                    changed = True
                if tags_json != existing.tags:
                    existing.tags = tags_json
                    changed = True
                if changed:
                    updated += 1
                else:
                    skipped += 1
                continue

            row_out = {key: value for key, value in record.items() if key != "external_submission_id"}
            row_out["via_vjudge"] = bool(record.get("via_vjudge"))
            row_out["tags"] = tags_json
            payload.append(row_out)

        inserted = 0
        if payload:
            stmt = sqlite_insert(Submission).values(payload)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["oj_source", "problem_id", "status", "submit_time"]
            )
            result = self.db.execute(stmt)
            inserted = result.rowcount if result.rowcount is not None and result.rowcount >= 0 else 0
        direct_pairs = {
            (str(r["oj_source"]), str(r["problem_id"]))
            for r in records
            if r.get("status") == "AC"
            and not r.get("via_vjudge")
            and r.get("oj_source")
            and r.get("problem_id")
        }
        if direct_pairs:
            self._purge_vjudge_shadowed(direct_pairs)
        self.db.commit()
        skipped += max(len(payload) - inserted, 0)
        return inserted, skipped, unknown_time_count, updated

    def _start_sync_run(self, source: str | None, force_full: bool) -> SyncRun:
        sync_run = SyncRun(
            source=source or "all",
            mode="full" if force_full else "incremental",
            status="running",
            failed_sources="[]",
            detail="{}",
        )
        self.db.add(sync_run)
        self.db.commit()
        self.db.refresh(sync_run)
        return sync_run

    def _finish_sync_run(self, sync_run: SyncRun, summary: dict) -> None:
        sync_run.status = "partial_failed" if summary["failed_sources"] else "success"
        sync_run.finished_at = datetime.now(timezone.utc)
        sync_run.fetched_count = summary["fetched"]
        sync_run.inserted_count = summary["inserted"]
        sync_run.skipped_count = summary["skipped"]
        sync_run.failed_sources = json.dumps(summary["failed_sources"], ensure_ascii=False)
        sync_run.detail = json.dumps(summary["sources"], ensure_ascii=False)
        self.db.add(sync_run)
        self.db.commit()

    def sync_all(
        self,
        source: str | None = None,
        force_full: bool = False,
        *,
        only_configured: bool = False,
    ) -> dict:
        target = source.lower() if source else None
        if not self._sync_lock.acquire(blocking=False):
            raise RuntimeError("A sync job is already running")
        summary = {
            "fetched": 0,
            "inserted": 0,
            "skipped": 0,
            "updated": 0,
            "unknown_time_count": 0,
            "failed_sources": [],
            "sources": {},
        }
        sync_run = self._start_sync_run(source, force_full)

        try:
            from app.extra_oj import (
                fetch_atcoder_submissions,
                fetch_nowcoder_submissions,
            )

            jobs: list[tuple[str, Any]] = []
            if target in (None, "codeforces"):
                jobs.append(("codeforces", self.fetch_codeforces_submissions))
            if target in (None, "luogu"):
                jobs.append(("luogu", self.fetch_luogu_submissions))
            if target in (None, "nowcoder"):
                jobs.append(("nowcoder", lambda: fetch_nowcoder_submissions(self)))
            if target in (None, "atcoder"):
                jobs.append(("atcoder", lambda: fetch_atcoder_submissions(self)))

            if only_configured:
                jobs = [(n, f) for n, f in jobs if self._is_source_configured(n)]

            for source_name, func in jobs:
                try:
                    if source_name == "luogu":
                        fetched_records = func(force_full=force_full)
                    else:
                        fetched_records = func()
                    filtered_records = self._filter_incremental(source_name, fetched_records, force_full)
                    editorial_filled = self._fill_tags_from_editorial(filtered_records)
                    inserted, skipped, unknown_time_count, updated_count = self._save_submissions(filtered_records)
                    summary["fetched"] += len(fetched_records)
                    summary["inserted"] += inserted
                    summary["skipped"] += skipped
                    summary["updated"] += updated_count
                    summary["unknown_time_count"] += unknown_time_count
                    summary["sources"][source_name] = {
                        "fetched": len(fetched_records),
                        "after_filter": len(filtered_records),
                        "editorial_filled": editorial_filled,
                        "inserted": inserted,
                        "skipped": skipped,
                        "updated": updated_count,
                        "unknown_time_count": unknown_time_count,
                        "status": "success",
                        "message": "",
                    }
                    if source_name == "luogu":
                        diagnostics = dict(self._last_luogu_diagnostics)
                        summary["sources"][source_name].update(diagnostics)
                        if unknown_time_count:
                            summary["sources"][source_name]["message"] = (
                                f"record_count={diagnostics.get('record_count', 0)}, "
                                f"matched_ac_time_count={diagnostics.get('matched_ac_time_count', 0)}"
                            )
                except Exception as exc:
                    self.db.rollback()
                    summary["failed_sources"].append(source_name)
                    summary["sources"][source_name] = {
                        "fetched": 0,
                        "after_filter": 0,
                        "inserted": 0,
                        "skipped": 0,
                        "status": "failed",
                        "message": str(exc),
                    }

            self._finish_sync_run(sync_run, summary)
            return summary
        finally:
            self._sync_lock.release()

    def poll_latest(self, source: str | None = None) -> dict:
        return self.sync_all(source=source, force_full=False, only_configured=True)
