"""Agent memory lab routes: managed agent sessions (short-term) and agent memory (long-term).

Calls the Agent Bricks REST API (/api/2.0/agents) with the app's Service Principal.
Each participant's stores are created by labs/agentic-memory/Agent_Memory.py, which
also grants this app's SP WRITE on them. The participant's email is the actor_id,
so a user only sees their own sessions and memories.
"""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .db import _get_workspace_client
from .security import clamp_limit
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/agent", tags=["agent"])

_API = "/api/2.0/agents"
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MEMORY_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_LAB = "labs/agentic-memory/Agent_Memory"


def _call(user: UserContext, method: str, path: str, *, query=None, body=None, not_found: str | None = None) -> dict:
    """Call the agents API, mapping common failures to clear, actionable messages.

    ``not_found`` overrides the 404 message for calls on a single session or entry, where a
    missing resource doesn't mean the stores are missing.
    """
    try:
        return _get_workspace_client().api_client.do(method, f"{_API}{path}", query=query, body=body) or {}
    except Exception as e:
        code = getattr(e, "error_code", "") or ""
        msg = str(e)
        lowered = msg.lower()
        if code in ("RESOURCE_DOES_NOT_EXIST", "NOT_FOUND") or (not code and "does not exist" in lowered):
            raise HTTPException(
                404,
                not_found or f"Not found. Run {_LAB} to create your stores "
                f"({user.session_store_id}, {user.memory_store_id}).",
            )
        if code == "PERMISSION_DENIED" or (not code and "permission denied" in lowered):
            raise HTTPException(
                403,
                f"The app's Service Principal has no access to your stores. Re-run Part 4 "
                f"(grant the Lab Console app) in {_LAB}.",
            )
        if code == "ALREADY_EXISTS":
            raise HTTPException(409, msg[:300])
        if code in ("INVALID_PARAMETER_VALUE", "BAD_REQUEST"):
            raise HTTPException(400, msg[:300])
        raise HTTPException(502, f"Agent memory API error: {msg[:300]}")


def _sessions_path(user: UserContext) -> str:
    return f"/session-stores/{user.session_store_id}/sessions"


def _check_session_id(session_id: str) -> str:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, "Invalid session id")
    return session_id


def _owned_session(user: UserContext, session_id: str) -> dict:
    """Fetch a session and confirm it belongs to the caller (actor_id is not access control)."""
    s = _call(user, "GET", f"{_sessions_path(user)}/{_check_session_id(session_id)}",
              not_found="Session not found")
    if s.get("actor_id") != user.email:
        raise HTTPException(404, "Session not found")
    return s


# ── Models ───────────────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    agent_name: str = Field(default="lab-agent", min_length=1, max_length=100)


class AppendMessageRequest(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|system|tool)$")
    content: str = Field(..., min_length=1, max_length=20000)


class PutMemoryRequest(BaseModel):
    path: str = Field(..., pattern=r"^/[A-Za-z0-9._/-]{1,255}$")
    content: str = Field(..., min_length=1, max_length=20000)
    description: str | None = Field(default=None, max_length=500)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = 5


def _session_info(s: dict, message_count: int | None = None) -> dict:
    meta = s.get("metadata") or {}
    return {
        "session_id": s.get("session_id"),
        "agent_name": meta.get("agent", meta.get("agent_name", "")),
        "metadata": meta,
        "created_at": s.get("create_time", ""),
        "last_activity": s.get("last_activity_time", ""),
        "message_count": message_count,
    }


def _memory_info(m: dict) -> dict:
    return {
        "memory_id": (m.get("name") or "").rsplit("/", 1)[-1],
        "path": m.get("path"),
        "content": m.get("content"),
        "description": m.get("description"),
        "session_id": m.get("session_id"),
        "source_type": m.get("source_type"),
        "created_at": m.get("create_time", ""),
        "updated_at": m.get("update_time", ""),
    }


# ── Store info ───────────────────────────────────────────────────────


@router.get("/stores")
def store_info(user: UserContext = Depends(get_current_user)):
    """Names of the caller's stores and the actor_id the app uses."""
    return {
        "actor_id": user.email,
        "session_store": user.session_store_id,
        "memory_store": user.memory_store_id,
    }


# ── Sessions (short-term) ────────────────────────────────────────────


@router.get("/sessions")
def list_sessions(limit: int = 20, user: UserContext = Depends(get_current_user)):
    """List the caller's sessions, most recent first."""
    limit = clamp_limit(limit, default=20, maximum=100)
    out, token = [], None
    while len(out) < limit:
        query = {"page_size": 100, "order_by": "create_time desc"}
        if token:
            query["page_token"] = token
        resp = _call(user, "GET", _sessions_path(user), query=query)
        out.extend(s for s in resp.get("sessions", []) if s.get("actor_id") == user.email)
        token = resp.get("next_page_token")
        if not token:
            break
    out.sort(key=lambda s: s.get("last_activity_time") or s.get("create_time") or "", reverse=True)
    return [_session_info(s) for s in out[:limit]]


@router.post("/sessions")
def create_session(req: CreateSessionRequest, user: UserContext = Depends(get_current_user)):
    """Create a session owned by the caller (the service generates the session id)."""
    s = _call(user, "POST", _sessions_path(user),
              body={"actor_id": user.email, "metadata": {"agent": req.agent_name, "source": "lab-console"}})
    return _session_info(s, message_count=0)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: UserContext = Depends(get_current_user)):
    """Delete a session and its items (and any child sessions)."""
    _owned_session(user, session_id)
    _call(user, "DELETE", f"{_sessions_path(user)}/{session_id}", query={"force": True},
          not_found="Session not found")
    return {"status": "deleted", "session_id": session_id}


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str, user: UserContext = Depends(get_current_user)):
    """Replay a session's items in chronological order."""
    _owned_session(user, session_id)
    items, token = [], None
    while True:
        query = {"order_by": "create_time asc", "page_size": 100}
        if token:
            query["page_token"] = token
        resp = _call(user, "GET", f"{_sessions_path(user)}/{session_id}/items", query=query)
        items.extend(resp.get("session_items", []))
        token = resp.get("next_page_token")
        if not token or len(items) >= 1000:
            break
    out = []
    for it in items:
        data = it.get("data")
        if isinstance(data, dict):
            role, content = data.get("role", data.get("type", "item")), data.get("content", data)
        else:
            role, content = "item", data
        out.append({
            "item_id": it.get("item_id"),
            "role": role,
            "content": content if isinstance(content, str) else str(content),
            "created_at": it.get("create_time", ""),
        })
    return out


@router.post("/sessions/{session_id}/messages")
def append_message(session_id: str, req: AppendMessageRequest, user: UserContext = Depends(get_current_user)):
    """Append one message item to the caller's session."""
    _owned_session(user, session_id)
    resp = _call(user, "POST", f"{_sessions_path(user)}/{session_id}/items:append",
                 body={"items": [{"data": {"type": "message", "role": req.role, "content": req.content}}]})
    return resp.get("session_items", [])


# ── Memory (long-term) ───────────────────────────────────────────────


def _entries_path(user: UserContext) -> str:
    return f"/memory-stores/{user.memory_store_id}/entries"


@router.get("/memories")
def list_memories(path_prefix: str | None = None, limit: int = 100, user: UserContext = Depends(get_current_user)):
    """List the caller's memory entries, optionally under a path prefix, sorted by path."""
    limit = clamp_limit(limit, default=100, maximum=500)
    # Fetch up to the hard cap before sorting so the first `limit` paths are returned,
    # not whichever entries the server happened to page first.
    out, token = [], None
    while len(out) < 500:
        query = {"actor_id": user.email, "page_size": 100}
        if path_prefix:
            query["path_prefix"] = path_prefix
        if token:
            query["page_token"] = token
        resp = _call(user, "GET", _entries_path(user), query=query)
        out.extend(resp.get("managed_memory_entries", []))
        token = resp.get("next_page_token")
        if not token:
            break
    return sorted((_memory_info(m) for m in out), key=lambda m: m["path"] or "")[:limit]


def _find_entry(user: UserContext, path: str) -> dict | None:
    """Find the caller's unscoped entry at exactly `path`, across all pages.

    Rechecks the path because some servers ignore the `path` filter and return every entry.
    """
    token = None
    while True:
        query = {"actor_id": user.email, "path": path, "page_size": 100}
        if token:
            query["page_token"] = token
        resp = _call(user, "GET", _entries_path(user), query=query)
        for m in resp.get("managed_memory_entries", []):
            if m.get("path") == path and not m.get("session_id"):
                return m
        token = resp.get("next_page_token")
        if not token:
            return None


@router.post("/memories")
def put_memory(req: PutMemoryRequest, user: UserContext = Depends(get_current_user)):
    """Create the entry at the path, or replace its content if one exists (put semantics)."""
    if ".." in req.path:
        raise HTTPException(400, "Invalid path")
    body = {"actor_id": user.email, "path": req.path, "content": req.content}
    if req.description:
        body["description"] = req.description
    try:
        return _memory_info(_call(user, "POST", _entries_path(user), body=body))
    except HTTPException as e:
        if e.status_code != 409:
            raise
    match = _find_entry(user, req.path)
    if match is None:
        raise HTTPException(409, "Memory changed concurrently; retry")
    patch = {"content": req.content}
    if req.description:
        patch["description"] = req.description
    updated = _call(user, "PATCH", "/" + match["name"].lstrip("/"), query={"update_mask": ",".join(patch)},
                    body=patch, not_found="Memory changed concurrently; retry")
    return _memory_info(updated)


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str, user: UserContext = Depends(get_current_user)):
    """Delete one of the caller's memory entries."""
    if not _MEMORY_ID_RE.match(memory_id):
        raise HTTPException(400, "Invalid memory id")
    entry = _call(user, "GET", f"{_entries_path(user)}/{memory_id}", not_found="Memory not found")
    if entry.get("actor_id") != user.email:
        raise HTTPException(404, "Memory not found")
    _call(user, "DELETE", f"{_entries_path(user)}/{memory_id}", not_found="Memory not found")
    return {"status": "deleted", "memory_id": memory_id}


@router.post("/memories/search")
def search_memories(req: SearchRequest, user: UserContext = Depends(get_current_user)):
    """Natural-language recall over the caller's memories, ranked by relevance."""
    limit = clamp_limit(req.limit, default=5, maximum=100)
    resp = _call(user, "POST", f"{_entries_path(user)}:search",
                 body={"actor_id": user.email, "query": req.query, "limit": limit})
    hits = resp.get("results")
    if hits is not None:
        return [{**_memory_info(h.get("managed_memory_entry") or {}), "score": h.get("score")} for h in hits]
    return [{**_memory_info(m), "score": None} for m in resp.get("managed_memory_entries", [])]
