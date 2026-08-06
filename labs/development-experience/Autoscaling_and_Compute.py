# Databricks notebook source
# MAGIC %md
# MAGIC # Autoscaling & Compute
# MAGIC
# MAGIC **Path:** Development Experience &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase feature:** Autoscaling compute (autoscaling up to 64 CU with a max−min spread ≤ 16 CU; larger fixed-size computes above 64 CU), scale-to-zero
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
# MAGIC A **CU (Compute Unit)** provides **~2 GB of RAM** and a proportional amount of CPU.
# MAGIC Max connections grow with CU size.
# MAGIC
# MAGIC | CU | RAM | Max Connections* | Use Case |
# MAGIC |----|-----|-----------------|----------|
# MAGIC | 0.5 | ~1 GB | 105 | Dev/test, minimal traffic |
# MAGIC | 1 | ~2 GB | 218 | Light workloads |
# MAGIC | 4 | ~8 GB | 894 | Small production apps |
# MAGIC | 8 | ~16 GB | 1,795 | Medium production |
# MAGIC | 16 | ~32 GB | 3,597 | High-throughput apps |
# MAGIC | 32 | ~64 GB | 3,993 | Large production |
# MAGIC | 64 | ~128 GB | 3,993 | **Maximum autoscale** |
# MAGIC
# MAGIC \*Connections available for your workload, set by the compute size. `SHOW max_connections` in Postgres
# MAGIC reports a higher number because it includes slots reserved for system use. Confirm current values in the
# MAGIC [Compute specifications](https://docs.databricks.com/aws/en/oltp/projects/manage-computes) doc.
# MAGIC
# MAGIC **Key constraints** (per the [Autoscaling doc](https://docs.databricks.com/aws/en/oltp/projects/autoscaling)):
# MAGIC - Autoscaling ranges up to **64 CU**; the spread `max − min` cannot exceed **16 CU** (e.g. 2–8 CU or 8–24 CU are valid; 0.5–64 CU is not).
# MAGIC - Computes **larger than 64 CU are fixed-size** (non-autoscaling).
# MAGIC - **Autoscaling + High Availability:** all compute instances share one autoscaling range, secondaries scale to at least the primary's size, and **scale-to-zero is not available** on HA. See `High_Availability_and_Replicas` in this path.

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
# MAGIC Any branch's compute can **scale to zero** after a period of inactivity, so you pay only for active time.
# MAGIC
# MAGIC - **Enabled by default on every branch**, including `production`, with a **24-hour** inactivity timeout.
# MAGIC - **Configurable timeout:** anywhere from **60 seconds to 7 days** (set `suspend_timeout_duration`). For dev branches, a shorter timeout like 30 minutes saves more.
# MAGIC - **Turn it off** for always-on latency-sensitive workloads by setting `no_suspension: true`.
# MAGIC - **Wake-up time:** a few hundred milliseconds when a new query arrives.
# MAGIC - **Session reset:** temp tables, prepared statements, session settings, and pooled connections reset on wake — add connection retry logic in your app.
# MAGIC
# MAGIC To see it in action, create a dev branch, set a short timeout, wait for it to idle, then reconnect and
# MAGIC notice the brief reactivation delay. See [Scale to zero](https://docs.databricks.com/aws/en/oltp/projects/scale-to-zero).

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
