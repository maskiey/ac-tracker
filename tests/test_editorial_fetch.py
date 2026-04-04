from __future__ import annotations

from app.services.editorial_fetch import _rich_text_for_tag_inference


def test_rich_text_for_tag_inference_includes_plain_and_tex():
    html = (
        '<div class="subject-question">空字符串 删除字符</div>'
        '<img alt="\\texttt{dp}" src="https://hr.nowcoder.com/equation?tex=%5Ctexttt%7Bdp%7D" />'
    )
    t = _rich_text_for_tag_inference(html, max_len=8000)
    assert "空字符串" in t
    assert "texttt" in t.lower() or "dp" in t.lower()
