# Databricks notebook source
# MAGIC %md
# MAGIC # Data Operations
# MAGIC
# MAGIC **Path:** Data Operations &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase features:** CRUD, JSONB, arrays, audit triggers, transactions
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. Query and filter products using JSONB and array operators
# MAGIC 2. Perform CRUD operations (create, update, delete)
# MAGIC 3. Inspect the automatic audit trail
# MAGIC 4. Run a multi-statement transaction
# MAGIC 5. View database statistics and index usage
# MAGIC
# MAGIC **Run `00_Setup_Lakebase_Project` first.**
# MAGIC
# MAGIC ### Running SQL against Lakebase
# MAGIC
# MAGIC The SQL in this lab can be executed from:
# MAGIC
# MAGIC - **This notebook** — uses `psycopg` to connect via the Databricks SDK (run the cells below)
# MAGIC - **Lakebase SQL Editor** — open the SQL editor in the Databricks UI for your Lakebase instance and run queries directly
# MAGIC - **psql / any PostgreSQL client** — connect with your endpoint host and credentials
# MAGIC
# MAGIC Lab connections set PostgreSQL `search_path` to **your user schema** (the same name as `PG_SCHEMA` from notebook `00`). SQL in this notebook uses unqualified table names; they resolve to that schema.
# MAGIC
# MAGIC **Docs:** [SQL Editor](https://docs.databricks.com/aws/en/oltp/projects/sql-editor) |
# MAGIC [Postgres clients](https://docs.databricks.com/aws/en/oltp/projects/postgres-clients)

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

conn = get_connection()
print(f"✓ Connected to {PROJECT_ID} / production")
show_app_link("data", "Data Ops")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. JSONB Queries
# MAGIC Products have a `metadata JSONB` column with structured attributes.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT name, price, metadata->>'brand' AS brand, metadata->>'color' AS color
        FROM products
        WHERE metadata @> '{"brand": "SoundMax"}'
    """)
    for row in cur.fetchall():
        print(row)

# COMMAND ----------

# MAGIC %md
# MAGIC ### JSONB Updates
# MAGIC Add a sale flag to all electronics without replacing existing keys.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        UPDATE products
        SET metadata = metadata || '{"on_sale": true, "discount_pct": 15}'::jsonb
        WHERE category = 'Electronics'
        RETURNING name, metadata
    """)
    for row in cur.fetchall():
        print(f"  {row['name']}: {row['metadata']}")
conn.commit()
print("✓ Metadata updated")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Array Operations
# MAGIC Products have a `tags TEXT[]` column. Postgres array operators let you
# MAGIC filter on list membership efficiently.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT name, tags FROM products
        WHERE 'featured' = ANY(tags)
    """)
    for row in cur.fetchall():
        print(f"  {row['name']}: {row['tags']}")

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT name, tags FROM products
        WHERE tags && ARRAY['audio', 'gaming']
    """)
    print("Products matching ANY of ['audio', 'gaming']:")
    for row in cur.fetchall():
        print(f"  {row['name']}: {row['tags']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. CRUD — Insert, Update, Delete

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        INSERT INTO products (name, description, price, stock_quantity, category, tags, metadata)
        VALUES ('Workshop Notebook', 'Created during the lab', 19.99, 50, 'Office',
                ARRAY['workshop', 'demo'], '{"source": "notebook-03"}'::jsonb)
        RETURNING product_id, name
    """)
    new = cur.fetchone()
    print(f"✓ Inserted: {new}")
conn.commit()

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        UPDATE products SET price = 14.99
        WHERE name = 'Workshop Notebook'
        RETURNING product_id, name, price
    """)
    print(f"✓ Updated: {cur.fetchone()}")
conn.commit()

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        DELETE FROM products
        WHERE name = 'Workshop Notebook'
        RETURNING product_id, name
    """)
    print(f"✓ Deleted: {cur.fetchone()}")
conn.commit()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Audit Trail
# MAGIC Every INSERT, UPDATE, and DELETE is automatically captured by
# MAGIC the audit trigger defined in `seed.sql`. Let's inspect the log.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT table_name, operation, COUNT(*) AS cnt,
               MIN(created_at) AS first, MAX(created_at) AS last
        FROM audit_log
        GROUP BY table_name, operation
        ORDER BY table_name, operation
    """)
    print("Audit summary:")
    for row in cur.fetchall():
        print(f"  {row['table_name']}.{row['operation']}: {row['cnt']} events")

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        SELECT audit_id, table_name, operation,
               old_data->>'name' AS old_name, new_data->>'name' AS new_name,
               created_at
        FROM audit_log
        ORDER BY created_at DESC LIMIT 10
    """)
    print("Recent audit entries:")
    for row in cur.fetchall():
        print(f"  [{row['operation']}] {row['table_name']} — "
              f"old={row.get('old_name', '-')}, new={row.get('new_name', '-')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Transactions
# MAGIC Multiple statements commit or rollback as a unit.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        INSERT INTO events (event_type, source, payload)
        VALUES ('transaction_demo', 'notebook-03', '{"step": 1}')
    """)
    cur.execute("""
        INSERT INTO events (event_type, source, payload)
        VALUES ('transaction_demo', 'notebook-03', '{"step": 2}')
    """)
conn.commit()
print("✓ Transaction committed — both rows saved atomically")

with conn.cursor() as cur:
    cur.execute("SELECT count(*) AS cnt FROM events WHERE event_type = 'transaction_demo'")
    print(f"  Transaction rows: {cur.fetchone()['cnt']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Database Statistics
# MAGIC
# MAGIC The table-size query filters `pg_tables` by your schema name (`PG_SCHEMA`), matching the workshop seed tables.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute(f"""
        SELECT schemaname, tablename,
               pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size,
               pg_size_pretty(pg_relation_size(schemaname || '.' || tablename)) AS data_size
        FROM pg_tables WHERE schemaname = '{PG_SCHEMA}'
        ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
    """)
    print("Table sizes:")
    for row in cur.fetchall():
        print(f"  {row['tablename']}: {row['total_size']} (data: {row['data_size']})")

with conn.cursor() as cur:
    cur.execute("""
        SELECT datname, numbackends AS connections, xact_commit AS commits, xact_rollback AS rollbacks,
               ROUND(100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0), 2) AS cache_hit_pct
        FROM pg_stat_database WHERE datname = current_database()
    """)
    row = cur.fetchone()
    print(f"\nDatabase stats:")
    print(f"  Connections: {row['connections']}")
    print(f"  Commits:     {row['commits']}")
    print(f"  Rollbacks:   {row['rollbacks']}")
    print(f"  Cache hit:   {row['cache_hit_pct']}%")

# COMMAND ----------

conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC Try `Advanced_Postgres.sql` in this folder for more SQL patterns, or continue to another lab path:
# MAGIC
# MAGIC | Path | Folder | What You'll Learn |
# MAGIC |------|--------|-------------------|
# MAGIC | **Reverse ETL** | `labs/reverse-etl/` | Sync Delta Lake tables into Lakebase for low-latency serving |
# MAGIC | **Development Experience** | `labs/development-experience/` | Git-like branching, autoscaling compute, scale-to-zero |
# MAGIC | **Observability** | `labs/observability/` | pg_stat views, index analysis — richer after running this lab |
# MAGIC | **Authentication** | `labs/authentication/` | OAuth tokens, two-layer permissions, role grants |
# MAGIC | **Backup & Recovery** | `labs/backup-recovery/` | Point-in-time recovery, branch snapshots, instant restore |
# MAGIC | **Agentic Memory** | `labs/agentic-memory/` | Persistent AI agent memory with session/message storage |
# MAGIC | **Online Feature Store** | `labs/online-feature-store/` | Real-time ML feature serving powered by Lakebase Autoscaling |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |
