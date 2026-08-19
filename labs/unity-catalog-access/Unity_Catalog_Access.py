# Databricks notebook source
# MAGIC %md
# MAGIC # Unity Catalog Access (Federated Catalog)
# MAGIC
# MAGIC **Path:** Unity Catalog Access &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase feature:** Register a Postgres database as a **read-only Unity Catalog catalog** for federated Lakehouse queries
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. Understand **why** register Lakebase in Unity Catalog (discovery, governance, live joins)
# MAGIC 2. Compare federation to synced tables, Lakehouse Sync, direct compute, and the Data API
# MAGIC 3. **Register** your project's `databricks_postgres` database as a UC catalog (SDK)
# MAGIC 4. Verify registration and query live Postgres data from the **SQL Editor** (Serverless warehouse)
# MAGIC
# MAGIC **Run `00_Setup_Lakebase_Project` first.** Seeded tables live in your user schema (`PG_SCHEMA` from `_setup`).
# MAGIC
# MAGIC **Docs:** [Register a Lakebase database in Unity Catalog](https://docs.databricks.com/aws/en/oltp/projects/register-uc) |
# MAGIC [Query from SQL editor in the workspace](https://docs.databricks.com/aws/en/oltp/projects/query-sql-editor)

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "protobuf>=5.29.5,<6" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

from databricks.sdk.service.postgres import Catalog, CatalogCatalogSpec

# One UC catalog per Postgres database. Keep this distinct from `main` (used by Reverse ETL / Feature Store).
UC_FED_CATALOG = f"lb_fed_{_sanitize(user_email).replace('-', '_')}"
PG_DATABASE = "databricks_postgres"
BRANCH_RESOURCE = f"projects/{PROJECT_ID}/branches/production"

