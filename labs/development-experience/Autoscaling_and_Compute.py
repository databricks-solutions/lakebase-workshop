# Databricks notebook source
# MAGIC %md
# MAGIC # Autoscaling & Compute
# MAGIC
# MAGIC **Path:** Development Experience &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase feature:** Autoscaling compute (0.5–32 CU autoscaling; up to 112 CU fixed-size), scale-to-zero
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. Inspect your endpoint's current autoscaling configuration
# MAGIC 2. Understand CU sizing and connection limits
# MAGIC 3. Resize the compute range
# MAGIC 4. Learn about scale-to-zero behavior
# MAGIC
# MAGIC **Run `00_Setup_Lakebase_Project` first.**
# MAGIC
# MAGIC **Docs:** [Autoscaling](https://docs.databricks.com/aws/en/oltp/projects/autoscaling) |
# MAGIC [Scale to zero](https://docs.databricks.com/aws/en/oltp/projects/scale-to-zero) |
# MAGIC [Manage computes](https://docs.databricks.com/aws/en/oltp/projects/manage-computes)

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

from databricks.sdk.service.postgres import Endpoint, EndpointSpec, EndpointType, FieldMask
show_app_link("autoscale", "Autoscale Demo")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Inspect Current Compute
# MAGIC Each branch has a primary read-write endpoint that autoscales within a CU range.

# COMMAND ----------

endpoints = list(w.postgres.list_endpoints(
    parent=f"projects/{PROJECT_ID}/branches/production"
))

for ep_summary in endpoints:
    ep = w.postgres.get_endpoint(name=ep_summary.name)
    s = ep.status
    print(f"Endpoint:    {ep.name.split('/')[-1]}")
    print(f"State:       {s.current_state}")
    print(f"Type:        {s.endpoint_type}")
    print(f"Min CU:      {s.autoscaling_limit_min_cu}")
    print(f"Max CU:      {s.autoscaling_limit_max_cu}")
    print(f"RAM range:   {s.autoscaling_limit_min_cu * 2:.0f} – {s.autoscaling_limit_max_cu * 2:.0f} GB")
    print(f"Host:        {s.hosts.host}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. CU Sizing Reference
# MAGIC
# MAGIC | CU | RAM | Max Connections | Use Case |
# MAGIC |----|-----|-----------------|----------|
# MAGIC | 0.5 | ~1 GB | 104 | Dev/test, minimal traffic |
# MAGIC | 1 | ~2 GB | 209 | Light workloads |
# MAGIC | 4 | ~8 GB | 839 | Small production apps |
# MAGIC | 8 | ~16 GB | 1,678 | Medium production |
# MAGIC | 16 | ~32 GB | 3,357 | High-throughput apps |
# MAGIC | 32 | ~64 GB | 4,000 | Maximum autoscale |
# MAGIC
# MAGIC **Key constraint:** The autoscaling spread (max - min) cannot exceed **8 CU**.
# MAGIC For example: 4–8 CU is valid, but 0.5–32 CU is not.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Resize Compute (Optional)
# MAGIC
# MAGIC Uncomment the cell below to change the autoscaling range.
# MAGIC All updates require a `FieldMask` specifying which fields to change.

# COMMAND ----------

# UNCOMMENT TO RESIZE:
# ep_name = endpoints[0].name
# NEW_MIN = 0.5
# NEW_MAX = 4.0
#
# w.postgres.update_endpoint(
#     name=ep_name,
#     endpoint=Endpoint(
#         name=ep_name,
#         spec=EndpointSpec(
#             endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
#             autoscaling_limit_min_cu=NEW_MIN,
#             autoscaling_limit_max_cu=NEW_MAX,
#         ),
#     ),
#     update_mask=FieldMask(field_mask=[
#         "spec.autoscaling_limit_min_cu",
#         "spec.autoscaling_limit_max_cu",
#     ]),
# ).wait()
# print(f"✓ Resized to {NEW_MIN}–{NEW_MAX} CU")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Scale-to-Zero
# MAGIC
# MAGIC Non-production branches can **scale to zero** after a period of inactivity.
# MAGIC This saves cost for dev/test environments.
# MAGIC
# MAGIC - **Production branch:** Scale-to-zero is **disabled** by default (always active)
# MAGIC - **Other branches:** Suspend after configurable timeout (default: 5 minutes)
# MAGIC - **Wake-up time:** A few hundred milliseconds when a new connection arrives
# MAGIC - **Session reset:** Temp tables, prepared statements, and cache are cleared on wake
# MAGIC
# MAGIC To see scale-to-zero in action, create a branch in notebook `01` and wait
# MAGIC 5 minutes — then reconnect and notice the brief reactivation delay.

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
# MAGIC | **Observability** | `labs/observability/` | pg_stat views, index analysis, connection monitoring |
# MAGIC | **Authentication** | `labs/authentication/` | OAuth tokens, two-layer permissions, role grants |
# MAGIC | **Backup & Recovery** | `labs/backup-recovery/` | Point-in-time recovery, branch snapshots, instant restore |
# MAGIC | **Agentic Memory** | `labs/agentic-memory/` | Persistent AI agent memory with session/message storage |
# MAGIC | **Online Feature Store** | `labs/online-feature-store/` | Real-time ML feature serving powered by Lakebase Autoscaling |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |
