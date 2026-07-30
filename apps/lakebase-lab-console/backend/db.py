"""Lakebase connection manager with per-user routing via the app's Service Principal.

The shared Lab Console app uses the app's Service Principal (SP) for all
Lakebase SDK calls and database connections. The logged-in user's email
(from Databricks Apps forwarded headers) determines which project and schema
to connect to — but the SP's credentials are used for the actual connection.

Each user must grant the SP access to their project via the setup notebook.

DB credentials are cached per project for 45 minutes (tokens expire at 60 min).
"""

import logging
import os
import time
import threading
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .security import assert_valid_schema
from .user_context import UserContext

logger = logging.getLogger(__name__)

_TOKEN_REFRESH_INTERVAL = 2700  # 45 minutes

# Cap the number of concurrently cached pools so a large workshop cannot grow
# process memory unbounded; least-recently-created pools are evicted/closed.
_MAX_POOLS = 50

# Credential cache keyed by project_id:branch_id
_db_tokens: dict[str, tuple[str, float]] = {}
_db_tokens_lock = threading.Lock()

_connection_pools: dict[str, ConnectionPool] = {}
# When each pool was built (its embedded DB credential's mint time), so we can
# rebuild the pool before the OAuth database credential expires.
_pool_created_at: dict[str, float] = {}
_pool_lock = threading.Lock()

_host_cache: dict[str, str] = {}

# Singleton SP WorkspaceClient
_sp_client = None
_sp_client_lock = threading.Lock()


def _get_workspace_client():
    """Get or create the app's SP WorkspaceClient (singleton).

    Uses default SDK auth which reads DATABRICKS_HOST, DATABRICKS_CLIENT_ID,
    and DATABRICKS_CLIENT_SECRET from the environment — set automatically by
    the Databricks Apps runtime.
    """
    global _sp_client
    if _sp_client is not None:
        return _sp_client

    with _sp_client_lock:
        if _sp_client is not None:
            return _sp_client

        from databricks.sdk import WorkspaceClient
        _sp_client = WorkspaceClient()
        return _sp_client


def _get_sp_username() -> str:
    """Get the PG username for the SP.

    When connecting to Lakebase as an SP, the username is the SP's client_id.
    This is set by PGUSER (from postgres resource attachment) or DATABRICKS_CLIENT_ID.
    """
    return os.getenv("PGUSER") or os.getenv("DATABRICKS_CLIENT_ID", "")


def get_project_id(user: UserContext) -> str:
    return user.project_id


def get_schema(user: UserContext) -> str:
    return user.schema


def _get_db_credential(user: UserContext, branch_id: str | None = None) -> tuple[str, str, str]:
    """Generate or return cached (host, sp_username, db_token) for a user's project.

    Uses the SP's WorkspaceClient to discover the endpoint and generate
    a database credential. The SP connects as itself (DATABRICKS_CLIENT_ID),
    not as the user.
    """
    if not branch_id:
        branch_id = user.branch_id

    cache_key = f"{user.project_id}:{branch_id}"
    sp_username = _get_sp_username()

    with _db_tokens_lock:
        cached = _db_tokens.get(cache_key)
        if cached:
            token, ts = cached
            if (time.time() - ts) < _TOKEN_REFRESH_INTERVAL:
                host = _host_cache.get(cache_key, os.getenv("PGHOST", ""))
                if host:
                    return host, sp_username, token

    w = _get_workspace_client()
    project_id = user.project_id

    endpoints = list(
        w.postgres.list_endpoints(
            parent=f"projects/{project_id}/branches/{branch_id}"
        )
    )
    if not endpoints:
        raise RuntimeError(
            f"No endpoints found for project '{project_id}' branch '{branch_id}'. "
            f"Have you run the setup notebook (00_Setup_Lakebase_Project)?"
        )

    ep = w.postgres.get_endpoint(name=endpoints[0].name)
    host = ep.status.hosts.host
    cred = w.postgres.generate_database_credential(endpoint=endpoints[0].name)

    with _db_tokens_lock:
        _db_tokens[cache_key] = (cred.token, time.time())

    _host_cache[cache_key] = host

    return host, sp_username, cred.token


def _discover_host(user: UserContext, branch_id: str) -> str:
    """Look up the cached or discovered endpoint host."""
    cache_key = f"{user.project_id}:{branch_id}"
    cached = _host_cache.get(cache_key)
    if cached:
        return cached

    w = _get_workspace_client()
    endpoints = list(
        w.postgres.list_endpoints(
            parent=f"projects/{user.project_id}/branches/{branch_id}"
        )
    )
    if endpoints:
        ep = w.postgres.get_endpoint(name=endpoints[0].name)
        host = ep.status.hosts.host
        _host_cache[cache_key] = host
        return host

    raise RuntimeError(f"No endpoints for {user.project_id}/{branch_id}")


def _get_connection_params(user: UserContext, branch_id: str | None = None) -> dict:
    """Build psycopg connection parameters for a user's project."""
    if not branch_id:
        branch_id = user.branch_id

    schema = assert_valid_schema(user.schema)
    search_path_opt = f"-c search_path={schema},public"

    # Local dev with PGHOST/PGUSER: use env vars directly
    pghost = os.getenv("PGHOST") if user._is_local else None
    pguser = os.getenv("PGUSER") if user._is_local else None

    if pghost and pguser:
        w = _get_workspace_client()
        try:
            project_id = user.project_id or os.getenv("LAKEBASE_PROJECT_ID", "")
            endpoints = list(
                w.postgres.list_endpoints(
                    parent=f"projects/{project_id}/branches/{branch_id}"
                )
            )
            if endpoints:
                cred = w.postgres.generate_database_credential(endpoint=endpoints[0].name)
                token = cred.token
            else:
                token = w.config.oauth_token().access_token
        except Exception:
            token = w.config.oauth_token().access_token
        return {
            "host": pghost,
            "dbname": os.getenv("PGDATABASE", "databricks_postgres"),
            "user": pguser,
            "password": token,
            "sslmode": "require",
            "options": search_path_opt,
        }

    host, username, token = _get_db_credential(user, branch_id)
    return {
        "host": host,
        "dbname": "databricks_postgres",
        "user": username,
        "password": token,
        "sslmode": "require",
        "options": search_path_opt,
    }


def _build_conninfo(user: UserContext, branch_id: str | None = None) -> str:
    """Build a libpq connection string for pool creation.

    The returned string embeds a short-lived OAuth database credential as the
    password; never log it.
    """
    params = _get_connection_params(user, branch_id)
    schema = assert_valid_schema(user.schema)
    return (
        f"host={params['host']} dbname={params['dbname']} user={params['user']} "
        f"password={params['password']} sslmode=require "
        f"options=-c\\ search_path={schema},public"
    )


def _close_pool_locked(key: str) -> None:
    """Close and forget a pool. Caller must hold _pool_lock."""
    pool = _connection_pools.pop(key, None)
    _pool_created_at.pop(key, None)
    if pool is not None:
        try:
            pool.close()
        except Exception:
            pass


def _pool_is_fresh(key: str) -> bool:
    created = _pool_created_at.get(key)
    if created is None:
        return False
    # Rebuild before the OAuth database credential (60 min) expires.
    return (time.time() - created) < _TOKEN_REFRESH_INTERVAL


