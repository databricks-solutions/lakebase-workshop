# Databricks notebook source
# MAGIC %md
# MAGIC # Synced Tables (Reverse ETL)
# MAGIC
# MAGIC **Path:** Reverse ETL &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase feature:** **Synced tables** — serve Unity Catalog Delta data from Lakebase Postgres
# MAGIC
# MAGIC > **Terminology:** the current product term is **"synced tables"** (serving lakehouse data from
# MAGIC > Lakebase). You'll still hear "Reverse ETL" informally — that's what the folder is named — but
# MAGIC > prefer "synced tables" to match the docs and UI.
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. Set up a Delta source table (use your own data or generate sample data)
# MAGIC 2. Understand the three sync modes — **Snapshot**, **Triggered**, and **Continuous**
# MAGIC 3. Set up a synced table that pushes data to Lakebase
# MAGIC 4. Check sync status
# MAGIC 5. Update the source and observe the sync
# MAGIC
# MAGIC **Prerequisites:**
# MAGIC - Run `00_Setup_Lakebase_Project` first
# MAGIC - A Unity Catalog catalog & schema with write access
# MAGIC
# MAGIC **Docs:** [Serve lakehouse data with synced tables](https://docs.databricks.com/aws/en/oltp/projects/sync-tables)
# MAGIC
# MAGIC > **Bring your own data or use ours:** This lab generates a sample products table
# MAGIC > by default. If you already have a Delta table you'd like to sync, skip the
# MAGIC > sample data step and point the configuration at your own table instead.
# MAGIC
# MAGIC > **Note:** Synced tables are owned by the sync pipeline. If you deploy the
# MAGIC > Lab Console app, you must also GRANT the app's Service Principal access
# MAGIC > to synced tables. See `docs/PERMISSIONS.md`.

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

show_app_link("sync", "Reverse ETL")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration
# MAGIC
# MAGIC Set your catalog and schema below. The lab will create the schema if it
# MAGIC doesn't exist. By default it generates a sample `sample_products` table —
# MAGIC set `USE_OWN_DATA = True` if you want to sync an existing Delta table instead.

# COMMAND ----------

UC_CATALOG = "main"  # point to your own catalog
UC_SCHEMA  = f"lakebase_lab_{_sanitize(user_email).replace('-', '_')}"

USE_OWN_DATA = False

if USE_OWN_DATA:
    SOURCE_TABLE = "<catalog.schema.your_table>"   # point to your existing Delta table
else:
    SOURCE_TABLE = f"{UC_CATALOG}.{UC_SCHEMA}.sample_products"

SYNCED_TABLE = f"{UC_CATALOG}.{UC_SCHEMA}.products_synced"