print(f"Project:          {PROJECT_ID}")
print(f"Postgres schema:  {PG_SCHEMA}")
print(f"UC fed catalog:   {UC_FED_CATALOG}")
print(f"Branch:           {BRANCH_RESOURCE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Why register Lakebase in Unity Catalog?
# MAGIC
# MAGIC Registration creates a **read-only** UC catalog that **mirrors** your Postgres database
# MAGIC (schemas, tables, views). Data is **not copied** into Delta — SQL warehouses reach Lakebase
# MAGIC through a **federated connection** at query time.
# MAGIC
# MAGIC | Benefit | What you get |
# MAGIC |---------|----------------|
# MAGIC | **Unified discovery** | Catalog Explorer shows OLTP tables next to lakehouse tables |
# MAGIC | **Cross-source analytics** | Join live Postgres rows with Delta / UC tables in one SQL query |
# MAGIC | **UC governance** | `USE CATALOG` / `SELECT`, lineage, and audit for warehouse queries |
# MAGIC | **Lakehouse tooling** | Dashboards, Genie, scheduled queries without a separate Postgres client |
# MAGIC
# MAGIC **Write path stays on Lakebase.** UC queries cannot `INSERT`/`UPDATE`/`DELETE` through the federated catalog.
# MAGIC Use the Lakebase SQL Editor, drivers, apps, or the Data API to change data.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Compare ways to connect Lakebase ↔ the Lakehouse
# MAGIC
# MAGIC Pick the pattern that matches freshness, governance, and whether you need a **copy** of the data.
# MAGIC
# MAGIC | Method | Access | Copies data? | Governance | Best for |
# MAGIC |--------|--------|--------------|------------|----------|
# MAGIC | **UC catalog registration** *(this lab)* | Federated **read-only** via SQL warehouse | **No** (live) | Unity Catalog | Dashboards & joins of OLTP + analytics; centralized discovery |
# MAGIC | **SQL Editor → Lakebase compute** | Direct **read-write** to one project/branch | No | Postgres roles only | Interactive Postgres work; no cross-catalog joins |
# MAGIC | **Lakebase SQL Editor** | Native Postgres (incl. `\dt`, `EXPLAIN`) | No | Postgres roles | DBA / SQL-only exploration inside the Lakebase App |
# MAGIC | **Synced tables (Reverse ETL)** | Serving copy **in** Postgres | **Yes** (Delta → PG) | UC for sync control plane; Postgres for serving | Low-latency app lookups of lakehouse data |
# MAGIC | **Lakehouse Sync / CDF** | Change history **in** Delta | **Yes** (PG → Delta) | Unity Catalog on destination | Analytics, bronze CDC, audit of operational changes |
# MAGIC | **SDK OAuth + `psycopg`** | App/notebook → Postgres | No | Postgres roles | Workshop notebooks, backends that mint tokens |
# MAGIC | **Data API (PostgREST)** | HTTP → Postgres | No | **Postgres RLS** (not UC) | Lightweight REST without a driver |
# MAGIC
# MAGIC **Rule of thumb**
# MAGIC - Need **live** OLTP rows inside Databricks SQL / dashboards → **register the UC catalog**
# MAGIC - Need **fast serving** of lakehouse data to an app → **synced tables**
# MAGIC - Need a **durable change history** in open format → **Lakehouse Sync / CDF**
# MAGIC - Need **writes** or Postgres-native tooling → **direct Lakebase** (not the federated catalog)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Register the database as a Unity Catalog catalog
# MAGIC
# MAGIC Equivalent UI path: **Catalog Explorer → Create a catalog → Lakebase Postgres (Autoscaling)** →
# MAGIC pick project, `production` branch, and `databricks_postgres`.
# MAGIC
# MAGIC Requires **`CREATE CATALOG`** on the metastore. If this cell fails with a permission error,
# MAGIC ask a metastore admin to run it (or grant you the privilege), then re-run.

# COMMAND ----------

catalog_name = f"catalogs/{UC_FED_CATALOG}"
created_now = False

try:
    existing = w.postgres.get_catalog(name=catalog_name)
    print(f"Catalog already registered: {UC_FED_CATALOG}")
    print(f"  Postgres DB: {getattr(existing.status, 'postgres_database', None)}")
    print(f"  Branch:      {getattr(existing.status, 'branch', None)}")
except Exception:
    print(f"Registering {UC_FED_CATALOG} → {PG_DATABASE} on {BRANCH_RESOURCE} …")
    op = w.postgres.create_catalog(
        catalog=Catalog(
            spec=CatalogCatalogSpec(
                postgres_database=PG_DATABASE,
                branch=BRANCH_RESOURCE,
            )
        ),
        catalog_id=UC_FED_CATALOG,
    )
    result = op.wait()
    created_now = True
    print(f"Registered new catalog: {UC_FED_CATALOG}")
    print(f"  Resource: {getattr(result, 'name', catalog_name)}")

# Always re-read so later cells have a consistent object.
fed = w.postgres.get_catalog(name=catalog_name)
print(f"✓ Unity Catalog catalog ready: {UC_FED_CATALOG}")
print(f"  name:              {fed.name}")
print(f"  postgres_database: {getattr(fed.status, 'postgres_database', None)}")
print(f"  branch:            {getattr(fed.status, 'branch', None)}")
print(f"  project:           {getattr(fed.status, 'project', None)}")
print(f"  created_this_run:  {created_now}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Confirm Postgres still has the data (direct path)
# MAGIC
# MAGIC Federation does not move rows. Spot-check your seeded `products` table over the usual
# MAGIC OAuth + `psycopg` connection — this is the **direct** path from section 2.

# COMMAND ----------

conn = get_connection("production")
with conn.cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM products")
    n = cur.fetchone()["n"]
    cur.execute(
        "SELECT product_id, name, category, price FROM products ORDER BY product_id LIMIT 5"
    )
    rows = cur.fetchall()
conn.close()

print(f"✓ Direct Postgres read: {n} products in schema {PG_SCHEMA}")
for r in rows:
    print(f"  {r['product_id']:>3}  {r['name']:<28}  {r['category']:<14}  ${r['price']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Query through Unity Catalog (SQL Editor)
# MAGIC
# MAGIC Federated Lakebase catalogs require a **Serverless SQL Warehouse**. Pro and Classic warehouses
# MAGIC return `PERMISSION_DENIED`.
# MAGIC
# MAGIC ### Steps
# MAGIC 1. App switcher → **SQL Editor**
# MAGIC 2. Warehouse drop-down → pick a **Serverless** warehouse
# MAGIC 3. Run the SQL below (your catalog and schema are printed by the next cell)
# MAGIC
# MAGIC You can also browse the catalog in **Catalog Explorer** — schemas map 1:1 to Postgres schemas.
# MAGIC
# MAGIC > **Metadata lag:** new tables may not appear immediately. Use **Refresh** on the catalog in Catalog Explorer.

# COMMAND ----------

print("Paste into the SQL Editor (Serverless warehouse):\n")
print(f"-- Live federated read of Lakebase via Unity Catalog")
print(f"SELECT product_id, name, category, price")
print(f"FROM {UC_FED_CATALOG}.{PG_SCHEMA}.products")
print(f"ORDER BY product_id")
print(f"LIMIT 10;")
print()
print(f"-- Example: join OLTP (federated) with a lakehouse table in `main`")
print(f"-- SELECT p.product_id, p.name, s.some_analytic_col")
print(f"-- FROM {UC_FED_CATALOG}.{PG_SCHEMA}.products p")
print(f"-- JOIN main.{PG_SCHEMA}.some_delta_table s ON s.product_id = p.product_id;")
print()
print("Comparison reminder: this SELECT is UC-federated (read-only, Serverless warehouse).")
print("The previous cell used a direct Postgres connection (read-write capable).")

# Optional: try Spark against the federated catalog. Many notebook runtimes are not a
# Serverless SQL Warehouse — if this fails, use the SQL Editor path above (expected).
try:
    preview = spark.sql(
        f"SELECT product_id, name, category, price "
        f"FROM {UC_FED_CATALOG}.{PG_SCHEMA}.products "
        f"ORDER BY product_id LIMIT 5"
    )
    print("\n✓ Spark could read the federated catalog on this compute:")
    preview.show(truncate=False)
except Exception as e:
    print(f"\nℹ Spark federated read not available here ({type(e).__name__}: {str(e)[:180]})")
    print("  That is normal on many notebook warehouses — use the SQL Editor + Serverless warehouse.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Permissions (optional)
# MAGIC
# MAGIC After registration, **you** own the UC catalog. To let colleagues query it through SQL warehouses:
# MAGIC
# MAGIC ```sql
# MAGIC GRANT USE CATALOG ON CATALOG lb_fed_<you> TO `data-engineering`;
# MAGIC GRANT SELECT ON CATALOG lb_fed_<you> TO `data-engineering`;
# MAGIC ```
# MAGIC
# MAGIC UC grants control **federated** access only. Direct Postgres connections still need Postgres roles
# MAGIC and privileges (see `labs/authentication/`).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Clean up (optional)
# MAGIC
# MAGIC Unregistering **deletes the UC catalog entry only** — your Lakebase database and data stay intact.
# MAGIC Delete any synced tables that depend on this catalog first if you created them from it.

# COMMAND ----------

# UNCOMMENT TO UNREGISTER THE FEDERATED CATALOG:
# w.postgres.delete_catalog(name=f"catalogs/{UC_FED_CATALOG}").wait()
# print(f"✓ Unregistered catalog: {UC_FED_CATALOG}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC | Path | Folder | What You'll Learn |
# MAGIC |------|--------|-------------------|
# MAGIC | **Reverse ETL** | `labs/reverse-etl/` | Synced tables — **copy** Delta → Lakebase for serving |
# MAGIC | **Lakehouse Sync** *(Public Preview)* | `labs/lakehouse-sync/` | CDF — **copy** Lakebase → Delta change history |
# MAGIC | **Data Operations** | `labs/data-operations/` | CRUD, JSONB, arrays, triggers on Postgres directly |
# MAGIC | **Authentication** | `labs/authentication/` | OAuth, Postgres roles, Private Link |
# MAGIC | **Online Feature Store** | `labs/online-feature-store/` | Publish features into Lakebase for low-latency lookup |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Full-stack Lab Console on Lakebase |
