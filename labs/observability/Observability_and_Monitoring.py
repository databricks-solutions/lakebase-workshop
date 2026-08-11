# Databricks notebook source
# MAGIC %md
# MAGIC # Observability & Monitoring
# MAGIC
# MAGIC **Path:** Observability &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase features:** pg_stat views, index analysis, connection monitoring, workspace UI
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. Query `pg_stat_user_tables` for table-level activity
# MAGIC 2. Analyze index usage and identify unused indexes
# MAGIC 3. Monitor active connections and session state
# MAGIC 4. Check cache hit ratios and I/O performance
# MAGIC 5. Identify slow query patterns
# MAGIC 6. Learn where to find the Lakebase monitoring dashboard in the workspace
# MAGIC 7. Explore platform monitoring: metrics dashboard, OpenTelemetry export, Genie, and Insights
# MAGIC
# MAGIC **Run `00_Setup_Lakebase_Project` first.** Running `labs/data-operations/Data_Operations` first
# MAGIC for more interesting metrics. Catalog queries below filter on **your** PostgreSQL schema (`PG_SCHEMA` from `_setup`), not a fixed name.
# MAGIC
# MAGIC **Docs:** [Observability](https://docs.databricks.com/aws/en/oltp/projects/monitor) |
# MAGIC [pg_stat_statements](https://docs.databricks.com/aws/en/oltp/projects/pg-stat-statements) |
# MAGIC [OpenTelemetry export](https://docs.databricks.com/aws/en/oltp/projects/opentelemetry) |
# MAGIC [AI-assisted troubleshooting](https://docs.databricks.com/aws/en/oltp/projects/ai-assisted-troubleshooting)

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

