# Databricks notebook source
# MAGIC %md
# MAGIC # Lab Setup (shared)
# MAGIC This notebook is `%run` by each lab to provide common utilities.
# MAGIC **Do not run this notebook directly.**

# COMMAND ----------

import os
import re
import time
import psycopg
from psycopg.rows import dict_row
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
user_email = w.current_user.me().user_name

def _sanitize(email):
    name = email.split("@")[0]
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", name.lower())).strip("-")

PROJECT_ID = f"lakebase-lab-{_sanitize(user_email)}"
PG_SCHEMA  = f"lakebase_lab_{_sanitize(user_email).replace('-', '_')}"

_REQUIRED_TABLES = {"products", "events", "agent_sessions", "agent_messages", "agent_memory_store", "audit_log"}

# An endpoint is usable once it leaves INIT. IDLE means it scaled to zero, which is
# the normal resting state for a non-production branch and is not something to wait
# out: an idle endpoint only wakes when a client connects, so waiting for ACTIVE here
# would block until the timeout and then fail a branch that is perfectly healthy.
_READY_ENDPOINT_STATES = ("ACTIVE", "IDLE", "DEGRADED")


def wait_for_endpoint(branch="production", max_attempts=60, delay=5):
    """Poll until the branch's primary endpoint is past provisioning, then return it.

    Newly created branches (dev, snapshot, recovery) need a few seconds to a few
    minutes for their compute to spin up. Poll for readiness instead of guessing
    with a fixed sleep, which can flake on slower endpoint creation."""
    for attempt in range(max_attempts):
        try:
            endpoints = list(w.postgres.list_endpoints(
                parent=f"projects/{PROJECT_ID}/branches/{branch}"
            ))
            if endpoints:
                ep = w.postgres.get_endpoint(name=endpoints[0].name)
                state = str(getattr(ep.status, "current_state", "")).upper()
                if any(ready in state for ready in _READY_ENDPOINT_STATES):
                    return ep
        except Exception:
            pass
        time.sleep(delay)
    raise TimeoutError(
        f"Endpoint for branch '{branch}' is still provisioning after "
        f"{max_attempts * delay // 60} minutes. Check the Lakebase UI."
    )

def get_connection(branch="production", connect_retries=3):
    """Connect to a Lakebase branch. Returns a psycopg connection with dict_row.
    Sets search_path to PG_SCHEMA so table references don't need schema qualifiers.

    Retries the connect a few times: a scale-to-zero branch may take a moment to
    wake on the first connection (non-production branches suspend when idle)."""
    endpoints = list(w.postgres.list_endpoints(
        parent=f"projects/{PROJECT_ID}/branches/{branch}"
    ))
    ep = w.postgres.get_endpoint(name=endpoints[0].name)
    host = ep.status.hosts.host
    cred = w.postgres.generate_database_credential(endpoint=endpoints[0].name)
    # connect_timeout matters as much as the retry: without it a handshake against
    # a waking endpoint can hang instead of raising, which takes the kernel with it.
    params = {"host": host, "dbname": "databricks_postgres",
              "user": user_email, "password": cred.token, "sslmode": "require",
              "connect_timeout": 15,
              "options": f"-c search_path={PG_SCHEMA},public"}
    last_err = None
    for attempt in range(max(1, connect_retries)):
        try:
            conn = psycopg.connect(**params, row_factory=dict_row)
            _ensure_schema(conn, branch)
            return conn
        except psycopg.OperationalError as e:
            last_err = e
            time.sleep(3)  # brief pause for scale-to-zero wake / transient network
    raise last_err

def _find_seed_sql():
    """Locate bootstrap/seed.sql by walking up from this file or the calling notebook."""
    candidates = []
    try:
        nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        ws = f"/Workspace{nb_path}"
        # Calling notebook is labs/<lab>/<Notebook> — walk up 3 levels to project root
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(ws))), "bootstrap", "seed.sql"))
        # _setup.py is labs/_setup — walk up 2 levels
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(ws)), "bootstrap", "seed.sql"))
    except Exception:
        pass
    try:
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bootstrap", "seed.sql"))
    except NameError:
        pass
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None

_REPAIR_SQL = """
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.products (
    product_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    stock_quantity INTEGER DEFAULT 0 CHECK (stock_quantity >= 0),
    category VARCHAR(100),
    tags TEXT[],
    metadata JSONB DEFAULT '{{}}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {schema}.events (
    event_id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    source VARCHAR(100),
    payload JSONB DEFAULT '{{}}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {schema}.agent_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    metadata JSONB DEFAULT '{{}}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {schema}.agent_messages (
    message_id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES {schema}.agent_sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{{}}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {schema}.agent_memory_store (
    memory_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    memory TEXT NOT NULL,
    metadata JSONB DEFAULT '{{}}'::jsonb,
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
CREATE INDEX IF NOT EXISTS idx_audit_record ON {schema}.audit_log(record_id);
"""

def _ensure_schema(conn, branch):
    """Verify required tables exist; create any missing ones."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
            (PG_SCHEMA,),
        )
        existing = {r["table_name"] for r in cur.fetchall()}

    missing = _REQUIRED_TABLES - existing
    if not missing:
        return

    print(f"⚠ Missing tables in {PG_SCHEMA}: {missing}")
    print(f"  Creating missing tables...")

    seed_path = _find_seed_sql()
    if seed_path:
        with open(seed_path) as f:
            sql = f.read().replace("{schema}", PG_SCHEMA)
    else:
        sql = _REPAIR_SQL.format(schema=PG_SCHEMA)

    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"✓ Schema {PG_SCHEMA} repaired — all tables now exist")

def get_endpoint_name(branch="production"):
    """Get the full endpoint resource name for a branch."""
    return f"projects/{PROJECT_ID}/branches/{branch}/endpoints/primary"

WORKSPACE_HOST = w.config.host.rstrip("/") if w.config.host else ""
APP_NAME = "lakebase-lab-console"
APP_URL = f"{WORKSPACE_HOST}/apps/{APP_NAME}" if WORKSPACE_HOST else ""

def show_app_link(page_id, label=None):
    """Render a banner linking to the corresponding Lab Console app page."""
    if not APP_URL:
        return
    url = f"{APP_URL}#{page_id}"
    title = label or page_id.replace("-", " ").title()
    displayHTML(f"""
    <div style="padding:10px 16px;margin:8px 0;border-radius:8px;background:#e8f0fe;border:1px solid #aecbfa;display:flex;align-items:center;gap:12px;font-family:Inter,sans-serif">
      <span style="font-size:20px">🖥️</span>
      <div style="flex:1">
        <strong style="color:#1a73e8">Try it in the Lab Console</strong>
        <span style="color:#3c4043;margin-left:8px">This lab is also available as an interactive UI.</span>
      </div>
      <a href="{url}" target="_blank" style="background:#1a73e8;color:#fff;padding:6px 16px;border-radius:6px;font-size:13px;font-weight:600;text-decoration:none">
        Open {title} →
      </a>
    </div>
    """)

print(f"Project: {PROJECT_ID}")
print(f"Schema:  {PG_SCHEMA}")
print(f"User:    {user_email}")
if APP_URL:
    print(f"Lab App: {APP_URL}")
