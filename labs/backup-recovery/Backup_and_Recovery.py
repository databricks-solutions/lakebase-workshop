# Databricks notebook source
# MAGIC %md
# MAGIC # Backup & Recovery
# MAGIC
# MAGIC **Path:** Backup & Recovery &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase features:** Checkpoint branches, snapshots, point-in-time restore (PITR)
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. Understand Lakebase's built-in backup architecture
# MAGIC 2. Create a **checkpoint branch** to preserve a known-good state
# MAGIC 3. Simulate a data loss scenario on a development branch
# MAGIC 4. Recover the data by creating a new branch from the checkpoint
# MAGIC 5. See how **snapshots** — the managed backup feature — differ from checkpoint branches
# MAGIC 6. Learn about point-in-time restore (PITR)
# MAGIC
# MAGIC > **Terminology, because it matters here:** this notebook's hands-on exercise uses
# MAGIC > **branches** as checkpoints, not Lakebase **Snapshots**. Both give you a restore
# MAGIC > point, but they are different objects: a checkpoint branch is a copy-on-write branch
# MAGIC > you create yourself (SDK/CLI/UI), while a Snapshot is a managed backup of a *root*
# MAGIC > branch created from **Backup & Restore** in the Lakebase App, with schedules,
# MAGIC > retention, and its own storage billing. Section 5 covers Snapshots. The exercise
# MAGIC > uses branches because they are scriptable — Snapshots have no SDK or CLI surface yet.
# MAGIC
# MAGIC **Run `00_Setup_Lakebase_Project` first.** Table queries use unqualified names; your schema is set via `search_path` in `_setup`.
# MAGIC
# MAGIC **Docs:** [Backup and restore methods](https://docs.databricks.com/aws/en/oltp/projects/backup-methods) |
# MAGIC [Snapshots](https://docs.databricks.com/aws/en/oltp/projects/snapshots) |
# MAGIC [Point-in-time restore](https://docs.databricks.com/aws/en/oltp/projects/point-in-time-restore) |
# MAGIC [Branches](https://docs.databricks.com/aws/en/oltp/projects/branches)

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "protobuf>=5.29.5,<6" --quiet

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
# MAGIC | **Point-in-time restore** | Create a new root branch from any second within the restore window (up to 30 days) | Accidental data corruption or deletion |
# MAGIC | **Snapshots** | Managed point-in-time capture of a **root** branch, taken manually or on a schedule | Regular backups; pre-migration restore point |
# MAGIC | **Checkpoint branches** | A copy-on-write branch you create yourself as a named restore point | Scripted safety net around a migration |
# MAGIC | **Branch TTL** | Branches auto-delete after a configurable time | Dev/test cleanup |
# MAGIC
# MAGIC **You do NOT need to configure backups** — continuous protection is always on.
# MAGIC You only set the *history window* at the project level.
# MAGIC
# MAGIC > **Storage billing (effective Jun 1, 2026):** recovery is protected by default, but the
# MAGIC > storage it uses is billed. Lakebase bills three storage components separately:
# MAGIC > **(1) primary data**, **(2) PITR history** (WAL retained for your history window), and
# MAGIC > **(3) snapshots**. Manual snapshots bill as full snapshots; scheduled ones bill full for
# MAGIC > the first and incremental thereafter. Branches bill as primary data only for what
# MAGIC > diverges from their parent. Right-size the window and clean up what you no longer need.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create a Checkpoint Branch
# MAGIC
# MAGIC Before making risky changes (schema migration, bulk delete, etc.),
# MAGIC create a branch as a **named checkpoint**. This is instant and
# MAGIC costs no additional storage until data diverges.
# MAGIC
# MAGIC This is not the same thing as a Lakebase **Snapshot** (section 5) — it is a
# MAGIC branch you manage yourself. It works from any branch, is scriptable, and is
# MAGIC what you'd reach for in CI or a migration script.
# MAGIC
# MAGIC > **No TTL on a checkpoint:** the checkpoint branch must be non-expiring, because
# MAGIC > Lakebase does not allow creating child branches from a branch that has an
# MAGIC > expiration — and recovery works by branching off the checkpoint. Every branch
# MAGIC > must declare an expiration policy, so pass `no_expiry=True` explicitly rather
# MAGIC > than omitting `ttl`. Delete checkpoint branches manually when no longer needed.

# COMMAND ----------

CHECKPOINT_BRANCH = "lab-checkpoint-pre-migration"
WORK_BRANCH = "lab-migration-test"
RECOVERY_BRANCH = "lab-recovered"


def _create_branch(branch_id, source_branch_id, *, ttl_seconds=None, no_expiry=False, recreate=False):
    """Create a branch, optionally deleting a leftover one first.

    The work/recovery branches intentionally end this lab in a damaged or
    one-off state. Reusing them on a second run (e.g. after a partial reset)
    would either skip the disaster demo or trip _setup's schema-repair warning
    when products is already gone — so those callers pass recreate=True.
    """
    name = f"projects/{PROJECT_ID}/branches/{branch_id}"
    if recreate:
        try:
            w.postgres.delete_branch(name=name).wait()
            print(f"  Removed leftover {branch_id} before recreating")
        except Exception as e:
            if "not found" not in str(e).lower() and "does not exist" not in str(e).lower():
                raise

    spec_kwargs = {"source_branch": f"projects/{PROJECT_ID}/branches/{source_branch_id}"}
    if no_expiry:
        spec_kwargs["no_expiry"] = True
    elif ttl_seconds is not None:
        spec_kwargs["ttl"] = Duration(seconds=ttl_seconds)

    try:
        result = w.postgres.create_branch(
            parent=f"projects/{PROJECT_ID}",
            branch=Branch(spec=BranchSpec(**spec_kwargs)),
            branch_id=branch_id,
        ).wait()
        print(f"✓ Branch created: {result.name}")
        show_view_link(
            f"View the '{branch_id}' branch in Lakebase",
            lakebase_project_url(branch=branch_id),
        )
        return result
    except Exception as e:
        if "already exists" in str(e).lower() and not recreate:
            print(f"Branch {branch_id} already exists — continuing")
            show_view_link(
                f"View the '{branch_id}' branch in Lakebase",
                lakebase_project_url(branch=branch_id),
            )
            return None
        raise


_create_branch(CHECKPOINT_BRANCH, "production", no_expiry=True)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Simulate a Risky Change
# MAGIC
# MAGIC Let's create a working branch, make changes, and then simulate
# MAGIC a "bad migration" that destroys data.

# COMMAND ----------

_create_branch(WORK_BRANCH, "production", ttl_seconds=86400, recreate=True)

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
# MAGIC ## 4. Recover from the Checkpoint
# MAGIC
# MAGIC The production branch is untouched (we did the damage on a work branch).
# MAGIC But if this *had* been production, here's how you'd recover: create a new
# MAGIC branch from the checkpoint, verify the data, then point your application at it.
# MAGIC Recovery is always "branch and re-point" in Lakebase — snapshots and PITR
# MAGIC restores work the same way, producing a new branch rather than modifying
# MAGIC the damaged one in place.

# COMMAND ----------

_create_branch(RECOVERY_BRANCH, CHECKPOINT_BRANCH, ttl_seconds=86400, recreate=True)

# COMMAND ----------

print("Waiting for recovery branch endpoint...")
wait_for_endpoint(RECOVERY_BRANCH)
recovery_conn = get_connection(RECOVERY_BRANCH)

with recovery_conn.cursor() as cur:
    cur.execute("SELECT count(*) AS cnt FROM products")
    count = cur.fetchone()['cnt']
    print(f"✓ Products on recovered branch: {count}")
    print("  Data is fully intact — recovered from the checkpoint branch!")

