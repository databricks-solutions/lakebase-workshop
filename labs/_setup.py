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

    Newly created branches (dev, checkpoint, recovery) need a few seconds to a few
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

    Uses Databricks SDK OAuth (`generate_database_credential`) + sslmode=require —
    the recommended path for notebooks and apps that can mint short-lived tokens.
    For interactive clients (psql/pgAdmin/DBeaver), prefer a native Postgres password
    role from the Lakebase App Connect dialog instead.

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

# ---------------------------------------------------------------------------
# Databricks UI deep links
#
# Labs create durable artifacts (UC tables, Lakebase projects/branches/tables,
# sync pipelines). These helpers build per-user, per-workspace URLs so a
# participant can click straight through to what they just created. Everything
# resolves dynamically from the current identity/workspace — nothing hardcoded.
# ---------------------------------------------------------------------------

# The Lakebase UI addresses projects/branches by their system-generated UID
# (e.g. projects/5fd496e7-… / branches/br-round-tree-…), not the human-readable
# resource id the SDK uses in resource paths. Resolve + cache the UIDs once.
_project_uid_cache = {}
_branch_uid_cache = {}


def _workspace_org_id():
    """Resolve the numeric workspace/org id used by the `?o=` deep-link param.

    Works on all clouds: AWS/GCP hosts (e.g. e2-demo-field-eng.cloud.databricks.com)
    don't embed the id, so we ask the SDK (`get_workspace_id`). Azure hosts embed it
    as `adb-<digits>`, used as a fallback if the API call is unavailable.
    """
    try:
        wid = w.get_workspace_id()
        if wid:
            return str(wid)
    except Exception:
        pass
    if WORKSPACE_HOST:
        m = re.search(r"adb-(\d+)\.", WORKSPACE_HOST)
        if m:
            return m.group(1)
    return None


_ORG_ID = _workspace_org_id()


def _with_org(url):
    """Append the Azure `?o=<org>` param when we can derive it."""
    if _ORG_ID:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}o={_ORG_ID}"
    return url


def uc_table_url(catalog, schema, table):
    """Catalog Explorer deep link for a Unity Catalog table."""
    if not WORKSPACE_HOST:
        return ""
    return _with_org(f"{WORKSPACE_HOST}/explore/data/{catalog}/{schema}/{table}")


def _project_uid(project_id=None):
    """Resolve (and cache) the system UID for a Lakebase project."""
    project_id = project_id or PROJECT_ID
    if project_id in _project_uid_cache:
        return _project_uid_cache[project_id]
    uid = None
    try:
        proj = w.postgres.get_project(name=f"projects/{project_id}")
        uid = getattr(proj, "uid", None)
    except Exception:
        uid = None
    _project_uid_cache[project_id] = uid
    return uid


def _branch_uid(branch="production", project_id=None):
    """Resolve (and cache) the system UID for a Lakebase branch."""
    project_id = project_id or PROJECT_ID
    key = f"{project_id}/{branch}"
    if key in _branch_uid_cache:
        return _branch_uid_cache[key]
    uid = None
    try:
        b = w.postgres.get_branch(name=f"projects/{project_id}/branches/{branch}")
        uid = getattr(b, "uid", None)
    except Exception:
        uid = None
    _branch_uid_cache[key] = uid
    return uid


def lakebase_project_url(branch=None, project_id=None):
    """Lakebase project UI link, optionally focused on a branch.

    Falls back to the human-readable project id if the UID lookup fails."""
    if not WORKSPACE_HOST:
        return ""
    project_id = project_id or PROJECT_ID
    puid = _project_uid(project_id) or project_id
    url = f"{WORKSPACE_HOST}/lakebase/projects/{puid}"
    if branch:
        url = f"{url}?branchId={branch}"
    return url


def lakebase_tables_url(branch="production", project_id=None):
    """Lakebase Tables UI link for a branch.

    Prefers the UID path (/projects/{uid}/branches/{uid}/tables). If a UID can't
    be resolved, falls back to the project URL focused on the branch."""
    if not WORKSPACE_HOST:
        return ""
    project_id = project_id or PROJECT_ID
    puid = _project_uid(project_id)
    buid = _branch_uid(branch, project_id)
    if puid and buid:
        return f"{WORKSPACE_HOST}/lakebase/projects/{puid}/branches/{buid}/tables"
    return lakebase_project_url(branch=branch, project_id=project_id)


def pipeline_url(pipeline_id):
    """Lakeflow/DLT pipeline UI link for a sync or publish pipeline."""
    if not WORKSPACE_HOST or not pipeline_id:
        return ""
    return f"{WORKSPACE_HOST}/pipelines/{pipeline_id}"


def show_view_link(label, url):
    """Render a clickable 'View … →' banner linking to a Databricks UI page.

    Falls back to a plain-text print when displayHTML isn't available (e.g.
    running outside a notebook)."""
    if not url:
        return
    try:
        displayHTML(f"""
    <div style="padding:10px 16px;margin:8px 0;border-radius:8px;background:#e6f4ea;border:1px solid #a8dab5;display:flex;align-items:center;gap:12px;font-family:Inter,sans-serif">
      <div style="flex:1;color:#137333;font-weight:600">{label}</div>
      <a href="{url}" target="_blank" style="background:#137333;color:#fff;padding:6px 16px;border-radius:6px;font-size:13px;font-weight:600;text-decoration:none">
        View →
      </a>
    </div>
    """)
    except Exception:
        print(f"{label}: {url}")

print(f"Project: {PROJECT_ID}")
print(f"Schema:  {PG_SCHEMA}")
print(f"User:    {user_email}")
if APP_URL:
    print(f"Lab App: {APP_URL}")
