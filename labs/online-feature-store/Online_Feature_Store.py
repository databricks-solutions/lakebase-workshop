# Databricks notebook source
# MAGIC %md
# MAGIC # Online Feature Store with Lakebase
# MAGIC
# MAGIC **Path:** Online Feature Store &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase feature:** Real-time feature serving powered by Lakebase Autoscaling
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. Create a feature table in Unity Catalog
# MAGIC 2. Publish features to your existing Lakebase project for low-latency serving
# MAGIC 3. Verify online features via direct PostgreSQL access
# MAGIC 4. Update features and re-publish incrementally
# MAGIC 5. Clean up resources
# MAGIC
# MAGIC **Requirements:**
# MAGIC - Run `00_Setup_Lakebase_Project` first
# MAGIC - **DBR 16.4 LTS ML** or **serverless** compute
# MAGIC - A Unity Catalog catalog & schema with write access
# MAGIC
# MAGIC > **Why Lakebase?** Databricks Online Feature Stores are powered by Lakebase
# MAGIC > Autoscaling — the same managed PostgreSQL you explored in other labs. Your
# MAGIC > feature tables are published directly into your existing Lakebase project as
# MAGIC > PostgreSQL tables, so you get automatic scaling, low-latency reads, and direct
# MAGIC > PostgreSQL access without provisioning a separate instance.
# MAGIC >
# MAGIC > **Docs:** [Databricks Online Feature Stores](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store)

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "databricks-feature-engineering>=0.13.0" "psycopg[binary]>=3.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

from databricks.feature_engineering import FeatureEngineeringClient

fe = FeatureEngineeringClient()
print(f"✓ Feature Engineering client initialized")
show_app_link("feature-store", "Feature Store")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration
# MAGIC
# MAGIC The online store reuses your existing Lakebase project (`PROJECT_ID` from the
# MAGIC foundation notebook). Feature tables are published into the same Lakebase
# MAGIC instance alongside your workshop data — no separate instance needed.
# MAGIC
# MAGIC The [Databricks documentation](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store)
# MAGIC recommends this approach under **Cost optimization best practices**:
# MAGIC > *Reuse online stores: You can publish multiple feature tables to a single
# MAGIC > online store. For development, testing, and training scenarios, we recommend
# MAGIC > sharing one online store across multiple projects or users rather than
# MAGIC > creating separate stores.*

# COMMAND ----------

UC_CATALOG = "main"
UC_SCHEMA = f"lakebase_lab_{_sanitize(user_email).replace('-', '_')}"

FEATURE_TABLE = f"{UC_CATALOG}.{UC_SCHEMA}.customer_features"
ONLINE_TABLE = f"{UC_CATALOG}.{UC_SCHEMA}.customer_features_online"
ONLINE_STORE_NAME = PROJECT_ID

