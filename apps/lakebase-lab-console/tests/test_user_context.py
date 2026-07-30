"""Tests for the fail-closed identity gate."""

import pytest
from fastapi import HTTPException

from backend import user_context


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


def test_apps_mode_requires_forwarded_identity(monkeypatch):
    monkeypatch.setenv("LAKEBASE_AUTH_MODE", "apps")
    monkeypatch.delenv("LAKEBASE_ALLOW_HEADERLESS_AUTH", raising=False)
    with pytest.raises(HTTPException) as exc:
        user_context.get_current_user(_FakeRequest(headers={}))
    assert exc.value.status_code == 401


def test_forwarded_email_builds_context(monkeypatch):
    monkeypatch.setenv("LAKEBASE_AUTH_MODE", "apps")
    ctx = user_context.get_current_user(
        _FakeRequest(headers={"x-forwarded-email": "jane.doe@example.com"})
    )
    assert ctx.email == "jane.doe@example.com"
    # The forwarded user token must never be retained on the context.
    assert not hasattr(ctx, "access_token")


def test_local_mode_allows_headerless(monkeypatch):
    monkeypatch.setenv("LAKEBASE_AUTH_MODE", "local")

    sentinel = user_context.UserContext(email="local@example.com", _is_local=True)
    monkeypatch.setattr(user_context, "_get_local_context", lambda: sentinel)

    ctx = user_context.get_current_user(_FakeRequest(headers={}))
    assert ctx is sentinel
