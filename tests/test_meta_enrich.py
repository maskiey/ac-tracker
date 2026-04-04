from __future__ import annotations

from app.services.tags import infer_tags_from_editorial_text, infer_tags_from_title, is_unlabeled_for_knowledge


def test_is_unlabeled_for_knowledge():
    assert is_unlabeled_for_knowledge([]) is True
    assert is_unlabeled_for_knowledge(None) is True
    assert is_unlabeled_for_knowledge(["牛客"]) is True
    assert is_unlabeled_for_knowledge(["动态规划"]) is False


def test_infer_tags_from_title_hits_aliases():
    out = infer_tags_from_title("二分查找与双指针入门")
    assert "二分" in out
    assert "双指针" in out


def test_infer_tags_from_title_cf_english():
    out = infer_tags_from_title("graphs and shortest paths")
    assert "图论" in out
    assert "最短路" in out


def test_infer_tags_from_editorial_text_long_snippet():
    blob = "题目大意：给定一棵树。" + "解法使用树形 dp 维护子树信息。" * 20
    out = infer_tags_from_editorial_text(blob)
    assert out and ("树形DP" in out or "动态规划" in out)
