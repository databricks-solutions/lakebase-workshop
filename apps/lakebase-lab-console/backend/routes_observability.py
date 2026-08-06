"""Observability routes: PostgreSQL monitoring and diagnostics."""

from fastapi import APIRouter, Depends

from .db import execute_query, get_schema
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/observability", tags=["observability"])

# The catalogue views below also expose Lakebase's own plumbing (__db_system,
# wal2delta), which is neither the participant's data nor safe to size by bare
# name: __db_system.tables would resolve against search_path and error. Every
# query here is scoped to the caller's schema, matching the observability lab.


@router.get("/database")
def database_stats(user: UserContext = Depends(get_current_user)):
    """pg_stat_database metrics for the current database."""
    rows = execute_query(user, """
        SELECT
            datname,
            numbackends AS active_connections,
            xact_commit AS commits,
            xact_rollback AS rollbacks,
            blks_read AS disk_reads,
            blks_hit AS cache_hits,
            tup_returned AS rows_returned,
            tup_fetched AS rows_fetched,
            tup_inserted AS rows_inserted,
            tup_updated AS rows_updated,
            tup_deleted AS rows_deleted,
            conflicts,
            deadlocks,
            temp_files,
            temp_bytes,
            CASE WHEN (blks_hit + blks_read) > 0
                 THEN round(blks_hit::numeric / (blks_hit + blks_read) * 100, 2)
                 ELSE 100 END AS cache_hit_ratio
        FROM pg_stat_database
        WHERE datname = current_database()
    """)
    return rows[0] if rows else {}


@router.get("/tables")
def table_stats(user: UserContext = Depends(get_current_user)):
    """pg_stat_user_tables: sequential/index scans, live/dead tuples, last vacuum/analyze."""
    return execute_query(user, """
        SELECT
            schemaname,
            relname AS table_name,
            seq_scan,
            seq_tup_read,
            idx_scan,
            idx_tup_fetch,
            n_tup_ins AS inserts,
            n_tup_upd AS updates,
            n_tup_del AS deletes,
            n_live_tup AS live_rows,
            n_dead_tup AS dead_rows,
            last_vacuum::text,
            last_autovacuum::text,
            last_analyze::text,
            last_autoanalyze::text
        FROM pg_stat_user_tables
        WHERE schemaname = %s
        ORDER BY n_live_tup DESC
    """, (get_schema(user),))


@router.get("/indexes")
def index_stats(user: UserContext = Depends(get_current_user)):
    """pg_stat_user_indexes: index usage and sizes."""
    return execute_query(user, """
        SELECT
            schemaname,
            relname AS table_name,
            indexrelname AS index_name,
            idx_scan AS scans,
            idx_tup_read AS tuples_read,
            idx_tup_fetch AS tuples_fetched
        FROM pg_stat_user_indexes
        WHERE schemaname = %s
        ORDER BY idx_scan DESC
    """, (get_schema(user),))


@router.get("/sizes")
def table_sizes(user: UserContext = Depends(get_current_user)):
    """Table and index sizes."""
    return execute_query(user, """
        WITH t AS (
            SELECT tablename,
                   quote_ident(schemaname) || '.' || quote_ident(tablename) AS qualified
            FROM pg_tables
            WHERE schemaname = %s
        )
        SELECT
            tablename AS table_name,
            pg_size_pretty(pg_total_relation_size(qualified)) AS total_size,
            pg_size_pretty(pg_relation_size(qualified)) AS table_size,
            pg_size_pretty(pg_indexes_size(qualified)) AS index_size,
            pg_total_relation_size(qualified) AS total_bytes
        FROM t
        ORDER BY pg_total_relation_size(qualified) DESC
    """, (get_schema(user),))


@router.get("/connections")
def connection_info(user: UserContext = Depends(get_current_user)):
    """Active connections and limits."""
    conns = execute_query(user, """
        SELECT
            count(*) AS total_connections,
            count(*) FILTER (WHERE state = 'active') AS active,
            count(*) FILTER (WHERE state = 'idle') AS idle,
            count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_transaction
        FROM pg_stat_activity
        WHERE datname = current_database()
    """)
    max_conn = execute_query(user, "SHOW max_connections")
    result = conns[0] if conns else {}
    result["max_connections"] = int(max_conn[0].get("max_connections", 0)) if max_conn else 0
    return result


@router.get("/activity")
def recent_activity(user: UserContext = Depends(get_current_user)):
    """Current active queries from pg_stat_activity.

    Query text is truncated to avoid surfacing full SQL (which may contain
    literals) from other backends in the shared database.
    """
    return execute_query(user, """
        SELECT
            pid,
            usename AS username,
            state,
            left(query, 200) AS query,
            query_start::text,
            wait_event_type,
            wait_event,
            backend_type
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid != pg_backend_pid()
        ORDER BY query_start DESC NULLS LAST
        LIMIT 25
    """)


@router.get("/statements")
def slow_statements(user: UserContext = Depends(get_current_user)):
    """Top queries by total time from pg_stat_statements (if available).

    This GET is side-effect free: it does not create the extension. Install
    pg_stat_statements via the setup notebook if it is not already available;
    otherwise this returns an empty list.
    """
    try:
        return execute_query(user, """
            SELECT
                queryid,
                left(query, 200) AS query_preview,
                calls,
                round(total_exec_time::numeric, 2) AS total_time_ms,
                round(mean_exec_time::numeric, 2) AS avg_time_ms,
                round(min_exec_time::numeric, 2) AS min_time_ms,
                round(max_exec_time::numeric, 2) AS max_time_ms,
                rows
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
            ORDER BY total_exec_time DESC
            LIMIT 20
        """)
    except Exception:
        return []
