"""Data playground routes: CRUD on workshop tables."""

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .db import execute_query, execute_readonly, execute_write, get_schema
from .security import clamp_limit
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/data", tags=["data"])


@router.post("/seed")
def seed_tables(user: UserContext = Depends(get_current_user)):
    """Create workshop tables if they don't exist (idempotent)."""
    seed_file = Path(__file__).parent.parent.parent / "bootstrap" / "seed.sql"
    schema = get_schema(user)

    if seed_file.exists():
        raw = seed_file.read_text()
    else:
        raw = _INLINE_SEED

    sql = raw.replace("{schema}", schema)

    results = []
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if not stmt or stmt.startswith("--"):
            continue
        try:
            execute_write(user, stmt)
            results.append({"sql": stmt[:80], "status": "ok"})
        except Exception as e:
            results.append({"sql": stmt[:80], "status": "error", "error": str(e)})
    return {"seeded": True, "schema": schema, "statements": len(results), "results": results}


_INLINE_SEED = """
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.products (
    product_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    stock_quantity INTEGER DEFAULT 0 CHECK (stock_quantity >= 0),
    category VARCHAR(100),
    tags TEXT[],
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {schema}.events (
    event_id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    source VARCHAR(100),
    payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {schema}.agent_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {schema}.agent_messages (
    message_id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES {schema}.agent_sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {schema}.agent_memory_store (
    memory_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    memory TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, topic)
);

CREATE TABLE IF NOT EXISTS {schema}.audit_log (
    audit_id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    operation VARCHAR(10) NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    record_id INTEGER,
    old_data JSONB,
    new_data JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100) DEFAULT CURRENT_USER
);

CREATE INDEX IF NOT EXISTS idx_events_type ON {schema}.events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON {schema}.events(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_session ON {schema}.agent_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_memory_user ON {schema}.agent_memory_store(user_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON {schema}.products(category);
CREATE INDEX IF NOT EXISTS idx_products_tags ON {schema}.products USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_audit_table ON {schema}.audit_log(table_name);
"""


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    price: float = Field(..., ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    category: str = "General"
    tags: list[str] = []


class ProductUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    stock_quantity: int | None = None
    category: str | None = None


class EventCreate(BaseModel):
    event_type: str = Field(..., min_length=1)
    source: str = "manual"
    payload: dict = {}


# --- Products ---

@router.get("/products")
def list_products(category: str | None = None, limit: int = 50, user: UserContext = Depends(get_current_user)):
    """List products, optionally filtered by category."""
    limit = clamp_limit(limit, default=50, maximum=500)
    if category:
        return execute_query(
            user,
            "SELECT * FROM products WHERE category = %s ORDER BY product_id LIMIT %s",
            (category, limit),
        )
    return execute_query(
        user,
        "SELECT * FROM products ORDER BY product_id LIMIT %s", (limit,)
    )


@router.get("/products/{product_id}")
def get_product(product_id: int, user: UserContext = Depends(get_current_user)):
    """Get a single product."""
    rows = execute_query(
        user,
        "SELECT * FROM products WHERE product_id = %s", (product_id,)
    )
    if not rows:
        raise HTTPException(404, "Product not found")
    return rows[0]


@router.post("/products")
def create_product(req: ProductCreate, user: UserContext = Depends(get_current_user)):
    """Insert a new product."""
    return execute_write(
        user,
        "INSERT INTO products (name, description, price, stock_quantity, category, tags) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
        (req.name, req.description, req.price, req.stock_quantity, req.category, req.tags),
    )


@router.put("/products/{product_id}")
def update_product(product_id: int, req: ProductUpdate, user: UserContext = Depends(get_current_user)):
    """Update an existing product (partial)."""
    sets = []
    values = []
    if req.name is not None:
        sets.append("name = %s")
        values.append(req.name)
    if req.price is not None:
        sets.append("price = %s")
        values.append(req.price)
    if req.stock_quantity is not None:
        sets.append("stock_quantity = %s")
        values.append(req.stock_quantity)
    if req.category is not None:
        sets.append("category = %s")
        values.append(req.category)

    if not sets:
        raise HTTPException(400, "No fields to update")

    sets.append("updated_at = CURRENT_TIMESTAMP")
    values.append(product_id)

    return execute_write(
        user,
        f"UPDATE products SET {', '.join(sets)} WHERE product_id = %s RETURNING *",
        tuple(values),
    )


@router.delete("/products/{product_id}")
def delete_product(product_id: int, user: UserContext = Depends(get_current_user)):
    """Delete a product."""
    result = execute_write(
        user,
        "DELETE FROM products WHERE product_id = %s", (product_id,)
    )
    if result[0].get("rowcount", 0) == 0:
        raise HTTPException(404, "Product not found")
    return {"status": "deleted", "product_id": product_id}


# --- Events ---

@router.get("/events")
def list_events(event_type: str | None = None, limit: int = 100, user: UserContext = Depends(get_current_user)):
    """List recent events."""
    limit = clamp_limit(limit, default=100, maximum=1000)
    if event_type:
        return execute_query(
            user,
            "SELECT * FROM events WHERE event_type = %s ORDER BY created_at DESC LIMIT %s",
            (event_type, limit),
        )
    return execute_query(
        user,
        "SELECT * FROM events ORDER BY created_at DESC LIMIT %s", (limit,)
    )


@router.post("/events")
def create_event(req: EventCreate, user: UserContext = Depends(get_current_user)):
    """Insert a new event."""
    return execute_write(
        user,
        "INSERT INTO events (event_type, source, payload) VALUES (%s, %s, %s) RETURNING *",
        (req.event_type, req.source, json.dumps(req.payload)),
    )


@router.delete("/events/loadtest")
def clear_loadtest_events(user: UserContext = Depends(get_current_user)):
    """Delete all events from load tests."""
    return execute_write(user, "DELETE FROM events WHERE event_type = 'loadtest'")


# --- Audit Log ---

@router.get("/audit")
def list_audit_log(table_name: str | None = None, limit: int = 50, user: UserContext = Depends(get_current_user)):
    """View the audit log."""
    limit = clamp_limit(limit, default=50, maximum=500)
    if table_name:
        return execute_query(
            user,
            "SELECT * FROM audit_log WHERE table_name = %s ORDER BY created_at DESC LIMIT %s",
            (table_name, limit),
        )
    return execute_query(
        user,
        "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT %s", (limit,)
    )


# --- Table stats ---

@router.get("/stats")
def table_stats(user: UserContext = Depends(get_current_user)):
    """Get row counts for all workshop tables."""
    tables = ["products", "events", "agent_sessions", "agent_messages", "audit_log"]
    stats = {}
    for t in tables:
        try:
            rows = execute_query(user, f"SELECT count(*) as cnt FROM {t}")
            stats[t] = rows[0]["cnt"]
        except Exception:
            stats[t] = -1
    return stats


class QueryRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=5000)