print(f"Catalog:      {UC_CATALOG}")
print(f"Schema:       {UC_SCHEMA}")
print(f"Source table:  {SOURCE_TABLE}")
print(f"Synced table:  {SYNCED_TABLE}")
print(f"Using own data: {USE_OWN_DATA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Create a Delta Source Table
# MAGIC
# MAGIC Change Data Feed (CDF) must be enabled for synced tables to track changes.
# MAGIC
# MAGIC **Using your own data?** Skip this cell — just make sure your table has CDF
# MAGIC enabled: `ALTER TABLE <table> SET TBLPROPERTIES (delta.enableChangeDataFeed = true)`

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {UC_CATALOG}.{UC_SCHEMA}")

if not USE_OWN_DATA:
    spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {SOURCE_TABLE} (
        product_id INT,
        name STRING,
        price DOUBLE,
        category STRING,
        updated_at TIMESTAMP
    )
    USING DELTA
    TBLPROPERTIES (delta.enableChangeDataFeed = true)
    """)

    spark.sql(f"""
    MERGE INTO {SOURCE_TABLE} AS t
    USING (
        SELECT * FROM VALUES
            (1, 'Wireless Mouse', 29.99, 'Electronics', current_timestamp()),
            (2, 'USB-C Adapter', 14.99, 'Accessories', current_timestamp()),
            (3, 'Laptop Sleeve', 24.99, 'Accessories', current_timestamp()),
            (4, 'Webcam HD', 59.99, 'Electronics', current_timestamp()),
            (5, 'Desk Lamp', 34.99, 'Office', current_timestamp())
        AS s(product_id, name, price, category, updated_at)
    ) ON t.product_id = s.product_id
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
    """)
    print(f"✓ Sample data created in {SOURCE_TABLE}")
else:
    print(f"Using existing table: {SOURCE_TABLE}")

display(spark.sql(f"SELECT * FROM {SOURCE_TABLE}"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Sync Pipeline Modes
# MAGIC
# MAGIC Before creating the synced table, it's important to understand the three **sync modes**
# MAGIC available. Choose the right one based on your freshness requirements, cost tolerance,
# MAGIC and source table characteristics.
# MAGIC
# MAGIC | Mode | How It Works | When to Use | CDF Required? |
# MAGIC |------|-------------|-------------|---------------|
# MAGIC | **Snapshot** | Full copy of all data each sync cycle | Source changes >10% of rows per cycle, or source doesn't support CDF (views, Iceberg tables) | No |
# MAGIC | **Triggered** | Incremental updates run on demand or at intervals | Source rows change on a known cadence; good cost/freshness balance | Yes |
# MAGIC | **Continuous** | Real-time streaming with seconds of latency (minimum 15-second intervals) | Changes must appear in Lakebase in near real time | Yes |
# MAGIC
# MAGIC ### Mode Details
# MAGIC
# MAGIC **Snapshot mode** performs a full replacement of all data on each sync. It is
# MAGIC ~10× more efficient than incremental modes when more than 10% of rows change per
# MAGIC cycle. Snapshot is also the *only* option for sources that don't support Change Data
# MAGIC Feed, such as views, materialized views, and Iceberg tables.
# MAGIC
# MAGIC **Triggered mode** propagates inserts, updates, and deletes incrementally using
# MAGIC Change Data Feed. Subsequent syncs must be triggered explicitly — either manually
# MAGIC from Catalog Explorer, via the SDK, or by scheduling a **Database Table Sync pipeline**
# MAGIC task in Lakeflow Jobs. This gives you precise control over when syncs run and is the
# MAGIC most cost-effective option for tables that change on a predictable cadence.
# MAGIC *Note: running triggered syncs at intervals shorter than 5 minutes can become expensive.*
# MAGIC
# MAGIC **Continuous mode** is fully self-managing — once started, it streams changes from
# MAGIC the source table to Lakebase with near-real-time latency (seconds). It provides the
# MAGIC lowest lag but at the highest cost, since the pipeline runs continuously.
# MAGIC
# MAGIC ### Scheduling Triggered & Snapshot Syncs
# MAGIC
# MAGIC For Snapshot and Triggered modes, the initial sync runs automatically on creation.
# MAGIC To schedule subsequent syncs, create a Lakeflow Job with a **Database Table Sync
# MAGIC pipeline** task:
# MAGIC
# MAGIC - **Table update trigger** — fires when the source Unity Catalog table is updated,
# MAGIC   giving near-real-time freshness without the always-on cost of Continuous mode
# MAGIC - **Cron schedule** — runs the sync at a fixed cadence (e.g., nightly or hourly),
# MAGIC   well-suited for Snapshot mode where a periodic full refresh is most efficient
# MAGIC
# MAGIC ### Performance & Capacity
# MAGIC
# MAGIC | Write Pattern | Throughput (per CU) |
# MAGIC |--------------|---------------------|
# MAGIC | Continuous / Triggered (incremental) | ~150 rows/sec |
# MAGIC | Snapshot (full refresh) | ~2,000 rows/sec |
# MAGIC
# MAGIC Each synced table uses up to 16 connections to your Lakebase database. Total logical
# MAGIC data size limit across all synced tables is 16 TB. Databricks recommends individual
# MAGIC tables not exceed 1 TB for tables requiring refreshes.
# MAGIC
# MAGIC > **16 TB is the synced-table quota specifically** — the combined logical size of all synced
# MAGIC > tables. It is *separate* from your project's overall Postgres storage capacity (the default
# MAGIC > project storage limit is larger and has been increasing). Don't conflate the two.
# MAGIC
# MAGIC > **Docs:** [Sync modes](https://docs.databricks.com/aws/en/oltp/projects/sync-tables#sync-modes)
# MAGIC > &nbsp;|&nbsp; [Schedule syncs with Lakeflow Jobs](https://docs.databricks.com/aws/en/oltp/projects/sync-tables#schedule-or-trigger-subsequent-syncs)
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## 2. Create the Synced Table
# MAGIC
# MAGIC Below we create a synced table using **Triggered** mode. This means changes are
# MAGIC propagated incrementally each time you trigger a sync (manually, via SDK, or via
# MAGIC a Lakeflow Job). To use a different mode, change `SYNC_MODE` below.
# MAGIC
# MAGIC > **Where does the data land in Lakebase?** Synced tables automatically create a
# MAGIC > PostgreSQL schema matching the UC schema name. Look for `products_synced` under
# MAGIC > the `lakebase_lab_<your_username>` schema in Lakebase — not the workshop seed schema from notebook `00` unless you pointed sync there.
# MAGIC
# MAGIC **Using your own data?** Update `PRIMARY_KEY_COLUMNS` below to match
# MAGIC your table's primary key.

# COMMAND ----------

from databricks.sdk.service.postgres import (
    SyncedTable,
    SyncedTableSyncedTableSpec,
    SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy,
    NewPipelineSpec,
)

PRIMARY_KEY_COLUMNS = ["product_id"]

# Choose: "TRIGGERED", "CONTINUOUS", or "SNAPSHOT"
#   TRIGGERED  — incremental sync on demand (requires CDF on source table)
#   CONTINUOUS — real-time streaming, lowest latency, highest cost (requires CDF)
#   SNAPSHOT   — full data copy each cycle; works with any source including views
SYNC_MODE = "TRIGGERED"

scheduling_policy = SyncedTableSyncedTableSpecSyncedTableSchedulingPolicy[SYNC_MODE]

try:
    existing = w.postgres.get_synced_table(name=f"synced_tables/{SYNCED_TABLE}")
    print(f"Synced table already exists: {SYNCED_TABLE} (state: {existing.status.detailed_state})")
    synced_table = existing
except Exception:
    synced_table = w.postgres.create_synced_table(
        synced_table=SyncedTable(
            spec=SyncedTableSyncedTableSpec(
                branch=f"projects/{PROJECT_ID}/branches/production",
                postgres_database="databricks_postgres",
                source_table_full_name=SOURCE_TABLE,
                primary_key_columns=PRIMARY_KEY_COLUMNS,
                scheduling_policy=scheduling_policy,
                new_pipeline_spec=NewPipelineSpec(
                    storage_catalog=UC_CATALOG,
                    storage_schema=UC_SCHEMA,
                ),
            ),
        ),
        synced_table_id=SYNCED_TABLE,
    )
    print(f"✓ Synced table created: {SYNCED_TABLE} (mode: {SYNC_MODE})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Check Sync Status

# COMMAND ----------

status = w.postgres.get_synced_table(name=f"synced_tables/{SYNCED_TABLE}")
print(f"State:   {status.status.detailed_state}")
print(f"Message: {status.status.message or 'N/A'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Update Source & Trigger Re-sync
# MAGIC Add rows to the Delta table, then trigger the pipeline again to see
# MAGIC Reverse ETL push the changes to Lakebase.
# MAGIC
# MAGIC How the re-sync behaves depends on the sync mode you chose above:
# MAGIC
# MAGIC - **Triggered** — you must manually trigger a sync (button below, Catalog Explorer,
# MAGIC   or a Lakeflow Job). Only changed rows are propagated via CDF.
# MAGIC - **Continuous** — changes propagate automatically within seconds. No action needed.
# MAGIC - **Snapshot** — you must trigger a sync, and it will re-copy all data (not just changes).
# MAGIC
# MAGIC **Using your own data?** Make a change to your source table (insert, update,
# MAGIC or delete), then trigger a sync from Catalog Explorer → Synced Tables tab.

# COMMAND ----------

if not USE_OWN_DATA:
    spark.sql(f"""
    MERGE INTO {SOURCE_TABLE} AS t
    USING (
        SELECT * FROM VALUES
            (6, 'Standing Desk', 299.99, 'Office', current_timestamp()),
            (7, 'Monitor Arm', 89.99, 'Accessories', current_timestamp())
        AS s(product_id, name, price, category, updated_at)
    ) ON t.product_id = s.product_id
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
    """)
    print("✓ New rows upserted into sample table.")
else:
    print("Make a change to your source table, then trigger a re-sync.")

if SYNC_MODE == "CONTINUOUS":
    print("Continuous mode — changes will propagate automatically within seconds.")
else:
    print(f"{SYNC_MODE.title()} mode — trigger a sync from Catalog Explorer → Synced Tables tab, or schedule via a Lakeflow Job.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Grant Service Principal Access (for App)
# MAGIC
# MAGIC If you plan to deploy the Lab Console app, its Service Principal needs
# MAGIC explicit access to synced tables. **Synced tables are special:** they are
# MAGIC owned by the internal `databricks_writer_` role (the sync pipeline manages
# MAGIC them), **not** by you. A plain `GRANT ALL ON ALL TABLES` run as a normal
# MAGIC user will silently miss them.
# MAGIC
# MAGIC Per the docs, the **`databricks_superuser`** grants read access to another
# MAGIC identity. Connect as the `databricks_superuser` and run:
# MAGIC
# MAGIC ```sql
# MAGIC -- Read access to the synced-table schema and table (run as databricks_superuser)
# MAGIC GRANT USAGE ON SCHEMA <your_sync_schema> TO "<SP_CLIENT_ID>";
# MAGIC GRANT SELECT ON <your_sync_schema>.<synced_table> TO "<SP_CLIENT_ID>";
# MAGIC ```
# MAGIC
# MAGIC To let an identity perform allowed management operations on a synced table
# MAGIC (`CREATE/ALTER/DROP INDEX`, `DROP TABLE`), register it as a manager instead:
# MAGIC
# MAGIC ```sql
# MAGIC CREATE EXTENSION IF NOT EXISTS databricks_auth;
# MAGIC SELECT databricks_synced_table_add_manager(
# MAGIC     '"<your_sync_schema>"."<synced_table>"'::regclass, '<SP_CLIENT_ID>');
# MAGIC ```
# MAGIC
# MAGIC > **Docs:** [Synced tables — Ownership and permissions](https://docs.databricks.com/aws/en/oltp/projects/sync-tables#ownership-and-permissions)

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC Continue to another lab path:
# MAGIC
# MAGIC | Path | Folder | What You'll Learn |
# MAGIC |------|--------|-------------------|
# MAGIC | **Lakehouse Sync** *(Public Preview)* | `labs/lakehouse-sync/` | The inverse pattern — sync Lakebase → Unity Catalog Delta via Lakebase Change Data Feed (CDC change history) |
# MAGIC | **Data Operations** | `labs/data-operations/` | CRUD, JSONB queries, array operators, audit triggers, transactions |
# MAGIC | **Development Experience** | `labs/development-experience/` | Git-like branching, autoscaling compute, scale-to-zero |
# MAGIC | **Observability** | `labs/observability/` | pg_stat views, index analysis, connection monitoring |
# MAGIC | **Authentication** | `labs/authentication/` | OAuth tokens, two-layer permissions, role grants |
# MAGIC | **Backup & Recovery** | `labs/backup-recovery/` | Point-in-time recovery, branch snapshots, instant restore |
# MAGIC | **Agentic Memory** | `labs/agentic-memory/` | Persistent AI agent memory with session/message storage |
# MAGIC | **Online Feature Store** | `labs/online-feature-store/` | Real-time ML feature serving powered by Lakebase Autoscaling |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |
