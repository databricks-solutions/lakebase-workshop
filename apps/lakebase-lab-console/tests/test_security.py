"""Unit tests for the shared security helpers."""

from pathlib import Path

import pytest

from backend import security


def test_get_auth_mode_explicit(monkeypatch):
    monkeypatch.setenv("LAKEBASE_AUTH_MODE", "apps")
    assert security.get_auth_mode() == "apps"
    monkeypatch.setenv("LAKEBASE_AUTH_MODE", "local")
    assert security.get_auth_mode() == "local"


def test_get_auth_mode_autodetect(monkeypatch):
    monkeypatch.delenv("LAKEBASE_AUTH_MODE", raising=False)
    monkeypatch.delenv("DATABRICKS_APP_NAME", raising=False)
    assert security.get_auth_mode() == "local"
    monkeypatch.setenv("DATABRICKS_APP_NAME", "lakebase-lab-console")
    assert security.get_auth_mode() == "apps"


@pytest.mark.parametrize("value,ok", [
    ("lakebase_lab_jane_doe", True),
    ("public", True),
    ("", False),
    ("bad-schema", False),       # hyphen not allowed
    ("drop table x", False),     # spaces
    ("a" * 64, False),           # too long
])
def test_is_valid_schema(value, ok):
    assert security.is_valid_schema(value) is ok


def test_assert_valid_schema_raises():
    with pytest.raises(ValueError):
        security.assert_valid_schema("bad;schema")


@pytest.mark.parametrize("value,ok", [
    ("production", True),
    ("lab-abc-123", True),
    ("Production", False),   # uppercase
    ("1branch", False),      # must start with a letter
    ("", False),
])
def test_is_valid_resource_id(value, ok):
    assert security.is_valid_resource_id(value) is ok


@pytest.mark.parametrize("value,ok", [
    ("products", True),
    ("api_clients", True),
    ("robert'); DROP TABLE", False),
    ("has-hyphen", False),
    ("", False),
])
def test_is_valid_pg_ident(value, ok):
    assert security.is_valid_pg_ident(value) is ok


@pytest.mark.parametrize("value,expected", [
    (None, 50),
    (10, 10),
    (0, 1),
    (-5, 1),
    (99999, 500),
    ("not-a-number", 50),
])
def test_clamp_limit(value, expected):
    assert security.clamp_limit(value, default=50, maximum=500) == expected


def test_resolve_static_file_blocks_traversal(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("root")
    (static / "app.js").write_text("ok")
    secret = tmp_path / "secret.txt"
    secret.write_text("nope")

    assert security.resolve_static_file(static, "app.js") == (static / "app.js").resolve()
    assert security.resolve_static_file(static, "../secret.txt") is None
    assert security.resolve_static_file(static, "..%2f..%2fsecret.txt") is None
    assert security.resolve_static_file(static, "") is None
    assert security.resolve_static_file(static, "does_not_exist.js") is None


def test_normalized_and_capped_decode():
    body = b"x" * 100
    assert security._decode_capped(body, 1000) == "x" * 100
    capped = security._decode_capped(b"y" * 50, 10)
    assert capped.startswith("y" * 10)
    assert "truncated" in capped


def test_outbound_request_requires_https():
    with pytest.raises(security.OutboundHTTPError):
        security.outbound_request(
            "http://example.com", method="GET", headers={}
        )
