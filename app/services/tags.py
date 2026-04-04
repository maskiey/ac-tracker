from __future__ import annotations

import re


CF_TAG_TRANSLATIONS = {
    "2-sat": "2-SAT",
    "binary search": "二分",
    "bitmasks": "状压",
    "brute force": "暴力枚举",
    "chinese remainder theorem": "中国剩余定理",
    "combinatorics": "组合数学",
    "constructive algorithms": "构造",
    "data structures": "数据结构",
    "dfs and similar": "DFS",
    "divide and conquer": "分治",
    "dp": "动态规划",
    "dsu": "并查集",
    "expression parsing": "表达式解析",
    "fft": "FFT",
    "flows": "网络流",
    "games": "博弈论",
    "geometry": "计算几何",
    "graph matchings": "图匹配",
    "graphs": "图论",
    "greedy": "贪心",
    "hashing": "哈希",
    "implementation": "模拟",
    "interactive": "交互",
    "math": "数学",
    "matrices": "矩阵",
    "meet-in-the-middle": "折半搜索",
    "number theory": "数论",
    "probabilities": "概率论",
    "schedules": "调度",
    "shortest paths": "最短路",
    "sortings": "排序",
    "string suffix structures": "后缀数据结构",
    "strings": "字符串",
    "ternary search": "三分",
    "trees": "树",
    "two pointers": "双指针",
}

TAG_ALIAS_TRANSLATIONS: list[tuple[str, str]] = [
    ("动态规划 dp", "动态规划"),
    ("动态规划", "动态规划"),
    ("dp", "动态规划"),
    ("树形 dp", "树形DP"),
    ("数位 dp", "数位DP"),
    ("区间 dp", "区间DP"),
    ("背包 dp", "背包DP"),
    ("lis", "最长上升子序列"),
    ("lcs", "最长公共子序列"),
    ("mst", "最小生成树"),
    ("lca", "最近公共祖先"),
    ("ac 自动机", "AC自动机"),
    ("kmp", "KMP"),
    ("manacher", "Manacher"),
    ("st 表", "ST表"),
    ("树状数组", "树状数组"),
    ("线段树", "线段树"),
    ("前缀和", "前缀和"),
    ("差分", "差分"),
    ("并查集", "并查集"),
    ("最短路", "最短路"),
    ("拓扑", "拓扑排序"),
    ("欧拉", "欧拉路径"),
    ("二分图", "二分图"),
    ("网络流", "网络流"),
    ("强连通", "强连通分量"),
    ("后缀", "后缀数据结构"),
    ("字典树", "字典树"),
    ("trie", "字典树"),
    ("hash", "哈希"),
    ("回文", "回文"),
    ("二分", "二分"),
    ("三分", "三分"),
    ("分治", "分治"),
    ("双指针", "双指针"),
    ("离散化", "离散化"),
    ("质数", "质数"),
    ("gcd", "最大公约数"),
    ("欧拉函数", "欧拉函数"),
    ("同余", "同余"),
    ("筛法", "筛法"),
    ("因子", "因子分解"),
    ("组合", "组合数学"),
    ("计数", "计数"),
    ("容斥", "容斥原理"),
    ("生成函数", "生成函数"),
    ("排列组合", "排列组合"),
    ("矩阵", "矩阵"),
    ("高精度", "高精度"),
    ("进制", "进制"),
    ("线性代数", "线性代数"),
    ("位运算", "位运算"),
    ("bitset", "位集"),
    ("模拟", "模拟"),
    ("构造", "构造"),
    ("暴力", "暴力枚举"),
    ("几何", "计算几何"),
    ("凸包", "凸包"),
    ("叉积", "叉积"),
    ("博弈", "博弈论"),
    ("概率", "概率论"),
    ("交互", "交互"),
    ("搜索", "搜索"),
    ("dfs", "DFS"),
    ("bfs", "BFS"),
    ("回溯", "回溯"),
    ("剪枝", "剪枝"),
    ("枚举", "枚举"),
    ("递推", "递推"),
    ("贪心", "贪心"),
    ("图论", "图论"),
    ("数据结构", "数据结构"),
    ("字符串", "字符串"),
    ("数论", "数论"),
    ("数学", "数学"),
    # 牛客等中文题面常见表述（公式图转文本后仍可能缺省，补充短语匹配）
    ("滑动窗口", "双指针"),
    ("单调栈", "数据结构"),
    ("单调队列", "数据结构"),
    ("双端队列", "数据结构"),
    ("二叉堆", "数据结构"),
    ("快速幂", "数学"),
    ("逆元", "数学"),
    ("扩展欧几里得", "数学"),
    ("费马小定理", "数论"),
    ("中国剩余定理", "中国剩余定理"),
    ("线段树合并", "线段树"),
    ("树链剖分", "树"),
    ("长链剖分", "树"),
    ("虚树", "树"),
    ("点分治", "树"),
    ("边分治", "树"),
    ("cdq 分治", "分治"),
    ("cdq分治", "分治"),
    ("莫队", "数据结构"),
    ("整除分块", "数论"),
    ("根号分治", "分治"),
]

IGNORE_TAG_PATTERNS = (
    r"^\d{4}$",
    r"^noip",
    r"^csp",
    r"^noi",
    r"^cf\b",
    r"^省选",
    r"^提高组",
    r"^普及组",
    r"^入门",
    r"^模板$",
    r"^蓝桥杯",
    r"^usaco",
    r"^apio",
    r"^ioi",
    r"^年份",
    r"^题单",
    r"^洛谷",
    r"^牛客$",
    r"^nowcoder$",
)


def _clean_text(raw_tag: object) -> str:
    text = str(raw_tag).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _is_ignorable_tag(tag: str) -> bool:
    cleaned = tag.strip().lower()
    if not cleaned:
        return True
    if cleaned.isdigit():
        return True
    return any(re.search(pattern, cleaned) for pattern in IGNORE_TAG_PATTERNS)


def _translate_tag(raw_tag: object) -> str | None:
    if raw_tag is None or isinstance(raw_tag, (int, float)):
        return None

    cleaned = _clean_text(raw_tag)
    lowered = cleaned.lower()
    if _is_ignorable_tag(lowered):
        return None

    if lowered in CF_TAG_TRANSLATIONS:
        return CF_TAG_TRANSLATIONS[lowered]

    for keyword, translated in TAG_ALIAS_TRANSLATIONS:
        if keyword in lowered:
            return translated

    if re.search(r"[\u4e00-\u9fff]", cleaned):
        cleaned = re.sub(r"\s*dp\b", "DP", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace(" DP", "DP")
        return cleaned

    return cleaned


def tags_for_knowledge_stats(stored: list[str] | None) -> list[str]:
    """知识点分布 / 筛选：去掉已入库的平台占位标签（如「牛客」）。"""
    if not stored:
        return []
    out: list[str] = []
    for t in stored:
        s = str(t).strip()
        if not s or _is_ignorable_tag(s.lower()):
            continue
        if s in ("牛客", "Nowcoder", "NOWCODER"):
            continue
        # 历史版本用题库难度分合成的「牛客·0–400」等，不再作为知识点统计
        if s.startswith("牛客·"):
            continue
        out.append(s)
    return out


def is_unlabeled_for_knowledge(stored: list[str] | None) -> bool:
    """入库标签在知识点统计下是否为空（即视为「未标注」）。"""
    return len(tags_for_knowledge_stats(stored)) == 0


def infer_tags_from_editorial_text(text: str) -> list[str]:
    """
    从题面、题解等较长文本匹配知识点别名（与标题规则一致）。
    """
    if not text or not str(text).strip():
        return []
    raw: list[str] = []
    tl = str(text).strip()[:65536].lower()
    for kw, zh in sorted(TAG_ALIAS_TRANSLATIONS, key=lambda x: -len(x[0])):
        if kw.lower() in tl:
            raw.append(zh)
    for en, zh in CF_TAG_TRANSLATIONS.items():
        if en in tl:
            raw.append(zh)
    return normalize_tags(raw)


def infer_tags_from_title(title: str) -> list[str]:
    """从题目标题启发式推断知识点（内部委托 infer_tags_from_editorial_text）。"""
    return infer_tags_from_editorial_text(title or "")


# 入库标签为空或全部被过滤时，知识点柱状图 / 标签列表仍归入此类，避免个别来源整站「消失」
UNLABELED_KNOWLEDGE_TAG = "未标注"


def knowledge_tags_with_fallback(stored: list[str] | None) -> list[str]:
    """用于统计与展示的知识点标签：在 tags_for_knowledge_stats 为空时返回「未标注」。"""
    t = tags_for_knowledge_stats(stored)
    if t:
        return t
    return [UNLABELED_KNOWLEDGE_TAG]


def normalize_tags(tags: list[str] | tuple[str, ...] | None) -> list[str]:
    if not tags:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    saw_unknown_non_ignored = False
    for raw_tag in tags:
        translated = _translate_tag(raw_tag)
        if translated is None:
            if raw_tag not in (None, ""):
                raw_text = _clean_text(raw_tag)
                if raw_text and not _is_ignorable_tag(raw_text.lower()):
                    saw_unknown_non_ignored = True
            continue
        if translated not in seen:
            seen.add(translated)
            normalized.append(translated)

    if normalized:
        return normalized
    if saw_unknown_non_ignored:
        return ["其他"]
    return []
