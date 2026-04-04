"""Optional OJ sources: Nowcoder ACM, AtCoder."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any
import requests
from bs4 import BeautifulSoup

from app.services.tags import infer_tags_from_title, normalize_tags

NOWCODER_BASE = "https://ac.nowcoder.com"
NOWCODER_LIST_JSON = f"{NOWCODER_BASE}/acm/problem/list/json"
KENKOOOO_ATCODER = "https://kenkoooo.com/atcoder"


def _normalize_nc_status(text: str | None) -> str:
    if not text:
        return "UNKNOWN"
    t = re.sub(r"\s+", "", text)
    if "答案正确" in text or t == "AC":
        return "AC"
    if "编译错误" in text:
        return "CE"
    if "运行超时" in text or "时间限制" in text:
        return "TLE"
    if "内存" in text and "超出" in text:
        return "MLE"
    if "运行错误" in text or "段错误" in text:
        return "RE"
    if "答案错误" in text or "错误" in text:
        return "WA"
    return "WA"


def _atcoder_difficulty_str(pid: str, models: dict[str, Any]) -> str | None:
    """problem-models.json：难度为正整数时入库为字符串，供 difficulty_display 展示。"""
    m = models.get(pid)
    if not isinstance(m, dict):
        return None
    d = m.get("difficulty")
    if d is None:
        d = m.get("rawDifficulty")
    if isinstance(d, (int, float)):
        di = int(d)
        if di > 0:
            return str(di)
    return None


_NOWCODER_PLATFORM_TAG_NAMES = frozenset(
    {
        "牛客",
        "牛客网",
        "Nowcoder",
        "NOWCODER",
        "nowcoder",
        "牛客竞赛",
    }
)

# 来源/周赛类标签，对「算法知识点」统计噪声大；若仍无算法 tagList 则不再依赖其细分
def _nowcoder_row_tag_names(p: dict[str, Any]) -> list[str]:
    """
    从 list/json 单题解析知识点（与牛客题面「知识点」一致）。
    兼容多种字段名；不使用 sourceTagList（来源/平台/赛别）。
    """
    names: list[str] = []
    for key in (
        "tagList",
        "knowledgeTagList",
        "skillTagList",
        "algorithmTagList",
        "problemTagList",
        "allTagList",
        "labelList",
    ):
        for t in p.get(key) or []:
            if isinstance(t, dict) and t.get("name"):
                s = str(t["name"]).strip()
                if s and s not in _NOWCODER_PLATFORM_TAG_NAMES:
                    names.append(s)
            elif isinstance(t, str) and t.strip():
                s = t.strip()
                if s not in _NOWCODER_PLATFORM_TAG_NAMES:
                    names.append(s)
    raw_tags = p.get("tags")
    if isinstance(raw_tags, str) and raw_tags.strip():
        for piece in re.split(r"[,，;；|｜\s]+", raw_tags.strip()):
            s = piece.strip()
            if s and s not in _NOWCODER_PLATFORM_TAG_NAMES:
                names.append(s)
    return names


def _atcoder_collect_raw_tags(meta: dict[str, Any]) -> list[str]:
    """kenkoooo merged-problems 等字段：tags / classifications / genre 及嵌套对象。"""
    found: list[str] = []
    for key in ("tags", "classifications", "genre", "keyword", "keywords"):
        raw: Any = meta.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            s = raw.strip()
            if s:
                found.append(s)
            continue
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    found.append(s)
            elif isinstance(item, dict):
                for k in ("name", "tag", "label", "title", "slug", "keyword"):
                    v = item.get(k)
                    if v is not None and str(v).strip():
                        found.append(str(v).strip())
                        break
    return found


def _atcoder_tags_from_meta(meta: dict[str, Any]) -> list[str]:
    return normalize_tags(_atcoder_collect_raw_tags(meta))


def _atcoder_fallback_tags(problem_id: str) -> list[str]:
    """索引无算法标签时，用语种/赛别 + AtCoder 作为知识点，便于分布图统计。"""
    pid = str(problem_id).strip().lower()
    if "_" in pid:
        head = pid.split("_")[0]
        if head.startswith("abc"):
            return normalize_tags(["AtCoder ABC"])
        if head.startswith("arc"):
            return normalize_tags(["AtCoder ARC"])
        if head.startswith("agc"):
            return normalize_tags(["AtCoder AGC"])
    return normalize_tags(["AtCoder"])


def _atcoder_problem_resources(fetcher: Any) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """
    合并 kenkoooo 的 problems.json、merged-problems.json、problem-tags.json（若存在且 merged 无标签），
    以及 problem-models.json（难度估计）。
    文档建议两次请求间隔 ≥1s，首次同步会多等数秒。
    """
    cached: tuple[dict[str, dict[str, Any]], dict[str, Any]] | None = getattr(
        fetcher, "_atcoder_problem_resources", None
    )
    if cached is not None:
        return cached

    ua = fetcher.config.user_agent
    timeout = max(fetcher.config.timeout, 120)
    base = f"{KENKOOOO_ATCODER}/resources"

    def get_json(name: str) -> Any:
        # kenkoooo S3/API 在无 Accept-Encoding: gzip 时可能对部分客户端返回 403（见 AtCoderProblems#920）
        r = fetcher.session.get(
            f"{base}/{name}",
            headers={
                "User-Agent": ua,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": f"{KENKOOOO_ATCODER}/",
            },
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()

    by_id: dict[str, dict[str, Any]] = {}
    try:
        problems = get_json("problems.json")
        if isinstance(problems, list):
            for p in problems:
                if isinstance(p, dict) and p.get("id"):
                    by_id[str(p["id"])] = dict(p)
    except Exception:
        pass

    time.sleep(1.05)
    try:
        merged = get_json("merged-problems.json")
        if isinstance(merged, list):
            for p in merged:
                if not isinstance(p, dict) or not p.get("id"):
                    continue
                pid = str(p["id"])
                cur = by_id.setdefault(pid, {})
                for k, v in p.items():
                    if v is not None:
                        cur[k] = v
    except Exception:
        pass

    time.sleep(1.05)
    models: dict[str, Any] = {}
    try:
        raw_models = get_json("problem-models.json")
        if isinstance(raw_models, dict):
            models = raw_models
    except Exception:
        pass

    time.sleep(1.05)
    try:
        tag_extra = get_json("problem-tags.json")
        if isinstance(tag_extra, dict):
            for pid, tlist in tag_extra.items():
                if not pid or not isinstance(tlist, list) or not tlist:
                    continue
                cur = by_id.setdefault(str(pid), {})
                if not _atcoder_collect_raw_tags(cur):
                    cur["tags"] = tlist
    except Exception:
        pass

    fetcher._atcoder_problem_resources = (by_id, models)
    return fetcher._atcoder_problem_resources


def _normalize_atcoder_result(result: str | None) -> str:
    if not result:
        return "UNKNOWN"
    r = str(result).strip().upper()
    direct = {
        "AC": "AC",
        "WA": "WA",
        "TLE": "TLE",
        "MLE": "MLE",
        "RE": "RE",
        "CE": "CE",
        "OLE": "OLE",
        "PE": "PE",
        "WJ": "UNKNOWN",
        "WR": "UNKNOWN",
        "JUDGING": "UNKNOWN",
        "PENDING": "UNKNOWN",
        "PROCESSING": "UNKNOWN",
        "INTERNAL_ERROR": "UNKNOWN",
    }
    if r in direct:
        return direct[r]
    from app.fetcher import STATUS_MAP

    return STATUS_MAP.get(result, STATUS_MAP.get(r, "UNKNOWN"))


def fetch_atcoder_submissions(fetcher: Any) -> list[dict]:
    """
    全量提交：kenkoooo AtCoder API（公开，无需 Cookie）。
    题目名与 merged-problems 合并；难度来自 problem-models.json（估计分）；
    知识点标签若索引中含 tags/classifications 则与其它 OJ 一样经 normalize_tags 入库。
    """
    user = (fetcher.config.atcoder_username or "").strip()
    if not user:
        return []

    idx, models = _atcoder_problem_resources(fetcher)
    from_second = 0
    out: list[dict[str, Any]] = []
    max_batches = 20000

    for _ in range(max_batches):
        response = fetcher.session.get(
            f"{KENKOOOO_ATCODER}/atcoder-api/v3/user/submissions",
            params={"user": user, "from_second": from_second},
            headers={
                "User-Agent": fetcher.config.user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": f"{KENKOOOO_ATCODER}/",
            },
            timeout=fetcher.config.timeout,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        if not isinstance(batch, list):
            raise ValueError(f"AtCoder API 返回异常：{batch!r}")

        for item in batch:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("problem_id") or "").strip()
            meta = idx.get(pid) or {}
            raw_name = (meta.get("name") or meta.get("title") or "").strip()
            problem_name = raw_name or pid or "Unknown Problem"
            diff_str = _atcoder_difficulty_str(pid, models)
            tags = _atcoder_tags_from_meta(meta)
            tags = normalize_tags(tags) if tags else []
            ts = item.get("epoch_second")
            submit_time = (
                datetime.fromtimestamp(int(ts), tz=timezone.utc) if ts is not None else None
            )
            et = item.get("execution_time")
            runtime = None
            if et is not None:
                try:
                    runtime = int(et)
                except (TypeError, ValueError):
                    runtime = None

            sid = item.get("id")
            out.append(
                {
                    "oj_source": "atcoder",
                    "external_submission_id": str(sid) if sid is not None else None,
                    "problem_id": pid,
                    "problem_name": problem_name,
                    "difficulty": diff_str,
                    "tags": tags,
                    "status": _normalize_atcoder_result(item.get("result")),
                    "submit_time": submit_time,
                    "runtime": runtime,
                    "memory": None,
                }
            )

        from_second = int(batch[-1]["epoch_second"]) + 1

    return out


def _parse_nowcoder_practice_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for tr in soup.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 9:
            continue
        sub_a = tds[0].find("a", href=True)
        prob_a = tds[1].find("a", href=True)
        stat_a = tds[2].find("a")
        if not prob_a:
            continue
        href = prob_a.get("href", "")
        m = re.search(r"/acm/problem/(\d+)", href)
        problem_id = m.group(1) if m else prob_a.get_text(strip=True)
        problem_name = prob_a.get_text(strip=True) or f"Problem {problem_id}"
        sub_id = ""
        if sub_a and sub_a.get("href"):
            sm = re.search(r"submissionId=(\d+)", sub_a["href"])
            if sm:
                sub_id = sm.group(1)
        status_text = stat_a.get_text(strip=True) if stat_a else ""
        status = _normalize_nc_status(status_text)
        rt_text = tds[4].get_text(strip=True)
        mem_text = tds[5].get_text(strip=True)
        try:
            runtime = int(rt_text) if rt_text.isdigit() else None
        except ValueError:
            runtime = None
        try:
            memory = int(mem_text) if mem_text.isdigit() else None
        except ValueError:
            memory = None
        time_cell = tds[8].get_text(strip=True)
        submit_time = None
        if time_cell:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
                try:
                    submit_time = datetime.strptime(time_cell, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
        rows.append(
            {
                "oj_source": "nowcoder",
                "external_submission_id": sub_id or None,
                "problem_id": str(problem_id),
                "problem_name": problem_name,
                "difficulty": None,
                "tags": [],
                "status": status,
                "submit_time": submit_time,
                "runtime": runtime,
                "memory": memory,
            }
        )
    return rows


def _nowcoder_problem_meta_from_list_api(fetcher: Any, problem_id: str) -> dict[str, Any]:
    """
    通过题库公开接口 /acm/problem/list/json，用 keyword=题号 精确匹配单题，
    读取 difficulty（题库难度分）与 tagList（知识点标签对象列表）。
    """
    pid = str(problem_id).strip()
    if not pid.isdigit():
        return {}

    params = {
        "keyword": pid,
        "tagId": "",
        "platformTagId": "0",
        "sourceTagId": "0",
        "difficulty": "0",
        "status": "all",
        "order": "id",
        "asc": "false",
        "pageSize": "5",
        "page": "1",
    }
    headers = {
        "Referer": f"{NOWCODER_BASE}/acm/problem/list",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": fetcher.config.user_agent,
    }
    if fetcher.config.nowcoder_cookie:
        headers["Cookie"] = fetcher.config.nowcoder_cookie.strip()

    response = fetcher.session.get(NOWCODER_LIST_JSON, params=params, headers=headers, timeout=fetcher.config.timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("code") != 0:
        return {}
    sets = payload.get("data") or {}
    if not isinstance(sets, dict):
        return {}
    rows = sets.get("problemSets") or []
    if not isinstance(rows, list):
        return {}

    for p in rows:
        if not isinstance(p, dict):
            continue
        if str(p.get("problemId")) != pid:
            continue
        out: dict[str, Any] = {}
        di = 0
        diff = p.get("difficulty")
        if isinstance(diff, (int, float)):
            di = int(diff)
            if di > 0:
                out["difficulty"] = str(di)
        tag_names = _nowcoder_row_tag_names(p)
        if tag_names:
            out["tags"] = normalize_tags(tag_names)
        else:
            title_guess = (p.get("name") or "").strip()
            out["tags"] = normalize_tags(infer_tags_from_title(title_guess)) if title_guess else []
        return out
    return {}


def _nowcoder_enrich_practice_rows(fetcher: Any, rows: list[dict]) -> None:
    """为练习记录中的每道题补全难度与标签（按题号去重请求）。"""
    cache: dict[str, dict[str, Any]] = getattr(fetcher, "_nowcoder_problem_meta_cache", None) or {}
    fetcher._nowcoder_problem_meta_cache = cache

    seen_order: list[str] = []
    seen: set[str] = set()
    for r in rows:
        pid = str(r.get("problem_id") or "").strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        seen_order.append(pid)

    for pid in seen_order:
        if pid in cache:
            continue
        try:
            cache[pid] = _nowcoder_problem_meta_from_list_api(fetcher, pid)
        except Exception:
            cache[pid] = {}
        time.sleep(0.15)

    for r in rows:
        pid = str(r.get("problem_id") or "").strip()
        meta = cache.get(pid) or {}
        if meta.get("difficulty"):
            r["difficulty"] = meta["difficulty"]
        if meta.get("tags"):
            r["tags"] = meta["tags"]
        if not r.get("tags"):
            r["tags"] = []


def fetch_nowcoder_submissions(fetcher: Any) -> list[dict]:
    uid = (fetcher.config.nowcoder_uid or "").strip()
    if not uid:
        return []

    headers = {
        "Referer": f"{NOWCODER_BASE}/",
        "Accept": "text/html,application/xhtml+xml",
    }
    if fetcher.config.nowcoder_cookie:
        headers["Cookie"] = fetcher.config.nowcoder_cookie.strip()

    all_rows: list[dict] = []
    page = 1
    max_pages = 120
    page_size = 50
    while page <= max_pages:
        url = (
            f"{NOWCODER_BASE}/acm/contest/profile/{uid}/practice-coding"
            f"?pageSize={page_size}&page={page}&search=&statusTypeFilter=-1"
            f"&languageCategoryFilter=-1&orderType=DESC"
        )
        response = fetcher.session.get(url, headers=headers, timeout=fetcher.config.timeout)
        response.raise_for_status()
        chunk = _parse_nowcoder_practice_page(response.text)
        if not chunk:
            break
        all_rows.extend(chunk)
        if len(chunk) < page_size:
            break
        page += 1

    if all_rows:
        _nowcoder_enrich_practice_rows(fetcher, all_rows)

    return all_rows
