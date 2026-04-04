"""从各 OJ 题面/题解页拉取纯文本，供知识点关键词推断（同步流程内使用）。"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

_CF_PID_RE = re.compile(r"^(\d+)([A-Za-z]\d*)$")


def _append_unique_part(parts: list[str], chunk: str, max_piece: int = 20000) -> None:
    """避免题面与题解页返回同一段 HTML 时重复堆叠。"""
    t = (chunk or "").strip()
    if not t:
        return
    if max_piece and len(t) > max_piece:
        t = t[:max_piece]
    for p in parts:
        if len(t) > 80 and (t in p or p in t):
            return
    parts.append(t)


def _html_to_text(html: str, max_len: int = 24000) -> str:
    if not html or not html.strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    if len(text) > max_len:
        return text[:max_len]
    return text


def _rich_text_for_tag_inference(html: str, max_len: int = 28000) -> str:
    """
    可见文本 + img 的 alt 与 equation?tex= 中的 LaTeX。
    牛客/部分 OJ 题面正文多为公式图，纯 get_text 会漏掉「dp」「字符串」等可推断词。
    """
    if not html or not html.strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    chunks: list[str] = []
    plain = soup.get_text(" ", strip=True)
    if plain:
        chunks.append(plain[: max(4000, max_len // 2)])
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").strip()
        if len(alt) > 1:
            chunks.append(alt[:4000])
        src = (img.get("src") or "").strip()
        if not src or ("tex=" not in src and "equation" not in src.lower()):
            continue
        try:
            q = parse_qs(urlparse(src).query)
            tex = (q.get("tex") or [""])[0]
            if tex:
                chunks.append(unquote(tex)[:4000])
        except Exception:
            continue
    out = "\n".join(x for x in chunks if x)
    if len(out) > max_len:
        return out[:max_len]
    return out


def _session_get_text(fetcher: Any, url: str) -> str:
    r = fetcher.session.get(
        url,
        timeout=fetcher.config.timeout,
        headers={
            "User-Agent": fetcher.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    r.raise_for_status()
    return r.text


def _cf_collect_text(fetcher: Any, pid: str) -> str:
    m = _CF_PID_RE.match(pid.strip())
    if not m:
        return ""
    cid, idx = m.group(1), m.group(2)
    urls = [
        f"https://codeforces.com/problemset/problem/{cid}/{idx}",
        f"https://codeforces.com/contest/{cid}/problem/{idx}",
        f"https://codeforces.com/gym/{cid}/problem/{idx}",
    ]
    soup: BeautifulSoup | None = None
    for url in urls:
        try:
            resp = fetcher._get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            break
        except Exception:
            continue
    if soup is None:
        return ""
    parts: list[str] = []
    stmt = soup.select_one(".problem-statement")
    if stmt:
        parts.append(_rich_text_for_tag_inference(str(stmt), 16000))
    blog_links: list[tuple[str, str]] = []
    for a in soup.select('a[href*="/blog/entry/"]'):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = "https://codeforces.com" + href
        if "/blog/entry/" not in href:
            continue
        label = a.get_text(" ", strip=True).lower()
        blog_links.append((href, label))
    blog_links.sort(key=lambda x: (0 if "tutorial" in x[1] else 1, x[0]))
    seen_blog: set[str] = set()
    for href, _ in blog_links[:2]:
        if href in seen_blog:
            continue
        seen_blog.add(href)
        try:
            br = fetcher._get(href)
            bs = BeautifulSoup(br.text, "html.parser")
            topic = bs.select_one(".topic-content") or bs.select_one(".content") or bs
            parts.append(_rich_text_for_tag_inference(str(topic), 18000))
        except Exception:
            continue
    return "\n".join(p for p in parts if p)


def _luogu_collect_text(fetcher: Any, pid: str) -> str:
    parts: list[str] = []
    try:
        payload = fetcher._get_luogu_json(f"/problem/{pid}?_contentOnly=1")
        prob = (payload.get("data") or {}).get("problem") or {}
        if isinstance(prob, dict):
            for key in ("content", "background", "description", "translation"):
                raw = prob.get(key)
                if isinstance(raw, str) and raw.strip():
                    parts.append(_rich_text_for_tag_inference(raw, 14000))
    except Exception:
        pass
    try:
        html = _session_get_text(fetcher, f"https://www.luogu.com.cn/problem/{pid}/solution")
        sp = BeautifulSoup(html, "html.parser")
        for sel in (".solution-article", "article", ".markdown-body", "main"):
            node = sp.select_one(sel)
            if node:
                parts.append(_rich_text_for_tag_inference(str(node), 18000))
                break
        else:
            parts.append(_rich_text_for_tag_inference(html, 14000))
    except Exception:
        pass
    return "\n".join(p for p in parts if p)


def _atcoder_collect_text(fetcher: Any, pid: str) -> str:
    pid = str(pid).strip()
    if "_" not in pid:
        return ""
    contest = pid.split("_", 1)[0]
    url = f"https://atcoder.jp/contests/{contest}/tasks/{pid}"
    try:
        html = _session_get_text(fetcher, url)
    except Exception:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    parts: list[str] = []
    stmt_root = soup.select_one("#task-statement") or soup
    zh = stmt_root.select_one("span.lang-zh")
    if zh:
        parts.append(_rich_text_for_tag_inference(str(zh), 18000))
    en = stmt_root.select_one("span.lang-en")
    if en:
        parts.append(_rich_text_for_tag_inference(str(en), 18000))
    if not parts:
        stmt = soup.select_one("span.lang-en") or soup.select_one("#task-statement") or soup.select_one(".lang")
        if stmt:
            parts.append(_rich_text_for_tag_inference(str(stmt), 18000))
        else:
            parts.append(_rich_text_for_tag_inference(html, 16000))
    got_ed = False
    for a in soup.select('a[href*="/editorial"], a[href*="editorial"]'):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = "https://atcoder.jp" + href
        if "atcoder.jp" not in href:
            continue
        try:
            eh = _session_get_text(fetcher, href)
            parts.append(_rich_text_for_tag_inference(eh, 22000))
            got_ed = True
            break
        except Exception:
            continue
    if not got_ed:
        ed_contest = f"https://atcoder.jp/contests/{contest}/editorial"
        try:
            ed_html = _session_get_text(fetcher, ed_contest)
            parts.append(_rich_text_for_tag_inference(ed_html, 16000))
        except Exception:
            pass
    return "\n".join(p for p in parts if p)


def _nowcoder_collect_text(fetcher: Any, pid: str) -> str:
    """
    题面 + 多路径题解/讨论页（与洛谷「题面 JSON + /solution」思路一致，尽量多抓正文再关键词推断）。
    """
    if not str(pid).strip().isdigit():
        return ""
    headers = {
        "User-Agent": fetcher.config.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Referer": "https://ac.nowcoder.com/",
    }
    nc = (getattr(fetcher.config, "nowcoder_cookie", None) or "").strip()
    if nc:
        headers["Cookie"] = nc

    parts: list[str] = []
    base_paths = [
        f"https://ac.nowcoder.com/acm/problem/{pid}",
        f"https://ac.nowcoder.com/acm/problem/blogs/{pid}",
        f"https://ac.nowcoder.com/acm/problem/{pid}/solution",
        f"https://ac.nowcoder.com/acm/problem/{pid}/solutions",
        f"https://ac.nowcoder.com/acm/problem/{pid}/discuss",
        f"https://ac.nowcoder.com/acm/problem/discuss?problemId={pid}",
    ]
    seen_url: set[str] = set()
    for url in base_paths:
        if url in seen_url:
            continue
        seen_url.add(url)
        try:
            r = fetcher.session.get(url, timeout=fetcher.config.timeout, headers=headers)
            if r.status_code != 200:
                continue
            html = r.text
            sp = BeautifulSoup(html, "html.parser")
            for sel in (
                ".subject-describe",
                ".subject-question",
                ".terminal-topic",
                ".question-main",
                ".solution-content",
                ".solution-item",
                ".discuss-main",
                "article",
                ".markdown-body",
                ".nc-markdown",
                "main",
                ".acm-content",
            ):
                node = sp.select_one(sel)
                if node:
                    _append_unique_part(parts, _rich_text_for_tag_inference(str(node), 22000))
                    break
            else:
                _append_unique_part(parts, _rich_text_for_tag_inference(html, 20000))
        except Exception:
            continue

    try:
        qa_url = f"https://ac.nowcoder.com/acm/problem/qa/question-list?problemId={pid}"
        r = fetcher.session.get(qa_url, timeout=fetcher.config.timeout, headers=headers)
        if r.status_code == 200 and "application/json" in (r.headers.get("Content-Type") or ""):
            payload = r.json()
            if isinstance(payload, dict) and payload.get("code") == 0:
                data = payload.get("data") or {}
                items = data.get("list") or data.get("questionList") or data.get("records") or []
                if isinstance(items, list):
                    for it in items[:5]:
                        if not isinstance(it, dict):
                            continue
                        for key in ("content", "answer", "bestAnswer", "replyContent", "title"):
                            raw = it.get(key)
                            if isinstance(raw, str) and raw.strip():
                                _append_unique_part(parts, _rich_text_for_tag_inference(raw, 12000))
                                break
    except Exception:
        pass

    merged = "\n".join(p for p in parts if p)
    return merged[:48000] if len(merged) > 48000 else merged


def fetch_editorial_plaintext_for_problem(
    fetcher: Any,
    oj: str,
    pid: str,
    title_hint: str | None,
) -> str:
    """
    返回「标题 + 题面/题解」合并文本，供 infer_tags_from_editorial_text。
    各站失败时仍可能仅有 title_hint。
    """
    chunks: list[str] = []
    if title_hint and str(title_hint).strip():
        chunks.append(str(title_hint).strip())
    oj = (oj or "").strip().lower()
    body = ""
    try:
        if oj == "codeforces":
            body = _cf_collect_text(fetcher, pid)
        elif oj == "luogu":
            body = _luogu_collect_text(fetcher, pid)
        elif oj == "atcoder":
            body = _atcoder_collect_text(fetcher, pid)
        elif oj == "nowcoder":
            body = _nowcoder_collect_text(fetcher, pid)
    except Exception:
        body = ""
    if body:
        chunks.append(body)
    return "\n".join(chunks)
