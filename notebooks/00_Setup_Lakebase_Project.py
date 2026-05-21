# Databricks notebook source
# MAGIC %md
# MAGIC # 00 — Set Up Your Lakebase Autoscaling Project
# MAGIC
# MAGIC This notebook creates your Lakebase Autoscaling project, waits for the
# MAGIC endpoint to become active, and seeds a per-user schema with sample data.
# MAGIC
# MAGIC **Run this notebook once** before starting any of the workshop labs.
# MAGIC
# MAGIC ### What gets created
# MAGIC | Resource | Details |
# MAGIC |----------|---------|
# MAGIC | **Project** | `lakebase-lab-<your-username>` |
# MAGIC | **Branch** | `production` (auto-created, default) |
# MAGIC | **Compute** | Autoscaling endpoint (0.5+ CU) |
# MAGIC | **Schema** | `lakebase_lab_<your_username>` with 6 tables: products, events, agent_sessions, agent_messages, agent_memory_store, audit_log |
# MAGIC | **Sample data** | 8 products with JSONB metadata, array tags, and audit triggers |

# COMMAND ----------

# MAGIC %md
# MAGIC ## Lakebase Architecture
# MAGIC
# MAGIC Lakebase Autoscaling is Databricks' fully managed **PostgreSQL** service
# MAGIC for operational (OLTP) workloads. It runs inside your Databricks workspace
# MAGIC and is governed by Unity Catalog.
# MAGIC
# MAGIC ### Resource Hierarchy
# MAGIC
# MAGIC ```
# MAGIC Databricks Workspace
# MAGIC └── Lakebase Project (top-level container)
# MAGIC     └── Branch(es) (isolated database environments, like Git branches)
# MAGIC         ├── Compute Endpoint (autoscaling PostgreSQL server, 0.5–112 CU)
# MAGIC         ├── Database: databricks_postgres (default)
# MAGIC         │   └── Schema(s) → Tables, indexes, triggers, functions
# MAGIC         └── Roles (mapped to Databricks users / Service Principals)
# MAGIC ```
# MAGIC
# MAGIC ### Key Capabilities
# MAGIC
# MAGIC | Capability | Details |
# MAGIC |------------|---------|
# MAGIC | **Autoscaling Compute** | 0.5–112 CU (~1–224 GB RAM), scales based on load |
# MAGIC | **Scale-to-Zero** | Non-production branches suspend after inactivity |
# MAGIC | **Copy-on-Write Branching** | Instant isolated database clones for dev/test/CI |
# MAGIC | **Point-in-Time Recovery** | Restore to any moment within the configured window (up to 35 days) |
# MAGIC | **OAuth Authentication** | Token-based auth via Databricks SDK (1-hour token TTL) |
# MAGIC | **Reverse ETL** | Sync Delta Lake tables into PostgreSQL via synced tables |
# MAGIC | **Unity Catalog Integration** | Projects and access governed by workspace IAM |
# MAGIC
# MAGIC **Docs:** [What is Lakebase Autoscaling?](https://docs.databricks.com/aws/en/oltp/projects/about) |
# MAGIC [Get started with Lakebase](https://docs.databricks.com/aws/en/oltp/projects/get-started)
# MAGIC
# MAGIC ### How It Fits in the Databricks Platform
# MAGIC
# MAGIC ![Lakebase integration with Databricks services](../docs/images/lakebase-architecture.png)
# MAGIC
# MAGIC - **Delta Lake** stores your analytical data (OLAP)
# MAGIC - **Lakebase** serves operational data at low latency (OLTP)
# MAGIC - **Synced Tables** push lakehouse data into Lakebase for low-latency serving
# MAGIC - **Lakehouse Sync** *(Beta)* streams Lakebase changes back into Delta with CDC + SCD Type 2
# MAGIC - **Databricks Apps**, **AI agents**, and **Feature Store** all connect to Lakebase as a backend
# MAGIC
# MAGIC *Source: [What is Lakebase Autoscaling?](https://docs.databricks.com/aws/en/oltp/projects/about)*

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Configure
# MAGIC The project ID is derived from your username automatically.
# MAGIC Only change this if you want a custom name.

# COMMAND ----------

import re
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
user_email = w.current_user.me().user_name

def sanitize(email):
    name = email.split("@")[0]
    name = re.sub(r"[^a-z0-9-]", "-", name.lower())
    return re.sub(r"-+", "-", name).strip("-")

PROJECT_ID = f"lakebase-lab-{sanitize(user_email)}"
PG_SCHEMA  = f"lakebase_lab_{sanitize(user_email).replace('-', '_')}"
PG_VERSION = "17"

