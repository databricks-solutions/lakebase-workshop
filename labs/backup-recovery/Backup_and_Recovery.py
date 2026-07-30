# Databricks notebook source
# MAGIC %md
# MAGIC # Backup & Recovery
# MAGIC
# MAGIC **Path:** Backup & Recovery &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase features:** Point-in-time recovery (PITR), branch snapshots, instant restore
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. Understand Lakebase's built-in backup architecture
# MAGIC 2. Create a "snapshot" branch to preserve a known-good state
# MAGIC 3. Simulate a data loss scenario on a development branch
# MAGIC 4. Recover the data by creating a new branch from the snapshot
# MAGIC 5. Learn about point-in-time recovery (PITR) via the SDK
# MAGIC
# MAGIC **Run `00_Setup_Lakebase_Project` first.** Table queries use unqualified names; your schema is set via `search_path` in `_setup`.
# MAGIC
# MAGIC **Docs:** [Point-in-time restore](https://docs.databricks.com/aws/en/oltp/projects/point-in-time-restore) |
# MAGIC [Branches](https://docs.databricks.com/aws/en/oltp/projects/branches)

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

import time
from databricks.sdk.service.postgres import Branch, BranchSpec, Duration
show_app_link("backup", "Backup & Recovery")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Lakebase Backup Architecture
# MAGIC
# MAGIC Lakebase provides **multiple layers of data protection** built in:
# MAGIC
# MAGIC | Feature | How It Works | Use Case |
# MAGIC |---------|-------------|----------|
# MAGIC | **Continuous WAL archival** | Write-ahead logs are continuously streamed to durable storage | Foundation for PITR |
# MAGIC | **Point-in-Time Recovery** | Restore to any second within the configured window (up to 30 days) | Accidental data corruption or deletion |
# MAGIC | **Branch snapshots** | Create a copy-on-write branch as a named checkpoint | Pre-migration safety net |
# MAGIC | **Branch TTL** | Branches auto-delete after a configurable time | Dev/test cleanup |
# MAGIC
# MAGIC **You do NOT need to configure backups** — continuous protection is always on.
# MAGIC You only set the *history window* at the project level.
# MAGIC
# MAGIC > **Storage billing (effective Jun 1, 2026):** recovery is protected by default, but the
# MAGIC > storage it uses is billed. Lakebase bills three storage components separately:
# MAGIC > **(1) primary data**, **(2) PITR history** (WAL retained for your history window), and
# MAGIC > **(3) snapshots**. A longer history window and more/larger snapshot branches increase
# MAGIC > storage cost — right-size the window and clean up snapshots you no longer need.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create a Snapshot Branch
# MAGIC
# MAGIC Before making risky changes (schema migration, bulk delete, etc.),
# MAGIC create a branch as a **named checkpoint**. This is instant and
# MAGIC costs no additional storage until data diverges.
# MAGIC
# MAGIC > **No TTL on snapshots:** Snapshot branches must not have a TTL because
# MAGIC > Lakebase does not allow creating child branches from branches with an
# MAGIC > expiration. Delete snapshot branches manually when no longer needed.

# COMMAND ----------

SNAPSHOT_BRANCH = "lab-snapshot-pre-migration"

try:
    result = w.postgres.create_branch(
        parent=f"projects/{PROJECT_ID}",
        branch=Branch(
            spec=BranchSpec(
                source_branch=f"projects/{PROJECT_ID}/branches/production",
                no_expiry=True,  # snapshots must be non-expiring: you can't create child branches from an expiring branch
            )
        ),
        branch_id=SNAPSHOT_BRANCH,
    ).wait()
    print(f"✓ Snapshot branch created: {result.name}")
except Exception as e:
    if "already exists" in str(e).lower():
        print(f"Snapshot branch {SNAPSHOT_BRANCH} already exists — continuing")
    else:
        raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Simulate a Risky Change
# MAGIC
# MAGIC Let's create a working branch, make changes, and then simulate
# MAGIC a "bad migration" that destroys data.

# COMMAND ----------

WORK_BRANCH = "lab-migration-test"

try:
    result = w.postgres.create_branch(
        parent=f"projects/{PROJECT_ID}",
        branch=Branch(
            spec=BranchSpec(
                source_branch=f"projects/{PROJECT_ID}/branches/production",
                ttl=Duration(seconds=86400),
            )
        ),
        branch_id=WORK_BRANCH,
    ).wait()
    print(f"✓ Work branch created: {result.name}")
except Exception as e:
    if "already exists" in str(e).lower():
        print(f"Work branch {WORK_BRANCH} already exists — continuing")
    else:
        raise

# COMMAND ----------

print("Waiting for work branch endpoint...")
wait_for_endpoint(WORK_BRANCH)
work_conn = get_connection(WORK_BRANCH)
print("✓ Connected to work branch")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Check current state (before the "bad migration")

# COMMAND ----------

with work_conn.cursor() as cur:
    cur.execute("SELECT count(*) AS cnt FROM products")
    print(f"Products before migration: {cur.fetchone()['cnt']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Simulate the disaster — accidentally drop the products table

# COMMAND ----------

with work_conn.cursor() as cur:
    cur.execute("DROP TABLE IF EXISTS products CASCADE")
work_conn.commit()
print("💥 Products table dropped! (simulated bad migration)")

with work_conn.cursor() as cur:
    try:
        cur.execute("SELECT count(*) FROM products")
    except Exception as e:
        print(f"Confirmed: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Recover from the Snapshot
# MAGIC
# MAGIC The production branch is untouched (we did the damage on a work branch).
# MAGIC But if this *had* been production, here's how you'd recover:
# MAGIC
# MAGIC **Option A: Create a new branch from the snapshot**

# COMMAND ----------

RECOVERY_BRANCH = "lab-recovered"

try:
    result = w.postgres.create_branch(
        parent=f"projects/{PROJECT_ID}",
        branch=Branch(
            spec=BranchSpec(
                source_branch=f"projects/{PROJECT_ID}/branches/{SNAPSHOT_BRANCH}",
                ttl=Duration(seconds=86400),
            )
        ),
        branch_id=RECOVERY_BRANCH,
    ).wait()
    print(f"✓ Recovery branch created from snapshot: {result.name}")
except Exception as e:
    if "already exists" in str(e).lower():
        print(f"Recovery branch {RECOVERY_BRANCH} already exists — continuing")
    else:
        raise

# COMMAND ----------

print("Waiting for recovery branch endpoint...")
wait_for_endpoint(RECOVERY_BRANCH)
recovery_conn = get_connection(RECOVERY_BRANCH)

with recovery_conn.cursor() as cur:
    cur.execute("SELECT count(*) AS cnt FROM products")
    count = cur.fetchone()['cnt']
    print(f"✓ Products on recovered branch: {count}")
    print("  Data is fully intact — recovered from snapshot!")

recovery_conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Point-in-Time Recovery (PITR)
# MAGIC
# MAGIC For production scenarios where you need to recover to an *exact moment*
# MAGIC (not just a named snapshot), Lakebase supports PITR.
# MAGIC
# MAGIC ### How PITR Works
# MAGIC
# MAGIC 1. Lakebase continuously archives WAL (write-ahead log) segments
# MAGIC 2. You specify a target timestamp
# MAGIC 3. Lakebase creates a **new root branch** by replaying WAL up to that timestamp
# MAGIC 4. The recovered branch is a full, independent copy of the database
# MAGIC
# MAGIC ### The documented path is the UI: **Project → Backup & Restore**
# MAGIC
# MAGIC Per the [Point-in-time restore doc](https://docs.databricks.com/aws/en/oltp/projects/point-in-time-restore),
# MAGIC PITR is driven from the **Backup & Restore** flow in the Lakebase App: pick a timestamp within
# MAGIC the window and Lakebase provisions a new root branch at that point in time.
# MAGIC
# MAGIC > **Root-branch limit:** a restore creates a **new root branch**, and a project can have at
# MAGIC > most **3 root branches**. Delete an older recovery root before restoring again if you hit the limit.
# MAGIC
# MAGIC ### Using PITR via the SDK
# MAGIC
# MAGIC The `BranchSpec` field for point-in-time branching is **`source_branch_time`** (a protobuf
# MAGIC `Timestamp` marking the moment on the source branch to restore from). This creates a new root
# MAGIC branch — the same result as the UI flow above.
# MAGIC
# MAGIC ```python
# MAGIC from datetime import datetime, timezone, timedelta
# MAGIC from databricks.sdk.service.postgres import Branch, BranchSpec
# MAGIC from google.protobuf.timestamp_pb2 import Timestamp
# MAGIC
# MAGIC # Recover to 30 minutes ago
# MAGIC target = datetime.now(timezone.utc) - timedelta(minutes=30)
# MAGIC
# MAGIC ts = Timestamp()
# MAGIC ts.FromDatetime(target)
# MAGIC
# MAGIC w.postgres.create_branch(
# MAGIC     parent=f"projects/{PROJECT_ID}",
# MAGIC     branch=Branch(
# MAGIC         spec=BranchSpec(
# MAGIC             source_branch=f"projects/{PROJECT_ID}/branches/production",
# MAGIC             source_branch_time=ts,   # the point in time on the source branch
# MAGIC         )
# MAGIC     ),
# MAGIC     branch_id="pitr-recovery",
# MAGIC ).wait()
# MAGIC ```
# MAGIC
# MAGIC ### Recovery Window
# MAGIC
# MAGIC - Default: **7 days**
# MAGIC - Range: **2–30 days** (30 is the maximum)
# MAGIC - Configurable at the project level (Project → Settings → History window)
# MAGIC - You can recover to any **second** within the window
# MAGIC
# MAGIC ### Beyond a single region: Disaster Recovery
# MAGIC
# MAGIC PITR and snapshots protect against data loss **within a region**. For protection against a
# MAGIC regional impairment, Lakebase is adding **cross-region / cross-workspace Disaster Recovery**
# MAGIC (Beta / on the roadmap). High Availability (multi-AZ failover) protects against *compute*
# MAGIC failure within a region — see `High_Availability_and_Replicas` in the development-experience path.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Best Practices
# MAGIC
# MAGIC | Scenario | Recommended Approach |
# MAGIC |----------|---------------------|
# MAGIC | **Before a schema migration** | Create a snapshot branch (instant, free until divergence) |
# MAGIC | **Accidental DELETE/UPDATE** | PITR to the second before the mistake |
# MAGIC | **Testing destructive operations** | Create a work branch, test there, delete when done |
# MAGIC | **Compliance / audit retention** | Set the history window to its 30-day maximum at the project level |
# MAGIC | **Disaster recovery drill** | Periodically create a branch from PITR, verify data integrity |

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Clean Up (Optional)
# MAGIC
# MAGIC Delete the branches created in this notebook. Production is untouched.

# COMMAND ----------

# UNCOMMENT TO CLEAN UP:
# Delete child branches before their parent — RECOVERY_BRANCH is a child of
# SNAPSHOT_BRANCH, and a branch with children cannot be deleted.
# work_conn.close()
# for branch in [WORK_BRANCH, RECOVERY_BRANCH, SNAPSHOT_BRANCH]:
#     try:
#         w.postgres.delete_branch(name=f"projects/{PROJECT_ID}/branches/{branch}").wait()
#         print(f"✓ Deleted {branch}")
#     except Exception as e:
#         print(f"  {branch}: {e}")

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
# MAGIC | **Agentic Memory** | `labs/agentic-memory/` | Persistent AI agent memory with session/message storage |
# MAGIC | **Online Feature Store** | `labs/online-feature-store/` | Real-time ML feature serving powered by Lakebase Autoscaling |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |
