# Databricks notebook source
# MAGIC %md
# MAGIC # High Availability & Read Replicas
# MAGIC
# MAGIC **Path:** Development Experience &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase features:** Multi-AZ high availability (automatic failover) and read replicas
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. Understand HA compute topology (primary + secondaries across availability zones)
# MAGIC 2. See how failover works and why your connection string doesn't change
# MAGIC 3. Learn read replicas — independent read-only computes for read scaling
# MAGIC 4. Inspect your project's current endpoints (runnable) and connect to the primary
# MAGIC 5. Review the autoscaling + HA constraints and resilience best practices
# MAGIC
# MAGIC **Run `00_Setup_Lakebase_Project` first.**
# MAGIC
# MAGIC > **Configuration is done in the UI.** HA and read replicas are configured from the **Computes**
# MAGIC > tab / **Edit compute** drawer in the Lakebase App (there isn't a documented SDK path for
# MAGIC > enabling HA or adding replicas today). The cells below are **inspection-only** — they read your
# MAGIC > current topology and connect; they don't mutate compute.
# MAGIC
# MAGIC **Docs:** [High availability](https://docs.databricks.com/aws/en/oltp/projects/high-availability) |
# MAGIC [Read replicas](https://docs.databricks.com/aws/en/oltp/projects/read-replicas)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. High availability topology
# MAGIC
# MAGIC A high-availability endpoint always has **exactly one primary** and **1–3 secondary** compute
# MAGIC instances, spread across **availability zones**. The primary handles all read/write traffic;
# MAGIC secondaries stand by (and can optionally serve reads). Failover capacity is **pre-allocated** —
# MAGIC promotion needs no new provisioning.
# MAGIC
# MAGIC An HA endpoint exposes **two connection strings**:
# MAGIC
# MAGIC | Connection string | Host pattern | Use for |
# MAGIC |-------------------|--------------|---------|
# MAGIC | **Primary** | `{endpoint-id}.database.{region}.databricks.com` | All writes; reads that must hit the current primary. Auto-routes to whoever is primary after a failover. |
# MAGIC | **Secondary (read-only)** | `{endpoint-id}-ro.database.{region}.databricks.com` | Read offload — **only** when *Allow access to read-only compute instances* is enabled. |
# MAGIC
# MAGIC Each secondary's **Access** setting is either **Read-only** (serves reads via `-ro` and can be
# MAGIC promoted) or **Disabled** (standby for failover only). Enable readable secondaries from the
# MAGIC **Edit compute** drawer.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Failover behavior
# MAGIC
# MAGIC - Lakebase monitors primary health continuously; if it becomes unavailable, **failover is
# MAGIC   automatic** and **preserves all committed transactions**.
# MAGIC - The **primary connection string is unchanged** after failover — it re-points to the newly
# MAGIC   promoted compute. Apps don't reconfigure anything.
# MAGIC - **Existing connections are terminated** during failover and must reconnect — apps with retry
# MAGIC   logic recover within seconds.
# MAGIC - With readable secondaries: the promoted secondary stops serving reads. With **2+** readable
# MAGIC   secondaries, `-ro` reads continue at reduced capacity; with only **1**, reads are interrupted
# MAGIC   until a replacement is provisioned.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Secondary computes vs. standalone read replicas
# MAGIC
# MAGIC Both add read capacity, but they're different features and can coexist on the same branch:
# MAGIC
# MAGIC | | Secondary computes (HA) | Standalone read replicas |
# MAGIC |---|---|---|
# MAGIC | **Purpose** | Failover + optional read offload | Read offload only |
# MAGIC | **Added via** | High availability configuration | **Add Read Replica** (Computes tab) |
# MAGIC | **In failover?** | Yes | No |
# MAGIC | **Connection** | `-ro` on the primary endpoint | Its **own** separate endpoint |
# MAGIC | **Sizing** | Shared with primary (endpoint-level) | Sized **independently** |
# MAGIC | **Scale-to-zero** | Not available on HA | Supported (immediately up to date on wake) |
# MAGIC
# MAGIC Read replicas read from the **same storage layer** as the primary (no data duplication, no extra
# MAGIC storage cost), are created **in seconds**, and are **eventually consistent** (asynchronous). You
# MAGIC can add **up to 6 read replicas per branch**. Use them for horizontal read scaling, analytics /
# MAGIC reporting offload, and read-only access.

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Inspect your current topology (runnable)
# MAGIC
# MAGIC List the endpoints on your `production` branch and show each one's type, state, and CU range.
# MAGIC On a single-compute project you'll see one read-write endpoint; on an HA project you'll also see
# MAGIC read-only computes, and any read replicas appear as their own endpoints.

# COMMAND ----------

endpoints = list(w.postgres.list_endpoints(parent=f"projects/{PROJECT_ID}/branches/production"))

print(f"Endpoints on production: {len(endpoints)}\n")
for ep_summary in endpoints:
    ep = w.postgres.get_endpoint(name=ep_summary.name)
    s = ep.status
    print(f"Endpoint:  {ep.name.split('/')[-1]}")
    print(f"  Type:    {s.endpoint_type}")
    print(f"  State:   {s.current_state}")
    print(f"  CU:      {s.autoscaling_limit_min_cu}–{s.autoscaling_limit_max_cu}")
    print(f"  Host:    {s.hosts.host}")
    print()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Connect to the primary
# MAGIC
# MAGIC `get_connection()` uses the branch's primary endpoint. If you've enabled readable secondaries or
# MAGIC added a read replica, you'd point a read-only connection at the `-ro` host (HA) or the replica's
# MAGIC own host — copy those from the **Connect** dialog in the Lakebase App.

# COMMAND ----------

conn = get_connection("production")
with conn.cursor() as cur:
    cur.execute("SELECT current_user, inet_server_addr() AS server_ip, version()")
    print(dict(cur.fetchone()))
conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Limits & best practices
# MAGIC
# MAGIC **HA limits**
# MAGIC
# MAGIC | Limit | Value |
# MAGIC |-------|-------|
# MAGIC | Compute instances | 2, 3, or 4 (1 primary + 1–3 secondaries) |
# MAGIC | Autoscaling range (max − min) | ≤ 16 CU (same as standalone) |
# MAGIC | Secondary sizing | Always ≥ the primary's CU size |
# MAGIC | Scale to zero | **Not available** on HA (you can manually pause all computes) |
# MAGIC | Read replicas per branch | Up to 6 |
# MAGIC
# MAGIC **Resilience best practices**
# MAGIC
# MAGIC - **Implement connection retry logic** — connections drop during failover; configure TCP
# MAGIC   keepalives / a connection timeout so failure is detected promptly and retried.
# MAGIC - **Size your secondary count for the use case** — 1 secondary covers failover; use **2+** if you
# MAGIC   also serve reads from secondaries (so reads survive a failover).
# MAGIC - **Don't overload secondaries** — the service may restart an overloaded/lagging secondary;
# MAGIC   monitor load and raise CU size under sustained pressure.
# MAGIC
# MAGIC **Where HA fits:** HA protects against **compute failure within a region**. For **regional**
# MAGIC protection, see the cross-region **Disaster Recovery** note in
# MAGIC `labs/backup-recovery/Backup_and_Recovery.py`.

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC | Path | Folder | What You'll Learn |
# MAGIC |------|--------|-------------------|
# MAGIC | **Autoscaling & Compute** | this path | CU sizing, resize, scale-to-zero (HA shares the same autoscaling range) |
# MAGIC | **Backup & Recovery** | `labs/backup-recovery/` | PITR, snapshots, and cross-region DR |
# MAGIC | **Observability** | `labs/observability/` | Monitor connections, replication delay, and query load |
