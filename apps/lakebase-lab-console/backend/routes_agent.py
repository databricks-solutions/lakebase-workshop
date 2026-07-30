"""Agent memory lab routes: short-term (session/message) and long-term (memory store) CRUD."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .db import execute_query, execute_write
from .security import clamp_limit
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ── Short-term memory models ─────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    agent_name: str = Field(default="lab-agent", min_length=1)
    metadata: dict = {}


class AppendMessageRequest(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|system|tool)$")
    content: str = Field(..., min_length=1)
    metadata: dict = {}


class SessionInfo(BaseModel):
    session_id: str
    agent_name: str
    metadata: dict
    created_at: str
    message_count: int = 0


# ── Long-term memory models ──────────────────────────────────────────


class UpsertMemoryRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    memory: str = Field(..., min_length=1)
    metadata: dict = {}


class MemoryInfo(BaseModel):
    memory_id: int
    user_id: str
    topic: str
    memory: str
    metadata: dict
    created_at: str
    updated_at: str


@router.get("/sessions", response_model=list[SessionInfo])
def list_sessions(limit: int = 20, user: UserContext = Depends(get_current_user)):
    """List recent agent sessions with message counts."""
    limit = clamp_limit(limit, default=20, maximum=200)
    rows = execute_query(
        user,
        """
        SELECT s.session_id, s.agent_name, s.metadata, s.created_at::text as created_at,
               COALESCE(m.cnt, 0) as message_count
        FROM agent_sessions s
        LEFT JOIN (
            SELECT session_id, count(*) as cnt
            FROM agent_messages
            GROUP BY session_id
        ) m ON s.session_id = m.session_id
        ORDER BY s.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [SessionInfo(**r) for r in rows]


@router.post("/sessions", response_model=SessionInfo)
def create_session(req: CreateSessionRequest, user: UserContext = Depends(get_current_user)):
    """Create a new agent session."""
    session_id = str(uuid.uuid4())[:12]
    import json

    execute_write(
        user,
        "INSERT INTO agent_sessions (session_id, agent_name, metadata) VALUES (%s, %s, %s)",
        (session_id, req.agent_name, json.dumps(req.metadata)),
    )
    return SessionInfo(
        session_id=session_id,
        agent_name=req.agent_name,
        metadata=req.metadata,
        created_at="now",
        message_count=0,
    )


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: UserContext = Depends(get_current_user)):
    """Delete a session and all its messages (cascading)."""
    result = execute_write(
        user,
        "DELETE FROM agent_sessions WHERE session_id = %s", (session_id,)
    )
    if result[0].get("rowcount", 0) == 0:
        raise HTTPException(404, "Session not found")
    return {"status": "deleted", "session_id": session_id}


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str, user: UserContext = Depends(get_current_user)):
    """Get all messages in a session, ordered chronologically."""
    return execute_query(
        user,
        """
        SELECT message_id, session_id, role, content, metadata,
               created_at::text as created_at
        FROM agent_messages
        WHERE session_id = %s
        ORDER BY created_at ASC
        """,
        (session_id,),
    )


@router.post("/sessions/{session_id}/messages")
def append_message(session_id: str, req: AppendMessageRequest, user: UserContext = Depends(get_current_user)):
    """Append a message to a session."""
    import json

    sessions = execute_query(
        user,
        "SELECT 1 FROM agent_sessions WHERE session_id = %s", (session_id,)
    )
    if not sessions:
        raise HTTPException(404, "Session not found")

    result = execute_write(
        user,
        "INSERT INTO agent_messages (session_id, role, content, metadata) "
        "VALUES (%s, %s, %s, %s) RETURNING *",
        (session_id, req.role, req.content, json.dumps(req.metadata)),
    )

    execute_write(
        user,
        "UPDATE agent_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s",
        (session_id,),
    )

    return result


# ── Long-term memory routes ──────────────────────────────────────────


@router.get("/memories", response_model=list[MemoryInfo])
def list_memories(user_id: str | None = None, limit: int = 50, user: UserContext = Depends(get_current_user)):
    """List long-term memories, optionally filtered by user_id."""
    limit = clamp_limit(limit, default=50, maximum=500)
    if user_id:
        rows = execute_query(
            user,
            """
            SELECT memory_id, user_id, topic, memory, metadata,
                   created_at::text as created_at, updated_at::text as updated_at
            FROM agent_memory_store
            WHERE user_id = %s
            ORDER BY topic
            LIMIT %s
            """,
            (user_id, limit),
        )
    else:
        rows = execute_query(
            user,
            """
            SELECT memory_id, user_id, topic, memory, metadata,
                   created_at::text as created_at, updated_at::text as updated_at
            FROM agent_memory_store
            ORDER BY user_id, topic
            LIMIT %s
            """,
            (limit,),
        )
    return [MemoryInfo(**r) for r in rows]


@router.post("/memories", response_model=MemoryInfo)
def upsert_memory(req: UpsertMemoryRequest, user: UserContext = Depends(get_current_user)):
    """Create or update a long-term memory (upsert on user_id + topic)."""
    import json

    rows = execute_write(
        user,
        """
        INSERT INTO agent_memory_store (user_id, topic, memory, metadata)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, topic)
        DO UPDATE SET memory = EXCLUDED.memory,
                      metadata = EXCLUDED.metadata,
                      updated_at = CURRENT_TIMESTAMP
        RETURNING memory_id, user_id, topic, memory, metadata,
                  created_at::text as created_at, updated_at::text as updated_at
        """,
        (req.user_id, req.topic, req.memory, json.dumps(req.metadata)),
    )
    return MemoryInfo(**rows[0])


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: int, user: UserContext = Depends(get_current_user)):
    """Delete a long-term memory by ID."""
    result = execute_write(
        user,
        "DELETE FROM agent_memory_store WHERE memory_id = %s", (memory_id,)
    )
    if result[0].get("rowcount", 0) == 0:
        raise HTTPException(404, "Memory not found")
    return {"status": "deleted", "memory_id": memory_id}


@router.get("/memories/users")
def list_memory_users(user: UserContext = Depends(get_current_user)):
    """List all users who have long-term memories."""
    return execute_query(
        user,
        """
        SELECT user_id, COUNT(*) as memory_count,
               MAX(updated_at)::text as last_updated
        FROM agent_memory_store
        GROUP BY user_id
        ORDER BY last_updated DESC
        """
    )
