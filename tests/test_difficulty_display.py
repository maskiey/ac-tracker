from __future__ import annotations

from app.services.difficulty_display import format_difficulty_display


def test_codeforces_rating():
    assert "1200" in format_difficulty_display("codeforces", "1200")
    assert "灰" in format_difficulty_display("codeforces", "800")
    assert "红" in format_difficulty_display("codeforces", "3000")


def test_luogu_numeric():
    assert format_difficulty_display("luogu", "1") == "入门"
    assert format_difficulty_display("luogu", "普及-") == "普及-"


def test_nowcoder_score():
    assert format_difficulty_display("nowcoder", "1800") == "1800 分"
    assert format_difficulty_display("nowcoder", "100") == "100 分"


def test_empty():
    assert format_difficulty_display("codeforces", None) == "—"
    assert format_difficulty_display("luogu", "") == "—"