conn = get_connection()
print(f"✓ Connected to {PROJECT_ID} / production")
show_app_link("observability", "Observability")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Database-Level Overview
# MAGIC
# MAGIC `pg_stat_database` gives a high-level snapshot of activity:
# MAGIC commits, rollbacks, block reads, cache hits.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT
            datname AS database,
            numbackends AS active_connections,
            xact_commit AS total_commits,
            xact_rollback AS total_rollbacks,
            blks_read AS disk_reads,
            blks_hit AS cache_hits,
            CASE WHEN blks_hit + blks_read > 0
                THEN ROUND(100.0 * blks_hit / (blks_hit + blks_read), 2)
                ELSE 0
            END AS cache_hit_pct,
            tup_returned AS rows_returned,
            tup_fetched AS rows_fetched,
            tup_inserted AS rows_inserted,
            tup_updated AS rows_updated,
            tup_deleted AS rows_deleted,
            temp_files,
            pg_size_pretty(temp_bytes) AS temp_bytes
        FROM pg_stat_database
        WHERE datname = current_database()
    """)
    row = cur.fetchone()
    print("Database Overview")
    print("=" * 50)
    for k, v in row.items():
        print(f"  {k:<22} {v}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Key Metrics to Watch
# MAGIC
# MAGIC | Metric | Healthy | Warning |
# MAGIC |--------|---------|---------|
# MAGIC | **Cache hit %** | > 99% | < 95% — data doesn't fit in RAM |
# MAGIC | **Rollbacks** | Near 0 | High ratio vs commits = app errors |
# MAGIC | **Temp files** | 0 | > 0 — queries spilling to disk, need more RAM or query tuning |

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Table-Level Activity
# MAGIC
# MAGIC `pg_stat_user_tables` shows per-table read/write activity, sequential
# MAGIC vs. index scans, and dead tuple counts.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute(f"""
        SELECT
            schemaname || '.' || relname AS table_name,
            seq_scan,
            seq_tup_read,
            idx_scan,
            idx_tup_fetch,
            n_tup_ins AS inserts,
            n_tup_upd AS updates,
            n_tup_del AS deletes,
            n_live_tup AS live_rows,
            n_dead_tup AS dead_rows,
            last_vacuum,
            last_analyze
        FROM pg_stat_user_tables
        WHERE schemaname = '{PG_SCHEMA}'
        ORDER BY COALESCE(seq_scan, 0) + COALESCE(idx_scan, 0) DESC
    """)
    rows = cur.fetchall()
    for r in rows:
        print(f"\n{r['table_name']}:")
        print(f"  Seq scans: {r['seq_scan']}  (rows read: {r['seq_tup_read']})")
        print(f"  Idx scans: {r['idx_scan']}  (rows fetched: {r['idx_tup_fetch']})")
        print(f"  Inserts: {r['inserts']}  Updates: {r['updates']}  Deletes: {r['deletes']}")
        print(f"  Live rows: {r['live_rows']}  Dead rows: {r['dead_rows']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Sequential Scans vs. Index Scans
# MAGIC
# MAGIC - **High seq_scan + high seq_tup_read** on a large table = missing index
# MAGIC - **idx_scan = 0** for an index = the index is unused (candidate for removal)
# MAGIC - **dead_rows >> live_rows** = table needs VACUUM

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Index Usage Analysis
# MAGIC
# MAGIC Find which indexes are being used and which are wasting space.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute(f"""
        SELECT
            schemaname || '.' || relname AS table_name,
            indexrelname AS index_name,
            idx_scan AS times_used,
            idx_tup_read AS rows_read,
            idx_tup_fetch AS rows_fetched,
            pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
        FROM pg_stat_user_indexes
        WHERE schemaname = '{PG_SCHEMA}'
        ORDER BY idx_scan DESC
    """)
    rows = cur.fetchall()
    print(f"{'Index':<40} {'Table':<25} {'Scans':>8} {'Size':>10}")
    print("-" * 85)
    for r in rows:
        flag = " ⚠ UNUSED" if r['times_used'] == 0 else ""
        print(f"{r['index_name']:<40} {r['table_name']:<25} {r['times_used']:>8} {r['index_size']:>10}{flag}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Table Sizes
# MAGIC
# MAGIC Total size includes the table data + all indexes + TOAST.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute(f"""
        SELECT
            schemaname || '.' || tablename AS table_name,
            pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size,
            pg_size_pretty(pg_relation_size(schemaname || '.' || tablename)) AS data_size,
            pg_size_pretty(
                pg_total_relation_size(schemaname || '.' || tablename)
                - pg_relation_size(schemaname || '.' || tablename)
            ) AS index_toast_size
        FROM pg_tables
        WHERE schemaname = '{PG_SCHEMA}'
        ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
    """)
    rows = cur.fetchall()
    print(f"{'Table':<30} {'Total':>10} {'Data':>10} {'Idx+TOAST':>10}")
    print("-" * 65)
    for r in rows:
        print(f"{r['table_name']:<30} {r['total_size']:>10} {r['data_size']:>10} {r['index_toast_size']:>10}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Active Connections & Session State

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT
            pid,
            usename AS user,
            state,
            COALESCE(wait_event_type, '-') AS wait_type,
            COALESCE(wait_event, '-') AS wait_event,
            query_start,
            LEFT(query, 80) AS query_preview
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid != pg_backend_pid()
        ORDER BY query_start DESC NULLS LAST
    """)
    rows = cur.fetchall()
    if rows:
        print(f"{'PID':<8} {'User':<30} {'State':<12} {'Wait':<20} {'Query'}")
        print("-" * 100)
        for r in rows:
            print(f"{r['pid']:<8} {(r['user'] or '-'):<30} {(r['state'] or '-'):<12} "
                  f"{r['wait_type'] + '/' + r['wait_event']:<20} {(r['query_preview'] or '-')}")
    else:
        print("No other active sessions (only this notebook is connected)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Connection Limits
# MAGIC
# MAGIC Max connections available for direct use scale with CU size:
# MAGIC
# MAGIC | CU | Max Connections |
# MAGIC |----|----------------|
# MAGIC | 0.5 | 105 |
# MAGIC | 1 | 218 |
# MAGIC | 4 | 894 |
# MAGIC | 8 | 1,795 |
# MAGIC | 16 | 3,597 |
# MAGIC | 32+ | 3,993 |
# MAGIC
# MAGIC > **Note:** `SHOW max_connections` (below) reports a **higher** number than this table because it
# MAGIC > includes connections reserved for system/administrative use. The values above are what's
# MAGIC > available for your workload. See [Compute specifications](https://docs.databricks.com/aws/en/oltp/projects/manage-computes).

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("SHOW max_connections")
    max_conn = cur.fetchone()
    cur.execute("SELECT count(*) AS cnt FROM pg_stat_activity WHERE datname = current_database()")
    active = cur.fetchone()
    print(f"Max connections: {max_conn['max_connections']}")
    print(f"Active now:      {active['cnt']}")
    print(f"Available:       {int(max_conn['max_connections']) - active['cnt']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Identifying Slow Queries
# MAGIC
# MAGIC `pg_stat_statements` tracks cumulative query statistics.
# MAGIC It requires a one-time extension setup, which we do below.
# MAGIC
# MAGIC > **Note:** Statistics are stored in memory and reset when compute
# MAGIC > suspends (scale-to-zero) or restarts. For persistent history,
# MAGIC > export results to a Delta table on a schedule.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")
    conn.commit()
print("✓ pg_stat_statements extension enabled")

# COMMAND ----------

with conn.cursor() as cur:
    try:
        cur.execute("""
            SELECT
                LEFT(query, 80) AS query,
                calls,
                ROUND(total_exec_time::numeric, 2) AS total_ms,
                ROUND(mean_exec_time::numeric, 2) AS avg_ms,
                ROUND(max_exec_time::numeric, 2) AS max_ms,
                rows
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
            ORDER BY total_exec_time DESC
            LIMIT 10
        """)
        rows = cur.fetchall()
        if rows:
            print("Top 10 queries by total execution time:\n")
            for i, r in enumerate(rows, 1):
                print(f"  #{i}  calls={r['calls']}  avg={r['avg_ms']}ms  max={r['max_ms']}ms  rows={r['rows']}")
                print(f"      {r['query']}")
                print()
        else:
            print("No query statistics collected yet.")
    except Exception as e:
        print(f"pg_stat_statements not available: {e}")
        print("This is normal — it requires an extension to be enabled.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Lakebase Monitoring in the Workspace UI
# MAGIC
# MAGIC In addition to these SQL-level metrics, Databricks provides a
# MAGIC **monitoring dashboard** in the workspace UI:
# MAGIC
# MAGIC 1. Navigate to **Catalog → Lakebase** (or **Compute → Lakebase**)
# MAGIC 2. Select your project
# MAGIC 3. Click the **Monitoring** tab
# MAGIC
# MAGIC The **Metrics dashboard** shows:
# MAGIC - **Compute utilization** — current CU usage and autoscaling events
# MAGIC - **Connection count** — active connections over time
# MAGIC - **Query throughput** — queries per second
# MAGIC - **Storage usage** — data size across branches
# MAGIC - **Branch activity** — which branches are active vs. suspended
# MAGIC
# MAGIC This is especially useful during load tests (notebook 04 + the Lab Console
# MAGIC app) to watch autoscaling respond to traffic in real time.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Platform Monitoring: Export, Genie & Insights
# MAGIC
# MAGIC The `pg_stat` queries above are the live, do-it-yourself layer. Lakebase also
# MAGIC captures your project's telemetry as **Delta tables in Unity Catalog** and builds
# MAGIC managed tooling on top. You configure all of this in the **Lakebase UI**, not in code:
# MAGIC
# MAGIC | Tool | What it does | Where |
# MAGIC |------|--------------|-------|
# MAGIC | **Metrics dashboard** | System + DB metrics (CPU, RAM, connections, DB size, throughput) over time | Project → **Monitoring** |
# MAGIC | **OpenTelemetry export** | Managed collector ships metrics (prefixed `lakebase_`) and Postgres logs to any OTLP backend — Grafana, New Relic, Datadog, Honeycomb | Project → **Settings → Integrations** |
# MAGIC | **Genie** | Ask about a slow query or capacity issue in plain language; grounded in your telemetry + live compute state | Project → Monitoring → **Fix with Genie** |
# MAGIC | **Insights** | Background agent reviews telemetry on a schedule and surfaces issues proactively | Project → Monitoring → **Insights** |
# MAGIC
# MAGIC **Setup notes:**
# MAGIC - Genie and Insights need an **observability configuration** that captures telemetry to Unity
# MAGIC   Catalog. A workspace admin enables the **Advanced Postgres Telemetry** preview from the Previews page.
# MAGIC - There's **no separate charge** — it counts toward ingestion, Databricks-managed storage, and Genie usage you already pay for.
# MAGIC - For OTLP export, enter the base endpoint URL (the collector appends `/v1/metrics` and `/v1/logs`).
# MAGIC   For Datadog, enable **Delta metrics** temporality.
# MAGIC
# MAGIC **Docs:** [OpenTelemetry export](https://docs.databricks.com/aws/en/oltp/projects/opentelemetry) |
# MAGIC [AI-assisted troubleshooting](https://docs.databricks.com/aws/en/oltp/projects/ai-assisted-troubleshooting) |
# MAGIC [Insights](https://docs.databricks.com/aws/en/oltp/projects/observability-ai-insights)

# COMMAND ----------

conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC Continue to another lab path:
# MAGIC
# MAGIC | Path | Folder | What You'll Learn |
# MAGIC |------|--------|-------------------|
# MAGIC | **Data Operations** | `labs/data-operations/` | CRUD, JSONB queries, array operators, audit triggers, transactions |
# MAGIC | **Reverse ETL** | `labs/reverse-etl/` | Sync Delta Lake tables into Lakebase for low-latency serving |
# MAGIC | **Development Experience** | `labs/development-experience/` | Git-like branching, autoscaling compute, scale-to-zero |
# MAGIC | **Authentication** | `labs/authentication/` | OAuth tokens, two-layer permissions, role grants |
# MAGIC | **Backup & Recovery** | `labs/backup-recovery/` | Checkpoint branches, snapshots, point-in-time restore |
# MAGIC | **Agentic Memory** | `labs/agentic-memory/` | Persistent AI agent memory with session/message storage |
# MAGIC | **Online Feature Store** | `labs/online-feature-store/` | Real-time ML feature serving powered by Lakebase Autoscaling |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |
