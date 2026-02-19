from __future__ import annotations

import pytest
from fastapi import HTTPException

from apps.api.security import _extract_bearer_token, require_api_auth
from kbeton.core.config import settings


def test_extract_bearer_token():
    assert _extract_bearer_token(None) == ""
    assert _extract_bearer_token("") == ""
    assert _extract_bearer_token("Basic abc") == ""
    assert _extract_bearer_token("Bearer token123") == "token123"


def test_require_api_auth_disabled(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", False)
    require_api_auth()


def test_require_api_auth_rejects_missing_token(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", "secret")
    with pytest.raises(HTTPException) as ex:
        require_api_auth()
    assert ex.value.status_code == 401


def test_require_api_auth_accepts_bearer(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", "secret")
    require_api_auth(authorization="Bearer secret")


def test_require_api_auth_accepts_x_api_key(monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_token", "secret")
    require_api_auth(x_api_key="secret")
