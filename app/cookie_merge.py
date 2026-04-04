"""Parse / serialize Cookie header strings; merge multiline key=value fragments."""

from __future__ import annotations


def parse_cookie_header(cookie: str) -> dict[str, str]:
    """Parse `a=b; c=d` into a dict (last wins on duplicate keys)."""
    out: dict[str, str] = {}
    if not cookie or not cookie.strip():
        return out
    for part in cookie.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        out[name] = value.strip()
    return out


def serialize_cookie(parts: dict[str, str]) -> str:
    """Join dict into `name=value; name2=value2` (sorted keys for stable output)."""
    if not parts:
        return ""
    return "; ".join(f"{k}={v}" for k, v in sorted(parts.items()))


def parse_kv_lines(text: str) -> dict[str, str]:
    """
    Multiline key=value (e.g. cf_clearance=...).
    Lines starting with # are ignored; empty lines skipped.
    """
    out: dict[str, str] = {}
    if not text:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if not name:
            continue
        out[name] = value.strip()
    return out


def merge_kv_cookie(kv_lines: str | None) -> str:
    """Build Cookie header from multiline name=value (Codeforces / Nowcoder)."""
    return serialize_cookie(parse_kv_lines(kv_lines or ""))


def merge_luogu_cookie(
    client_id_value: str | None,
    uid_cookie_value: str | None,
    extra_kv_lines: str | None,
) -> str:
    """Build luogu.com.cn Cookie: value-only __client_id / _uid plus optional extra lines."""
    parts = parse_kv_lines(extra_kv_lines or "")
    if client_id_value and client_id_value.strip():
        parts["__client_id"] = client_id_value.strip()
    if uid_cookie_value and uid_cookie_value.strip():
        parts["_uid"] = uid_cookie_value.strip()
    return serialize_cookie(parts)


def cookie_to_kv_lines(cookie: str) -> str:
    """Inverse for settings UI: merged Cookie -> sorted multiline name=value."""
    parts = parse_cookie_header(cookie)
    if not parts:
        return ""
    return "\n".join(f"{k}={v}" for k, v in sorted(parts.items()))


def kv_lines_excluding(parts: dict[str, str], omit: tuple[str, ...]) -> str:
    """Multiline name=value for keys not in omit (e.g. Luogu extra textarea)."""
    sub = {k: v for k, v in parts.items() if k not in omit}
    if not sub:
        return ""
    return "\n".join(f"{k}={v}" for k, v in sorted(sub.items()))


def cookie_get(parts: dict[str, str], *names: str) -> str:
    for n in names:
        if n in parts:
            return parts[n]
    return ""
