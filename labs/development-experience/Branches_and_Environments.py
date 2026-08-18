# Databricks notebook source
# MAGIC %md
# MAGIC # Branches & Environments
# MAGIC
# MAGIC **Path:** Development Experience &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase feature:** Copy-on-write database branching
# MAGIC
# MAGIC In this notebook you will:
# MAGIC 1. List existing branches on your project
# MAGIC 2. Create an isolated development branch
# MAGIC 3. Make schema changes on the branch without affecting production
# MAGIC 4. Inspect the branch and clean up
# MAGIC
# MAGIC **Run `00_Setup_Lakebase_Project` first.** Connections use your schema via `search_path`; SQL below uses unqualified names.
# MAGIC
# MAGIC **Docs:** [Branches](https://docs.databricks.com/aws/en/oltp/projects/branches) |
# MAGIC [Manage branches](https://docs.databricks.com/aws/en/oltp/projects/manage-branches)

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "protobuf>=5.29.5,<6" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

import time
from databricks.sdk.service.postgres import Branch, BranchSpec, Duration
show_app_link("branches", "Branch Manager")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. List Branches
# MAGIC Every project starts with a `production` branch (the default).

# COMMAND ----------

branches = list(w.postgres.list_branches(parent=f"projects/{PROJECT_ID}"))
for b in branches:
    bid = b.name.split("/")[-1]
    default = " (default)" if getattr(b.status, "default", False) else ""
    protected = " (protected)" if getattr(b.status, "is_protected", False) else ""
    print(f"  {bid}{default}{protected}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create a Development Branch
# MAGIC
# MAGIC This creates an instant, isolated copy of the production database.
# MAGIC The copy uses **copy-on-write** storage — no data is duplicated until
# MAGIC you make changes. We set a 24-hour TTL so it auto-deletes.

# COMMAND ----------

DEV_BRANCH = "lab-dev-01"

try:
    result = w.postgres.create_branch(
        parent=f"projects/{PROJECT_ID}",
        branch=Branch(
            spec=BranchSpec(
                source_branch=f"projects/{PROJECT_ID}/branches/production",
                ttl=Duration(seconds=86400),  # 24 hours
            )
        ),
        branch_id=DEV_BRANCH,
    ).wait()
    print(f"✓ Branch created: {result.name}")
except Exception as e:
    if "already exists" in str(e).lower():
        print(f"Branch {DEV_BRANCH} already exists — continuing")
    else:
        raise

show_view_link(
    f"View the '{DEV_BRANCH}' branch you just created in Lakebase",
    lakebase_project_url(branch=DEV_BRANCH),
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Connect to the Dev Branch
# MAGIC Each branch has its own compute endpoint. Let's connect and make
# MAGIC schema changes that are **completely isolated from production**.

# COMMAND ----------

print("Waiting for dev branch endpoint to activate...")
wait_for_endpoint(DEV_BRANCH)
conn = get_connection(DEV_BRANCH)
print("✓ Connected to dev branch")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Make Changes on the Dev Branch
# MAGIC Add a `reviews` table — this only exists on the dev branch.

# COMMAND ----------

with conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            review_id SERIAL PRIMARY KEY,
            product_id INTEGER REFERENCES products(product_id),
            rating INTEGER CHECK (rating BETWEEN 1 AND 5),
            comment TEXT,
            reviewer VARCHAR(100),
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        INSERT INTO reviews (product_id, rating, comment, reviewer)
        SELECT * FROM (VALUES
            (1, 5, 'Great sound quality!', 'alice'),
            (1, 4, 'Good ANC, comfortable fit', 'bob'),
            (2, 5, 'Best keyboard I have ever used', 'charlie'),
            (3, 4, 'Clear explanations, useful recipes', 'diana')
        ) AS seed(product_id, rating, comment, reviewer)
        WHERE NOT EXISTS (SELECT 1 FROM reviews LIMIT 1)
    """)
conn.commit()
print("✓ Reviews table created and seeded on dev branch")

show_view_link(
    f"View the reviews table on the '{DEV_BRANCH}' branch in Lakebase",
    lakebase_tables_url(DEV_BRANCH),
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Verify Isolation
# MAGIC The reviews table exists on `lab-dev-01` but **not** on `production`.

# COMMAND ----------

from psycopg.rows import dict_row

with conn.cursor(row_factory=dict_row) as cur:
    cur.execute("SELECT count(*) as cnt FROM reviews")
    print(f"Dev branch — reviews count: {cur.fetchone()['cnt']}")

prod_conn = get_connection("production")
with prod_conn.cursor() as cur:
    try:
        cur.execute("SELECT 1 FROM reviews LIMIT 1")
        print("Production — reviews table exists (unexpected)")
    except Exception:
        print("Production — reviews table does NOT exist (expected!)")
prod_conn.close()

print("\n✓ Branch isolation confirmed — changes on dev do not affect production")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Clean Up (Optional)
# MAGIC Delete the dev branch when you're done. Or leave it — the 24h TTL
# MAGIC will auto-delete it.

# COMMAND ----------

# UNCOMMENT TO DELETE NOW:
# conn.close()
# w.postgres.delete_branch(name=f"projects/{PROJECT_ID}/branches/{DEV_BRANCH}").wait()
# print(f"✓ Branch {DEV_BRANCH} deleted")

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC Try `Autoscaling_and_Compute` in this folder, or continue to another lab path:
# MAGIC
# MAGIC | Path | Folder | What You'll Learn |
# MAGIC |------|--------|-------------------|
# MAGIC | **Data Operations** | `labs/data-operations/` | CRUD, JSONB queries, array operators, audit triggers, transactions |
# MAGIC | **Reverse ETL** | `labs/reverse-etl/` | Sync Delta Lake tables into Lakebase for low-latency serving |
# MAGIC | **Observability** | `labs/observability/` | pg_stat views, index analysis, connection monitoring |
# MAGIC | **Authentication** | `labs/authentication/` | OAuth tokens, two-layer permissions, role grants |
# MAGIC | **Backup & Recovery** | `labs/backup-recovery/` | Checkpoint branches, snapshots, point-in-time restore |
# MAGIC | **Agentic Memory** | `labs/agentic-memory/` | Persistent AI agent memory with session/message storage |
# MAGIC | **Online Feature Store** | `labs/online-feature-store/` | Real-time ML feature serving powered by Lakebase Autoscaling |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |
