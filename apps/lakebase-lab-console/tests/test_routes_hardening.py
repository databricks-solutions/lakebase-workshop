"""Tests for SQL read-only enforcement and load-test ownership."""

import pytest
from fastapi import HTTPException

routes_data = pytest.importorskip("backend.routes_data")
routes_loadtest = pytest.importorskip("backend.routes_loadtest")
from backend.user_context import UserContext  # noqa: E402


def _user(email="jane@example.com"):
    return UserContext(email=email, schema="lakebase_lab_jane", project_id="p1")


def test_query_rejects_writes_and_ddl(monkeypatch):
    # execute_readonly should never be reached for disallowed statements.
    monkeypatch.setattr(routes_data, "execute_readonly",
                        lambda *a, **k: pytest.fail("should not execute"))
    for sql in ["DROP TABLE products", "DELETE FROM products", "UPDATE products SET x=1",
                "INSERT INTO products VALUES (1)", "GRANT ALL ON products TO x"]:
        with pytest.raises(HTTPException) as exc:
            routes_data.run_query(routes_data.QueryRequest(sql=sql), _user())
        assert exc.value.status_code == 400


def test_query_rejects_multiple_statements(monkeypatch):
    monkeypatch.setattr(routes_data, "execute_readonly",
                        lambda *a, **k: pytest.fail("should not execute"))
    with pytest.raises(HTTPException):
        routes_data.run_query(
            routes_data.QueryRequest(sql="SELECT 1; DROP TABLE products"), _user()
        )


def test_query_allows_select(monkeypatch):
    called = {}

    def fake_ro(user, sql, **kwargs):
        called["sql"] = sql
        called["max_rows"] = kwargs.get("max_rows")
        return [{"ok": 1}]

    monkeypatch.setattr(routes_data, "execute_readonly", fake_ro)
    out = routes_data.run_query(
        routes_data.QueryRequest(sql="SELECT * FROM products"), _user()
    )
    assert out == [{"ok": 1}]
    assert called["max_rows"] == routes_data._MAX_QUERY_ROWS


def test_loadtest_ownership_isolation():
    routes_loadtest._active_tests.clear()
    routes_loadtest._active_tests["t1"] = {"running": True, "owner": "owner@example.com"}

    # A different user cannot see or stop another user's test.
    with pytest.raises(HTTPException) as exc:
        routes_loadtest._owned_test("t1", _user("intruder@example.com"))
    assert exc.value.status_code == 404

    # The owner can.
    state = routes_loadtest._owned_test("t1", _user("owner@example.com"))
    assert state["owner"] == "owner@example.com"
    routes_loadtest._active_tests.clear()