recovery_conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Snapshots — the managed backup feature
# MAGIC
# MAGIC What you just did in sections 2–4 was a **do-it-yourself checkpoint** built out of
# MAGIC branches. Lakebase also has a first-class **Snapshot**: a point-in-time capture of a
# MAGIC root branch's schema and data, created instantly and managed for you.
# MAGIC
# MAGIC | | Checkpoint branch (sections 2–4) | Snapshot |
# MAGIC |---|---|---|
# MAGIC | **What it is** | A copy-on-write branch you create and name | A managed backup object of a root branch |
# MAGIC | **How you create it** | SDK / CLI / UI (`create_branch`) | Lakebase App → **Backup & Restore** → *Create snapshot* |
# MAGIC | **Automation** | Whatever you script | Built-in daily / weekly / monthly backup schedules with retention |
# MAGIC | **Scope** | Any branch | **Root branches only** |
# MAGIC | **Limits** | Counts against your branch limits | 10 manual snapshots per project; scheduled ones are not capped by that limit |
# MAGIC | **Restoring** | You create a child branch from it (section 4) | *Restore* creates a new root branch named `branch_from_snapshot_<date>` |
# MAGIC | **Billing** | Storage for data that diverges from the parent | Billed as snapshot storage — manual = full, scheduled = full then incremental |
# MAGIC
# MAGIC ### Try it in the UI
# MAGIC
# MAGIC 1. Open your project in the Lakebase App and select **Backup & Restore**.
# MAGIC 2. Click **Create snapshot** to capture the current state of the root branch.
# MAGIC 3. Click **Edit schedule** to set up automated daily/weekly/monthly snapshots and retention.
# MAGIC 4. To restore, find a snapshot in the list and click **Restore** — Lakebase creates a new
# MAGIC    root branch with that data. Your current branch is left untouched, so you can connect to
# MAGIC    the new branch, verify the data, and only then re-point your application at it.
# MAGIC
# MAGIC > **Why this notebook uses branches instead:** snapshots are UI-driven today — there is no
# MAGIC > `snapshot` verb in the Postgres SDK or the `databricks postgres` CLI. Checkpoint branches
# MAGIC > are the scriptable equivalent, which is what you want inside a migration or CI job.
# MAGIC > Note that the **3 root branches per project** limit applies to every restore, since both
# MAGIC > snapshot restores and PITR restores produce a new root branch.
# MAGIC
# MAGIC **Docs:** [Snapshots](https://docs.databricks.com/aws/en/oltp/projects/snapshots)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Point-in-Time Recovery (PITR)
# MAGIC
# MAGIC A checkpoint or a snapshot only gets you back to a moment you thought to capture
# MAGIC in advance. PITR gets you back to *any* second in the restore window, including
# MAGIC the second before a mistake you didn't see coming.
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
# MAGIC ## 7. Best Practices
# MAGIC
# MAGIC | Scenario | Recommended Approach |
# MAGIC |----------|---------------------|
# MAGIC | **Before a scripted schema migration** | Create a checkpoint branch (instant; shares storage until data diverges) |
# MAGIC | **Before a manual/ad-hoc change in the UI** | Take a snapshot from Backup & Restore |
# MAGIC | **Routine backups** | Set a snapshot schedule on the root branch with a retention that matches your RPO |
# MAGIC | **Accidental DELETE/UPDATE** | PITR to the second before the mistake |
# MAGIC | **Testing destructive operations** | Create a work branch, test there, delete when done |
# MAGIC | **Compliance / audit retention** | Set the history window to its 30-day maximum at the project level |
# MAGIC | **Disaster recovery drill** | Periodically restore from a snapshot or PITR and verify data integrity |

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Clean Up (Optional)
# MAGIC
# MAGIC Delete the branches created in this notebook. Production is untouched.

# COMMAND ----------

# UNCOMMENT TO CLEAN UP:
# Delete child branches before their parent — RECOVERY_BRANCH is a child of
# CHECKPOINT_BRANCH, and a branch with children cannot be deleted.
# work_conn.close()
# for branch in [WORK_BRANCH, RECOVERY_BRANCH, CHECKPOINT_BRANCH]:
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
