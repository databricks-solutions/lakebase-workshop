"""Tests for the managed agent memory routes (sessions + memory via /api/2.0/agents)."""

import pytest
from fastapi import HTTPException

routes_agent = pytest.importorskip("backend.routes_agent")
from backend.user_context import UserContext  # noqa: E402


class FakeApiError(Exception):
    def __init__(self, error_code, msg="boom"):
        super().__init__(msg)
        self.error_code = error_code


class FakeApi:
    """Records calls and returns canned responses keyed by (method, path)."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def do(self, method, path, query=None, body=None):
        self.calls.append((method, path, query, body))
        resp = self.responses.get((method, path))
        if isinstance(resp, Exception):
            raise resp
        if callable(resp):
            return resp(query, body)
        return resp if resp is not None else {}


@pytest.fixture
def user():
    return UserContext(email="jane.doe@example.com", schema="s", project_id="p")


def _install(monkeypatch, responses):
    api = FakeApi(responses)
    ws = type("WS", (), {"api_client": api})()
    monkeypatch.setattr(routes_agent, "_get_workspace_client", lambda: ws)
    return api


BASE = "/api/2.0/agents"


def test_store_ids_match_lab_convention(user):
    assert user.session_store_id == "lab-jane-doe-sessions"
    assert user.memory_store_id == "lab-jane-doe-memory"
    long = UserContext(email=("x" * 60) + "@example.com")
    assert len(long.session_store_id) <= 56 and len(long.memory_store_id) <= 56


def test_list_sessions_only_returns_callers_sessions(monkeypatch, user):
    _install(monkeypatch, {("GET", f"{BASE}/session-stores/lab-jane-doe-sessions/sessions"): {"sessions": [
        {"session_id": "a", "actor_id": user.email, "create_time": "2026-01-01"},
        {"session_id": "b", "actor_id": "someone@else.com", "create_time": "2026-01-02"},
    ]}})
    out = routes_agent.list_sessions(limit=20, user=user)
    assert [s["session_id"] for s in out] == ["a"]


def test_messages_reject_other_actors_session(monkeypatch, user):
    _install(monkeypatch, {("GET", f"{BASE}/session-stores/lab-jane-doe-sessions/sessions/t1"):
                           {"session_id": "t1", "actor_id": "someone@else.com"}})
    with pytest.raises(HTTPException) as exc:
        routes_agent.get_messages("t1", user=user)
    assert exc.value.status_code == 404


def test_invalid_session_id_rejected(monkeypatch, user):
    api = _install(monkeypatch, {})
    with pytest.raises(HTTPException) as exc:
        routes_agent.get_messages("../../memory-stores/x", user=user)
    assert exc.value.status_code == 400
    assert api.calls == []


def test_messages_replayed_in_order(monkeypatch, user):
    sess = f"{BASE}/session-stores/lab-jane-doe-sessions/sessions/t1"
    api = _install(monkeypatch, {
        ("GET", sess): {"session_id": "t1", "actor_id": user.email},
        ("GET", f"{sess}/items"): {"session_items": [
            {"item_id": "1", "data": {"type": "message", "role": "user", "content": "hi"}},
            {"item_id": "2", "data": {"type": "message", "role": "assistant", "content": "hello"}},
        ]},
    })
    out = routes_agent.get_messages("t1", user=user)
    assert [(m["role"], m["content"]) for m in out] == [("user", "hi"), ("assistant", "hello")]
    assert api.calls[-1][2]["order_by"] == "create_time asc"


def test_put_memory_updates_existing_entry(monkeypatch, user):
    entries = f"{BASE}/memory-stores/lab-jane-doe-memory/entries"
    name = "memory-stores/lab-jane-doe-memory/entries/e1"
    api = _install(monkeypatch, {
        ("POST", entries): FakeApiError("ALREADY_EXISTS"),
        ("GET", entries): {"managed_memory_entries": [{"name": name, "path": "/p.md", "actor_id": user.email}]},
        ("PATCH", f"{BASE}/{name}"): {"name": name, "path": "/p.md", "content": "new"},
    })
    out = routes_agent.put_memory(routes_agent.PutMemoryRequest(path="/p.md", content="new"), user=user)
    assert out["memory_id"] == "e1" and out["content"] == "new"
    method, _, query, body = api.calls[-1]
    assert method == "PATCH" and query == {"update_mask": "content"} and body == {"content": "new"}


def test_put_memory_always_uses_caller_as_actor(monkeypatch, user):
    entries = f"{BASE}/memory-stores/lab-jane-doe-memory/entries"
    api = _install(monkeypatch, {("POST", entries): lambda q, b: {"name": "x/entries/e2", **b}})
    routes_agent.put_memory(routes_agent.PutMemoryRequest(path="/a.md", content="c"), user=user)
    assert api.calls[0][3]["actor_id"] == user.email


def test_missing_store_maps_to_actionable_404(monkeypatch, user):
    _install(monkeypatch, {("GET", f"{BASE}/memory-stores/lab-jane-doe-memory/entries"):
                           FakeApiError("RESOURCE_DOES_NOT_EXIST")})
    with pytest.raises(HTTPException) as exc:
        routes_agent.list_memories(user=user)
    assert exc.value.status_code == 404
    assert "Agent_Memory" in exc.value.detail


def test_permission_denied_maps_to_403(monkeypatch, user):
    _install(monkeypatch, {("POST", f"{BASE}/memory-stores/lab-jane-doe-memory/entries:search"):
                           FakeApiError("PERMISSION_DENIED")})
    with pytest.raises(HTTPException) as exc:
        routes_agent.search_memories(routes_agent.SearchRequest(query="q"), user=user)
    assert exc.value.status_code == 403


def test_delete_memory_checks_owner(monkeypatch, user):
    entry = f"{BASE}/memory-stores/lab-jane-doe-memory/entries/e1"
    api = _install(monkeypatch, {("GET", entry): {"actor_id": "someone@else.com"}})
    with pytest.raises(HTTPException) as exc:
        routes_agent.delete_memory("e1", user=user)
    assert exc.value.status_code == 404
    assert not any(c[0] == "DELETE" for c in api.calls)


def test_put_memory_ignores_entries_at_other_paths(monkeypatch, user):
    # A server that ignores the path filter returns every entry; only the exact path may be patched.
    entries = f"{BASE}/memory-stores/lab-jane-doe-memory/entries"
    other = "memory-stores/lab-jane-doe-memory/entries/e0"
    name = "memory-stores/lab-jane-doe-memory/entries/e1"
    pages = {
        None: {"managed_memory_entries": [{"name": other, "path": "/other.md"}], "next_page_token": "t2"},
        "t2": {"managed_memory_entries": [{"name": name, "path": "/p.md"}]},
    }
    api = _install(monkeypatch, {
        ("POST", entries): FakeApiError("ALREADY_EXISTS"),
        ("GET", entries): lambda q, b: pages[q.get("page_token")],
        ("PATCH", f"{BASE}/{name}"): {"name": name, "path": "/p.md", "content": "new"},
    })
    routes_agent.put_memory(routes_agent.PutMemoryRequest(path="/p.md", content="new"), user=user)
    assert api.calls[-1][:2] == ("PATCH", f"{BASE}/{name}")


def test_list_sessions_requests_newest_first(monkeypatch, user):
    api = _install(monkeypatch, {("GET", f"{BASE}/session-stores/lab-jane-doe-sessions/sessions"): {"sessions": []}})
    routes_agent.list_sessions(limit=20, user=user)
    assert api.calls[0][2]["order_by"] == "create_time desc"


def test_list_memories_sorts_before_truncating(monkeypatch, user):
    entries = f"{BASE}/memory-stores/lab-jane-doe-memory/entries"
    pages = {
        None: {"managed_memory_entries": [{"name": "x/z", "path": "/z.md"}], "next_page_token": "t2"},
        "t2": {"managed_memory_entries": [{"name": "x/a", "path": "/a.md"}]},
    }
    _install(monkeypatch, {("GET", entries): lambda q, b: pages[q.get("page_token")]})
    assert [m["path"] for m in routes_agent.list_memories(limit=1, user=user)] == ["/a.md"]


def test_missing_entry_does_not_blame_stores(monkeypatch, user):
    entry = f"{BASE}/memory-stores/lab-jane-doe-memory/entries/e1"
    _install(monkeypatch, {("GET", entry): FakeApiError("RESOURCE_DOES_NOT_EXIST")})
    with pytest.raises(HTTPException) as exc:
        routes_agent.delete_memory("e1", user=user)
    assert exc.value.status_code == 404 and exc.value.detail == "Memory not found"