print(f"Catalog:       {UC_CATALOG}")
print(f"Schema:        {UC_SCHEMA}")
print(f"Feature table: {FEATURE_TABLE}")
print(f"Online table:  {ONLINE_TABLE}")
print(f"Online store:  {ONLINE_STORE_NAME}  (reusing existing Lakebase project)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Create the Offline Feature Table
# MAGIC
# MAGIC The offline feature table lives in Unity Catalog as a regular Delta table.
# MAGIC Before it can be published to an online store, it needs:
# MAGIC - A **primary key** constraint (non-nullable)
# MAGIC - **[Change Data Feed](https://docs.databricks.com/aws/en/delta/delta-change-data-feed)** enabled (for incremental sync)
# MAGIC
# MAGIC We'll use the Feature Engineering client to create the table with the proper
# MAGIC primary key, then enable CDF separately.
# MAGIC
# MAGIC See: [Prerequisites for publishing to online stores](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store#prerequisites-for-publishing-to-online-stores)

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {UC_CATALOG}.{UC_SCHEMA}")

from pyspark.sql.types import (
    StructType, StructField, IntegerType, DoubleType, StringType, DateType,
)
from datetime import date

schema = StructType([
    StructField("customer_id", IntegerType(), nullable=False),
    StructField("total_orders", IntegerType()),
    StructField("avg_order_value", DoubleType()),
    StructField("preferred_category", StringType()),
    StructField("lifetime_value", DoubleType()),
    StructField("risk_score", DoubleType()),
    StructField("last_order_date", DateType()),
])

data = [
    (1001, 47, 156.80, "Electronics", 7432.60, 0.12, date(2026, 4, 20)),
    (1002, 12, 89.50, "Books",       1074.00, 0.45, date(2026, 4, 18)),
    (1003, 95, 210.25, "Electronics", 19973.75, 0.05, date(2026, 4, 21)),
    (1004, 3,  42.99, "Office",       128.97, 0.78, date(2026, 4, 10)),
    (1005, 28, 175.40, "Accessories", 4911.20, 0.22, date(2026, 4, 19)),
    (1006, 61, 134.60, "Electronics", 8210.60, 0.08, date(2026, 4, 21)),
    (1007, 8,  55.75, "Books",        446.00, 0.62, date(2026, 4, 15)),
    (1008, 34, 198.90, "Electronics", 6762.60, 0.15, date(2026, 4, 20)),
    (1009, 19, 112.30, "Accessories", 2133.70, 0.31, date(2026, 4, 17)),
    (1010, 72, 88.45, "Office",       6368.40, 0.09, date(2026, 4, 21)),
]

features_df = spark.createDataFrame(data, schema=schema)

if spark.catalog.tableExists(FEATURE_TABLE):
    print(f"Feature table already exists: {FEATURE_TABLE}")
else:
    fe.create_table(
        name=FEATURE_TABLE,
        primary_keys=["customer_id"],
        df=features_df,
        description="Customer features for real-time personalization and fraud detection",
    )
    print(f"✓ Feature table created: {FEATURE_TABLE}")

# COMMAND ----------

spark.sql(f"""
ALTER TABLE {FEATURE_TABLE}
SET TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
""")
print(f"✓ Change Data Feed enabled on {FEATURE_TABLE}")

# COMMAND ----------

from pyspark.sql import Window
from pyspark.sql.functions import row_number

total = spark.sql(f"SELECT COUNT(*) AS n FROM {FEATURE_TABLE}").first()["n"]
distinct = spark.sql(f"SELECT COUNT(DISTINCT customer_id) AS n FROM {FEATURE_TABLE}").first()["n"]

if total != distinct:
    print(f"⚠ Found {total - distinct} duplicate rows — deduplicating...")
    _w = Window.partitionBy("customer_id").orderBy("customer_id")
    deduped = (
        spark.read.table(FEATURE_TABLE)
        .withColumn("_rn", row_number().over(_w))
        .filter("_rn = 1")
        .drop("_rn")
    )
    deduped.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(FEATURE_TABLE)
    spark.sql(f"ALTER TABLE {FEATURE_TABLE} SET TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')")
    new_count = spark.sql(f"SELECT COUNT(*) AS n FROM {FEATURE_TABLE}").first()["n"]
    print(f"✓ Deduplicated: {total} → {new_count} rows")
else:
    print(f"✓ No duplicates found ({total} rows, {distinct} distinct keys)")

display(spark.sql(f"SELECT * FROM {FEATURE_TABLE} ORDER BY customer_id"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Verify the Online Store (Existing Lakebase Project)
# MAGIC
# MAGIC Unlike creating a dedicated online store with `fe.create_online_store()`, we
# MAGIC reuse the Lakebase Autoscaling project you already provisioned in the
# MAGIC foundation notebook. The Feature Engineering client can reference **any**
# MAGIC Lakebase Autoscaling project as an online store via `fe.get_online_store()`.
# MAGIC
# MAGIC From the [documentation](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store#publish-a-feature-table):
# MAGIC > *For Lakebase Autoscaling projects created using the Lakebase API or UI,
# MAGIC > `name` is the last part of the resource name: `projects/{online_store_name}`*
# MAGIC
# MAGIC This means your workshop project serves double duty: operational data **and**
# MAGIC real-time feature serving — all from one Lakebase instance.

# COMMAND ----------

online_store = fe.get_online_store(name=ONLINE_STORE_NAME)
print(f"✓ Online store ready (reusing existing Lakebase project)")
print(f"  Name:     {online_store.name}")
print(f"  State:    {online_store.state}")
print(f"  Capacity: {online_store.capacity}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Publish Features to Online Store
# MAGIC
# MAGIC Publishing syncs your offline feature table into the online store for
# MAGIC low-latency reads. The default **TRIGGERED** mode does a one-time incremental
# MAGIC sync — you can re-run `publish_table` to push updates, or switch to
# MAGIC **CONTINUOUS** mode for streaming sync.
# MAGIC
# MAGIC | Publish Mode | Behavior |
# MAGIC |-------------|----------|
# MAGIC | TRIGGERED | Incremental sync on each `publish_table` call (default) |
# MAGIC | CONTINUOUS | Streaming pipeline — updates immediately as source changes |
# MAGIC | SNAPSHOT | Full copy — best when most rows change between syncs |
# MAGIC
# MAGIC See: [Publish modes](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store#publish-modes)

# COMMAND ----------

try:
    ot = w.online_tables.get(name=ONLINE_TABLE)
    state = str(getattr(getattr(ot, "status", None), "detailed_state", "")).upper()
    if "FAILED" in state or "ERROR" in state:
        print(f"⚠ Online table in error state ({state}) — deleting and re-creating...")
        w.feature_store.delete_online_table(online_table_name=ONLINE_TABLE)
        import time; time.sleep(5)
except Exception:
    pass

fe.publish_table(
    online_store=online_store,
    source_table_name=FEATURE_TABLE,
    online_table_name=ONLINE_TABLE,
)

print(f"✓ Feature table published to online store")
print(f"  Source table:  {FEATURE_TABLE}")
print(f"  Online table:  {ONLINE_TABLE}")
print(f"  Online store:  {ONLINE_STORE_NAME}")
print(f"  Publish mode:  TRIGGERED (default)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Verify Online Features
# MAGIC
# MAGIC List all online stores accessible to you and verify the publish completed.

# COMMAND ----------

stores = fe.list_online_stores()
print("Accessible online stores:")
for s in stores:
    marker = " ← yours" if s.name and ONLINE_STORE_NAME in s.name else ""
    print(f"  {s.name} | State: {s.state} | Capacity: {s.capacity}{marker}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Explore Online Features via Lakebase
# MAGIC
# MAGIC Since the online store IS your Lakebase project, you can connect directly with
# MAGIC the same `get_connection()` helper you used in other labs. The feature tables
# MAGIC appear as PostgreSQL tables inside `databricks_postgres`.
# MAGIC
# MAGIC You can also explore online features through the
# MAGIC [Unity Catalog UI](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store#explore-and-query-online-features)
# MAGIC or the [SQL Editor](https://docs.databricks.com/aws/en/oltp/projects/sql-editor).
# MAGIC
# MAGIC > **Note:** If the publish pipeline is still running, the feature table may
# MAGIC > not appear yet. Wait a minute and re-run this section.

# COMMAND ----------

try:
    ep_name = get_endpoint_name("production")
    ep = w.postgres.get_endpoint(name=ep_name)
    host = ep.status.hosts.host
    cred = w.postgres.generate_database_credential(endpoint=ep_name)

    import psycopg
    from psycopg.rows import dict_row

    fs_conn = psycopg.connect(
        host=host, dbname="databricks_postgres",
        user=user_email, password=cred.token,
        sslmode="require", row_factory=dict_row,
    )
    print(f"✓ Connected to Lakebase project: {host}")

    with fs_conn.cursor() as cur:
        cur.execute("""
            SELECT schemaname, tablename
            FROM pg_tables
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'pg_internal')
            ORDER BY schemaname, tablename
        """)
        tables = cur.fetchall()
        print(f"\nTables in the Lakebase project ({len(tables)} found):")
        for row in tables:
            label = " ← feature table" if "feature" in row['tablename'].lower() else ""
            print(f"  {row['schemaname']}.{row['tablename']}{label}")

    fs_conn.close()
    print("\n✓ Connection closed")

except Exception as e:
    print(f"Could not connect to Lakebase project: {e}")
    print("\nThis can happen if the publish pipeline is still running.")
    print("You can also query online features through the SQL editor in the")
    print("Databricks workspace UI — navigate to the online store in Catalog Explorer.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Update Features and Re-publish
# MAGIC
# MAGIC In a real workflow, features are updated by your batch or streaming pipelines.
# MAGIC Here we simulate adding new customers and re-publishing. The **TRIGGERED**
# MAGIC mode incrementally syncs only the new/changed rows.

# COMMAND ----------

from datetime import date
from delta.tables import DeltaTable

new_customers = spark.createDataFrame([
    (1011, 5,  67.20, "Books",       336.00, 0.55, date(2026, 4, 22)),
    (1012, 41, 145.90, "Electronics", 5981.90, 0.10, date(2026, 4, 22)),
], schema=schema)

dt = DeltaTable.forName(spark, FEATURE_TABLE)
dt.alias("target").merge(
    new_customers.alias("source"),
    "target.customer_id = source.customer_id"
).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()

count = spark.sql(f"SELECT COUNT(*) AS n FROM {FEATURE_TABLE}").first()["n"]
print(f"✓ Merged 2 customers into {FEATURE_TABLE} (total rows: {count})")

# COMMAND ----------

fe.publish_table(
    online_store=online_store,
    source_table_name=FEATURE_TABLE,
    online_table_name=ONLINE_TABLE,
)
print("✓ Re-published with updated features")
print("  The TRIGGERED mode incrementally syncs only the new/changed rows.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Feature Serving Endpoints
# MAGIC
# MAGIC To serve features to real-time applications (recommendation engines, fraud
# MAGIC detection, personalization), create a
# MAGIC **[Feature Serving endpoint](https://docs.databricks.com/aws/en/machine-learning/feature-store/feature-function-serving)**.
# MAGIC The endpoint handles feature lookups against the online store automatically.
# MAGIC
# MAGIC ```python
# MAGIC # Example — create a feature serving endpoint
# MAGIC from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup
# MAGIC
# MAGIC fe = FeatureEngineeringClient()
# MAGIC
# MAGIC # Define which features to serve
# MAGIC feature_lookups = [
# MAGIC     FeatureLookup(
# MAGIC         table_name="catalog.schema.customer_features",
# MAGIC         lookup_key=["customer_id"],
# MAGIC     )
# MAGIC ]
# MAGIC
# MAGIC # Models trained with feature lookups automatically resolve to online stores
# MAGIC # when deployed as serving endpoints
# MAGIC ```
# MAGIC
# MAGIC For the full walkthrough, see the
# MAGIC [Feature Serving documentation](https://docs.databricks.com/aws/en/machine-learning/feature-store/feature-function-serving).
# MAGIC
# MAGIC For details on how models automatically look up features at inference time, see
# MAGIC [Use features in online workflows](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-workflows).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cleanup
# MAGIC
# MAGIC Uncomment the cells below to remove the feature table and online table.
# MAGIC
# MAGIC **Important:** Use `delete_online_table` from the SDK — do not use `DROP TABLE`
# MAGIC in SQL, as that [leaves orphaned data](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store#delete-an-online-table)
# MAGIC in the Lakebase instance.
# MAGIC
# MAGIC > **Note:** We do **not** delete the Lakebase project here — it's shared with
# MAGIC > the other workshop labs. The project cleanup is handled in
# MAGIC > `00_Setup_Lakebase_Project`.

# COMMAND ----------

# UNCOMMENT TO DELETE THE ONLINE TABLE:
# from databricks.sdk import WorkspaceClient
# w_cleanup = WorkspaceClient()
# w_cleanup.feature_store.delete_online_table(online_table_name=ONLINE_TABLE)
# print(f"✓ Deleted online table: {ONLINE_TABLE}")

# COMMAND ----------

# UNCOMMENT TO DROP THE SOURCE FEATURE TABLE:
# spark.sql(f"DROP TABLE IF EXISTS {FEATURE_TABLE}")
# print(f"✓ Dropped feature table: {FEATURE_TABLE}")

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
# MAGIC | **Observability** | `labs/observability/` | pg_stat views, index analysis, connection monitoring |
# MAGIC | **Authentication** | `labs/authentication/` | OAuth tokens, two-layer permissions, role grants |
# MAGIC | **Backup & Recovery** | `labs/backup-recovery/` | Point-in-time recovery, branch snapshots, instant restore |
# MAGIC | **Agentic Memory** | `labs/agentic-memory/` | Persistent AI agent memory with session/message storage |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |
# MAGIC
# MAGIC **Further Reading:**
# MAGIC - [Databricks Online Feature Stores](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store)
# MAGIC - [Feature Serving Endpoints](https://docs.databricks.com/aws/en/machine-learning/feature-store/feature-function-serving)
# MAGIC - [Feature Engineering in Databricks](https://docs.databricks.com/aws/en/machine-learning/feature-store/)
# MAGIC - [Lakebase Autoscaling](https://docs.databricks.com/aws/en/oltp/projects/)
