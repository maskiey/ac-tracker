from __future__ import annotations

from app.extra_oj import (
    _atcoder_difficulty_str,
    _atcoder_fallback_tags,
    _atcoder_tags_from_meta,
    _normalize_atcoder_result,
    _nowcoder_row_tag_names,
    _parse_nowcoder_practice_page,
)


def test_parse_nowcoder_practice_table():
    html = """
    <html><body><table><tbody>
    <tr>
      <td><a href="/acm/contest/view-submission?submissionId=80978536&uid=1">80978536</a></td>
      <td><a href="/acm/problem/308921">小红有无穷无尽的数</a></td>
      <td><a class="font-green">答案正确</a></td>
      <td><span>100</span></td>
      <td>46</td>
      <td>708</td>
      <td>1867</td>
      <td>C++</td>
      <td>2025-11-30 22:35:16</td>
    </tr>
    <tr>
      <td><a href="/acm/contest/view-submission?submissionId=80978526&uid=1">80978526</a></td>
      <td><a href="/acm/problem/308921">小红有无穷无尽的数</a></td>
      <td><a>运行超时</a></td>
      <td><span>92.50</span></td>
      <td>1001</td>
      <td>0</td>
      <td>1888</td>
      <td>C++</td>
      <td>2025-11-30 22:34:44</td>
    </tr>
    </tbody></table></body></html>
    """
    rows = _parse_nowcoder_practice_page(html)
    assert len(rows) == 2
    assert rows[0]["problem_id"] == "308921"
    assert rows[0]["status"] == "AC"
    assert rows[1]["status"] == "TLE"


def test_atcoder_fallback_tags():
    assert "AtCoder ABC" in _atcoder_fallback_tags("abc400_a")
    assert "AtCoder ARC" in _atcoder_fallback_tags("arc100_c")
    assert "AtCoder" in _atcoder_fallback_tags("xyz123")


def test_atcoder_difficulty_and_tags_from_meta():
    models = {"abc100_a": {"difficulty": 800, "rawDifficulty": 800}}
    assert _atcoder_difficulty_str("abc100_a", models) == "800"
    assert _atcoder_difficulty_str("missing", models) is None
    assert "动态规划" in _atcoder_tags_from_meta({"tags": ["dp", "math"]})
    assert "数学" in _atcoder_tags_from_meta(
        {"tags": [{"name": "dp"}, {"slug": "math", "name": "math"}]}
    )
    assert "动态规划" in _atcoder_tags_from_meta({"classifications": ["dp"]})


def test_atcoder_empty_meta_merges_title_infer_and_series_fallback():
    from app.extra_oj import _atcoder_fallback_tags
    from app.services.tags import infer_tags_from_title, normalize_tags

    ti = infer_tags_from_title("区间 DP 练习")
    fb = _atcoder_fallback_tags("abc300_d")
    out = normalize_tags([*ti, *fb])
    assert "AtCoder ABC" in out
    assert "动态规划" in out or "区间DP" in out


def test_normalize_atcoder_result():
    assert _normalize_atcoder_result("AC") == "AC"
    assert _normalize_atcoder_result("WA") == "WA"
    assert _normalize_atcoder_result("WJ") == "UNKNOWN"
    assert _normalize_atcoder_result("TLE") == "TLE"


def test_knowledge_tags_with_fallback_unlabeled():
    from app.services.tags import UNLABELED_KNOWLEDGE_TAG, knowledge_tags_with_fallback

    assert knowledge_tags_with_fallback(None) == [UNLABELED_KNOWLEDGE_TAG]
    assert knowledge_tags_with_fallback([]) == [UNLABELED_KNOWLEDGE_TAG]
    assert knowledge_tags_with_fallback(["动态规划"]) == ["动态规划"]


def test_nowcoder_taglist_normalizes_into_knowledge_tags():
    from app.services.tags import normalize_tags

    out = normalize_tags(["逆元", "数学", "快速幂"])
    assert "数学" in out


def test_nowcoder_row_tag_names_uses_taglist_only():
    """知识点仅来自 tagList；来源类标签在 sourceTagList 中，不并入知识点。"""
    row = {
        "tagList": [{"name": "动态规划"}, {"name": "数学"}],
        "sourceTagList": [
            {"name": "牛客"},
            {"name": "牛客周赛"},
            {"name": "高校赛"},
        ],
    }
    names = _nowcoder_row_tag_names(row)
    assert "动态规划" in names
    assert "数学" in names
    assert "高校赛" not in names
    assert "牛客" not in names
    assert "牛客周赛" not in names


def test_nowcoder_row_tag_names_parses_comma_separated_tags_field():
    row = {"tags": "贪心,数学|图论"}
    names = _nowcoder_row_tag_names(row)
    assert "贪心" in names
    assert "数学" in names
    assert "图论" in names

