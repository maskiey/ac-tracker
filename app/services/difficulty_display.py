"""将各 OJ 存入库的原始难度字段统一为易读中文展示（仅用于 API 输出，不改库内原始值）。"""

from __future__ import annotations

# 与洛谷题库整数难度一致（与 fetcher.LUOGU_DIFFICULTY_LABEL 对齐）
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

def _cf_rating_band(r: int) -> str:
    """Codeforces 分数段色阶（与官网习惯一致）。"""
    if r < 1200:
        return "灰"
    if r < 1400:
        return "绿"
    if r < 1600:
        return "青"
    if r < 1900:
        return "蓝"
    if r < 2100:
        return "紫"
    if r < 2400:
        return "橙"
    return "红"


def format_difficulty_display(oj_source: str | None, raw: str | None) -> str:
    if raw is None:
        return "—"
    s = str(raw).strip()
    if not s or s == "—":
        return "—"

    oj = (oj_source or "").strip().lower()

    if oj == "codeforces":
        if s.isdigit():
            r = int(s)
            return f"{r} · {_cf_rating_band(r)}"
        return s

    if oj == "luogu":
        if s.isdigit():
            return LUOGU_DIFFICULTY_LABEL.get(int(s), s)
        return s

    if oj == "atcoder":
        # kenkoooo 等索引可能为 0–6000 的整数难度
        if s.isdigit():
            d = int(s)
            if d <= 0:
                return "—"
            if d < 400:
                return f"{d} · 易"
            if d < 800:
                return f"{d} · 偏易"
            if d < 1200:
                return f"{d} · 中"
            if d < 2000:
                return f"{d} · 偏难"
            return f"{d} · 难"
        return s

    if oj == "nowcoder":
        # 牛客题库公开接口返回的 difficulty 为整数难度分（非星级）
        if s.isdigit():
            return f"{int(s)} 分"
        return s

    return s