def get_pool(
    user: UserContext,
    branch_id: str | None = None,
    min_size: int = 4,
    max_size: int = 20,
) -> ConnectionPool:
    """Get or create a connection pool for the given user's project and branch.

    Pools embed a short-lived OAuth database credential, so a stale pool (older
    than the refresh interval) is closed and rebuilt to pick up a fresh
    credential instead of failing once the original token expires.
    """
    if not branch_id:
        branch_id = user.branch_id
    key = f"{user.project_id}:{branch_id}"

    pool = _connection_pools.get(key)
    if pool is not None and not pool.closed and _pool_is_fresh(key):
        return pool

    with _pool_lock:
        existing = _connection_pools.get(key)
        if existing is not None and not existing.closed and _pool_is_fresh(key):
            return existing

        # Stale, closed, or credential rotated: rebuild.
        _close_pool_locked(key)

        # Bound total pools: evict the oldest if at capacity.
        if len(_connection_pools) >= _MAX_POOLS:
            oldest = min(_pool_created_at, key=_pool_created_at.get, default=None)
            if oldest is not None:
                _close_pool_locked(oldest)

        conninfo = _build_conninfo(user, branch_id)
        pool = ConnectionPool(
            conninfo=conninfo,
            min_size=min_size,
            max_size=max_size,
            timeout=10,
            max_lifetime=600,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        _connection_pools[key] = pool
        _pool_created_at[key] = time.time()
        return pool


def close_all_pools():
    """Close all connection pools (call on shutdown)."""
    for pool in _connection_pools.values():
        try:
            pool.close()
        except Exception:
            pass
    _connection_pools.clear()
    _pool_created_at.clear()


@contextmanager
def get_connection(user: UserContext, branch_id: str | None = None):
    """Context manager that yields a psycopg connection with dict_row."""
    params = _get_connection_params(user, branch_id)
    conn = psycopg.connect(**params, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_pooled_connection(user: UserContext, branch_id: str | None = None):
    """Context manager that yields a connection from the pool."""
    pool = get_pool(user, branch_id)
    with pool.connection() as conn:
        conn.row_factory = dict_row
        yield conn


def execute_query(
    user: UserContext,
    sql: str,
    params: tuple | None = None,
    branch_id: str | None = None,
) -> list[dict]:
    """Execute a query and return results as list of dicts."""
    with get_connection(user, branch_id) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                return cur.fetchall()
            conn.commit()
            return [{"rowcount": cur.rowcount}]


def execute_readonly(
    user: UserContext,
    sql: str,
    params: tuple | None = None,
    branch_id: str | None = None,
    max_rows: int = 1000,
    statement_timeout_ms: int = 15000,
) -> list[dict]:
    """Execute SQL inside a READ ONLY transaction and never commit.

    Used by the SQL playground so that even if a statement attempts a write, the
    database rejects it (read-only transaction). A statement timeout bounds
    runaway queries and the result set is capped at ``max_rows`` to bound memory
    and response size. The transaction is always rolled back.
    """
    with get_connection(user, branch_id) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                # SET does not accept bind parameters; inline a validated integer.
                cur.execute(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
                cur.execute(sql, params)
                rows = cur.fetchmany(max_rows) if cur.description else []
            return rows
        finally:
            conn.rollback()


def execute_write(
    user: UserContext,
    sql: str,
    params: tuple | None = None,
    branch_id: str | None = None,
) -> list[dict]:
    """Execute a write query (INSERT/UPDATE/DELETE), commit, return results."""
    with get_connection(user, branch_id) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                result = cur.fetchall()
                conn.commit()
                return result
            conn.commit()
            return [{"rowcount": cur.rowcount}]


def get_db_metrics(user: UserContext, branch_id: str | None = None) -> dict:
    """Fetch real-time DB-level metrics from pg_stat views."""
    try:
        with get_pooled_connection(user, branch_id) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        numbackends AS active_connections,
                        xact_commit + xact_rollback AS total_transactions,
                        xact_commit AS commits,
                        tup_returned AS rows_read,
                        tup_inserted AS rows_inserted,
                        tup_updated AS rows_updated,
                        tup_deleted AS rows_deleted,
                        blks_hit AS cache_hits,
                        blks_read AS disk_reads
                    FROM pg_stat_database
                    WHERE datname = current_database()
                """)
                row = cur.fetchone()
                if row:
                    hits = row.get("cache_hits", 0) or 0
                    reads = row.get("disk_reads", 0) or 0
                    total = hits + reads
                    row["cache_hit_ratio"] = round(hits / total * 100, 1) if total > 0 else 100.0
                return row or {}
    except Exception:
        return {}
