from __future__ import annotations

from app.cookie_merge import (
    cookie_to_kv_lines,
    kv_lines_excluding,
    merge_kv_cookie,
    merge_luogu_cookie,
    parse_cookie_header,
    parse_kv_lines,
    serialize_cookie,
)


def test_parse_and_serialize_roundtrip():
    s = "a=1; b=two"
    d = parse_cookie_header(s)
    assert d == {"a": "1", "b": "two"}
    assert "a=1" in serialize_cookie(d) and "b=two" in serialize_cookie(d)


def test_parse_kv_lines():
    text = """
# comment
cf_clearance=abc
__cf_bm=xyz
"""
    assert parse_kv_lines(text) == {"cf_clearance": "abc", "__cf_bm": "xyz"}


def test_merge_kv_cookie():
    assert "a=1" in merge_kv_cookie("a=1")


def test_merge_luogu_value_only_fields():
    out = merge_luogu_cookie("cid123", "1430344", None)
    d = parse_cookie_header(out)
    assert d.get("__client_id") == "cid123"
    assert d.get("_uid") == "1430344"


def test_merge_luogu_named_override_extra_kv():
    out = merge_luogu_cookie("newcid", None, "__client_id=old\n_uid=1")
    assert "__client_id=newcid" in out
    assert "_uid=1" in out


def test_cookie_to_kv_lines():
    assert cookie_to_kv_lines("b=2; a=1") == "a=1\nb=2"


def test_kv_lines_excluding():
    parts = parse_cookie_header("__client_id=x; _uid=1; C3VK=ab")
    assert kv_lines_excluding(parts, ("__client_id", "_uid")) == "C3VK=ab"
