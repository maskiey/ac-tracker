from __future__ import annotations

import pytest

import app.services.app_meta as app_meta


def _clear_update_cache() -> None:
    app_meta._CACHE.clear()


class _OkResp:
    def __init__(self, payload: dict, status: int = 200):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self) -> dict:
        return self._payload


def test_get_about_payload_structure():
    data = app_meta.get_about_payload()
    assert "version" in data
    assert "repo_url" in data
    assert isinstance(data.get("third_party"), list)


def test_update_available_when_remote_newer(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_update_cache()
    monkeypatch.setattr(app_meta, "APP_VERSION", "1.0.0", raising=False)

    def fake_get(url: str, **kwargs):
        return _OkResp({"tag_name": "v2.0.0"})

    monkeypatch.setattr(app_meta.requests, "get", fake_get)
    d = app_meta.get_update_check_payload()
    assert d["update_check_enabled"] is True
    assert d["update_available"] is True
    assert d["latest_version"] == "2.0.0"


def test_update_not_available_when_current_is_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_update_cache()
    monkeypatch.setattr(app_meta, "APP_VERSION", "2.0.0", raising=False)

    def fake_get(url: str, **kwargs):
        return _OkResp({"tag_name": "v2.0.0"})

    monkeypatch.setattr(app_meta.requests, "get", fake_get)
    d = app_meta.get_update_check_payload()
    assert d["update_available"] is False


def test_update_check_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_update_cache()
    monkeypatch.setenv("ACM_TRACKER_DISABLE_UPDATE_CHECK", "1")
    d = app_meta.get_update_check_payload()
    assert d["update_check_enabled"] is False
    assert "update_available" not in d or d.get("update_available") is False


def test_update_check_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_update_cache()

    def boom(*a, **k):
        raise app_meta.requests.RequestException("offline")

    monkeypatch.setattr(app_meta.requests, "get", boom)
    d = app_meta.get_update_check_payload()
    assert d["check_error"] is True
    assert d["update_available"] is False