print(f"User:       {user_email}")
print(f"Project ID: {PROJECT_ID}")
print(f"PG Schema:  {PG_SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Create the Lakebase Project
# MAGIC This creates the project and waits for the production endpoint to be ready.
# MAGIC Takes 1-3 minutes.

# COMMAND ----------

from databricks.sdk.service.postgres import Project, ProjectSpec
import time

try:
    existing = w.postgres.get_project(name=f"projects/{PROJECT_ID}")
    print(f"Project already exists: {existing.name}")
    print(f"Display name: {existing.status.display_name}")
except Exception:
    print(f"Creating project: {PROJECT_ID} ...")
    operation = w.postgres.create_project(
        project=Project(
            spec=ProjectSpec(
                display_name=f"Lakebase Workshop: {PROJECT_ID}",
                pg_version=PG_VERSION,
            )
        ),
        project_id=PROJECT_ID,
    )
    result = operation.wait()
    print(f"✓ Project created: {result.name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Wait for the Endpoint
# MAGIC The production branch gets a compute endpoint automatically. We need to
# MAGIC wait for it to become `ACTIVE` before we can connect.

# COMMAND ----------

print("Waiting for production endpoint to become active...")

endpoint = None
for attempt in range(90):
    try:
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{PROJECT_ID}/branches/production"
        ))
        if endpoints:
            ep = w.postgres.get_endpoint(name=endpoints[0].name)
            state = str(getattr(ep.status, "current_state", ""))
            if "ACTIVE" in state.upper():
                endpoint = ep
                print(f"✓ Endpoint is active!")
                print(f"  Host: {ep.status.hosts.host}")
                print(f"  Name: {ep.name}")
                break
            print(f"  State: {state} (attempt {attempt + 1})...")
    except Exception as e:
        print(f"  Waiting... ({e})")
    time.sleep(5)