# Primary control is a READ ONLY transaction at the database layer (see
# execute_readonly); these are defense-in-depth so obvious writes/DDL are
# rejected before touching the database with a clear message.
_ALLOWED_START = re.compile(r"^\s*(SELECT|WITH|TABLE|VALUES|EXPLAIN|SHOW)\b", re.IGNORECASE)
_MAX_QUERY_ROWS = 1000


@router.post("/query")
def run_query(req: QueryRequest, user: UserContext = Depends(get_current_user)):
    """Run a read-only SQL query for the SQL playground.

    Enforced read-only: the statement must be a single read statement AND it runs
    inside a READ ONLY database transaction, so writes are impossible even if the
    text check is bypassed. Results are capped for memory/response safety.
    """
    sql = req.sql.strip().rstrip(";").strip()
    if not sql:
        raise HTTPException(400, "Empty query")
    # Reject multiple statements (a semicolon anywhere in the middle).
    if ";" in sql:
        raise HTTPException(400, "Only a single statement is allowed in the query playground")
    if not _ALLOWED_START.match(sql):
        raise HTTPException(
            400,
            "Only read-only statements (SELECT/WITH/TABLE/VALUES/EXPLAIN/SHOW) are "
            "allowed in the query playground",
        )
    try:
        return execute_readonly(user, sql, max_rows=_MAX_QUERY_ROWS)
    except HTTPException:
        raise
    except Exception:
        # Do not leak raw driver text (may include SQL, roles, or host details).
        raise HTTPException(400, "Query failed. Check your SQL syntax and that the table exists.")