if not endpoint:
    raise TimeoutError("Endpoint did not become active within 7.5 minutes. Check the Lakebase UI.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Connect and Seed the Schema
# MAGIC Creates 6 tables, indexes, audit triggers, and inserts 8 sample products
# MAGIC in a per-user schema (`lakebase_lab_<your_username>`).

# COMMAND ----------

import psycopg

host = endpoint.status.hosts.host
cred = w.postgres.generate_database_credential(endpoint=endpoint.name)
username = user_email

params = {"host": host, "dbname": "databricks_postgres", "user": username, "password": cred.token, "sslmode": "require"}
conn = psycopg.connect(**params)
print(f"✓ Connected to Lakebase")

# COMMAND ----------

import os

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
project_root = os.path.dirname(os.path.dirname(f"/Workspace{notebook_path}"))
seed_path = os.path.join(project_root, "bootstrap", "seed.sql")

with open(seed_path) as f:
    SEED_SQL = f.read().replace("{schema}", PG_SCHEMA)

print(f"Loaded seed SQL from: bootstrap/seed.sql ({len(SEED_SQL)} chars)")
print(f"Target schema: {PG_SCHEMA}")

with conn.cursor() as cur:
    cur.execute(SEED_SQL)
conn.commit()
print(f"✓ Schema {PG_SCHEMA} created and seeded")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Verify

# COMMAND ----------

from psycopg.rows import dict_row

cred = w.postgres.generate_database_credential(endpoint=endpoint.name)
params["password"] = cred.token

with psycopg.connect(**params, row_factory=dict_row) as verify_conn:
    with verify_conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name", [PG_SCHEMA])
        tables = [r["table_name"] for r in cur.fetchall()]
        print(f"Tables in {PG_SCHEMA} schema: {tables}")

        cur.execute(f"SELECT count(*) as cnt FROM {PG_SCHEMA}.products")
        cnt = cur.fetchone()["cnt"]
        print(f"Products seeded: {cnt}")

        cur.execute("SELECT version()")
        ver = cur.fetchone()["version"]
        print(f"PostgreSQL: {ver}")

conn.close()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6: Grant the Lab Console App Access
# MAGIC
# MAGIC The shared Lab Console app uses a **Service Principal** (SP) to connect to
# MAGIC every participant's Lakebase project. This step creates a PostgreSQL role
# MAGIC for the SP and grants it access to your schema.
# MAGIC
# MAGIC This is required because:
# MAGIC - The app's SP credentials have the `postgres` OAuth scope (forwarded user tokens do not)
# MAGIC - Each user must explicitly grant the SP access to their project/schema
# MAGIC - The SP connects as itself, but routes queries to your schema based on your email

# COMMAND ----------

app_name = "lakebase-lab-console"
try:
    app_info = w.apps.get(name=app_name)
    sp_id = getattr(app_info, 'effective_service_principal_client_id', None) or app_info.service_principal_client_id
    print(f"App: {app_name}")
    print(f"SP Client ID: {sp_id}")
except Exception as e:
    print(f"⚠ Could not look up app '{app_name}': {e}")
    print("  If the app hasn't been deployed yet, you can run this step later")
    print("  from the App Deployment lab (labs/app-deployment/).")
    sp_id = None

# COMMAND ----------

if sp_id:
    cred = w.postgres.generate_database_credential(endpoint=endpoint.name)
    params["password"] = cred.token
    grant_conn = psycopg.connect(**params)

    with grant_conn.cursor() as cur:
        # The databricks_auth extension provides databricks_create_role().
        # It's per-database and idempotent — safe to run on every setup.
        cur.execute("CREATE EXTENSION IF NOT EXISTS databricks_auth")
        print("✓ databricks_auth extension ready")

        try:
            cur.execute(f"SELECT databricks_create_role('{sp_id}', 'service_principal')")
            print(f"✓ Created OAuth role for SP: {sp_id}")
        except Exception as e:
            if 'already exists' in str(e):
                grant_conn.rollback()
                print(f"✓ OAuth role already exists for SP: {sp_id}")
            else:
                raise

        cur.execute(f'GRANT ALL ON SCHEMA {PG_SCHEMA} TO "{sp_id}"')
        cur.execute(f'GRANT ALL ON ALL TABLES IN SCHEMA {PG_SCHEMA} TO "{sp_id}"')
        cur.execute(f'GRANT ALL ON ALL SEQUENCES IN SCHEMA {PG_SCHEMA} TO "{sp_id}"')
        cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {PG_SCHEMA} GRANT ALL ON TABLES TO "{sp_id}"')
        cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {PG_SCHEMA} GRANT ALL ON SEQUENCES TO "{sp_id}"')
        print(f"✓ Granted SP access to schema: {PG_SCHEMA}")

    grant_conn.commit()
    grant_conn.close()
else:
    print("Skipping SP grants (app not found). Run this step later from the App Deployment lab.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✓ Setup Complete!
# MAGIC
# MAGIC Your Lakebase project is ready. The shared **Lab Console** app will
# MAGIC automatically connect to your project when you log in.
# MAGIC
# MAGIC The SP grant above allows the app to query your data on your behalf.

# COMMAND ----------

print("=" * 60)
print("  WORKSHOP CONFIGURATION")
print("=" * 60)
print(f"  Project ID:    {PROJECT_ID}")
print(f"  Endpoint:      {endpoint.name}")
print(f"  Host:          {endpoint.status.hosts.host}")
print(f"  Database:      databricks_postgres")
print(f"  Schema:        {PG_SCHEMA}")
print(f"  Username:      {user_email}")
if sp_id:
    print(f"  App SP:        {sp_id} (granted)")
print("=" * 60)
print()
print("  Open the Lab Console app (Compute → Apps → lakebase-lab-console)")
print("  to explore your data. The app routes each user to their own")
print("  Lakebase project automatically.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC Your Lakebase project is ready. Pick any lab path below — they're ordered from
# MAGIC foundational to advanced, but each one is independent. Start wherever interests you most.
# MAGIC
# MAGIC | | Path | Folder | What You'll Learn |
# MAGIC |---|------|--------|-------------------|
# MAGIC | 1 | **Data Operations** | `labs/data-operations/` | CRUD, JSONB queries, array operators, audit triggers, transactions |
# MAGIC | 2 | **Reverse ETL** | `labs/reverse-etl/` | Sync Delta Lake tables into Lakebase for low-latency serving |
# MAGIC | 3 | **Lakehouse Sync** *(Beta)* | `labs/lakehouse-sync/` | Sync Lakebase → Unity Catalog Delta with CDC + SCD Type 2 (UI-only) |
# MAGIC | 4 | **Development Experience** | `labs/development-experience/` | Git-like branching, autoscaling compute, scale-to-zero |
# MAGIC | 5 | **Observability** | `labs/observability/` | pg_stat views, index analysis, connection monitoring |
# MAGIC | 6 | **Authentication** | `labs/authentication/` | OAuth tokens, two-layer permissions, role grants |
# MAGIC | 7 | **Backup & Recovery** | `labs/backup-recovery/` | Point-in-time recovery, branch snapshots, instant restore |
# MAGIC | 8 | **Agentic Memory** | `labs/agentic-memory/` | Persistent AI agent memory with session/message storage |
# MAGIC | 9 | **Online Feature Store** | `labs/online-feature-store/` | Real-time ML feature serving powered by Lakebase |
# MAGIC | 10 | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |

# COMMAND ----------

# MAGIC %md
# MAGIC ## (Optional) Clean Up
# MAGIC
# MAGIC Uncomment and run the cell below to delete your project when you're done.
# MAGIC **This permanently deletes all branches and data.**

# COMMAND ----------

# UNCOMMENT TO DELETE:
# w.postgres.delete_project(name=f"projects/{PROJECT_ID}")
# print(f"Project {PROJECT_ID} deletion initiated.")
