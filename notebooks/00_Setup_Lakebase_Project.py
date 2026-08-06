# Databricks notebook source
# MAGIC %md
# MAGIC # 00 — Set Up Your Lakebase Project
# MAGIC
# MAGIC This notebook creates your Lakebase project, waits for the
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
# MAGIC Lakebase is Databricks' fully managed **PostgreSQL** service
# MAGIC for operational (OLTP) workloads. It runs inside your Databricks workspace
# MAGIC and is governed by Unity Catalog.
# MAGIC
# MAGIC > **It's all one Lakebase now.** Databricks has unified its managed Postgres under a single
# MAGIC > **Lakebase** offering (the earlier "Provisioned" instances were upgraded to the unified
# MAGIC > platform by Jul 31, 2026). You'll still see **"Autoscaling"** in doc URLs and the SDK
# MAGIC > (`w.postgres.*`, the `oltp/projects` surface) — that's the API surface this workshop uses.
# MAGIC
# MAGIC ### Resource Hierarchy
# MAGIC
# MAGIC ```
# MAGIC Databricks Workspace
# MAGIC └── Lakebase Project (top-level container)
# MAGIC     └── Branch(es) (isolated database environments, like Git branches)
# MAGIC         ├── Compute Endpoint (autoscaling PostgreSQL server, up to 64 CU)
# MAGIC         ├── Database: databricks_postgres (default)
# MAGIC         │   └── Schema(s) → Tables, indexes, triggers, functions
# MAGIC         └── Roles (mapped to Databricks users / Service Principals)
# MAGIC ```
# MAGIC
# MAGIC ### Key Capabilities
# MAGIC
# MAGIC | Capability | Details |
# MAGIC |------------|---------|
# MAGIC | **Autoscaling Compute** | Autoscales up to 64 CU (~2 GB RAM/CU, max−min spread ≤ 16 CU); larger fixed-size computes above 64 CU |
# MAGIC | **Scale-to-Zero** | Every branch (incl. production) suspends after inactivity; enabled by default with a 24h timeout (60s–7d) |
# MAGIC | **Copy-on-Write Branching** | Instant isolated database clones for dev/test/CI |
# MAGIC | **Point-in-Time Recovery** | Restore to any moment within the configured window (2–30 days, default 7) |
# MAGIC | **OAuth Authentication** | Token-based auth via Databricks SDK (1-hour token TTL) |
# MAGIC | **Synced Tables** | Sync Unity Catalog Delta tables into Postgres for low-latency serving |
# MAGIC | **Unity Catalog Integration** | Projects and access governed by workspace IAM |
# MAGIC
# MAGIC > **Postgres version:** this workshop provisions **PostgreSQL 17** (the current default).
# MAGIC > **PostgreSQL 18 is also supported** — set `pg_version="18"` at create time if you want it.
# MAGIC
# MAGIC **Docs:** [What is Lakebase?](https://docs.databricks.com/aws/en/oltp/projects/about) |
# MAGIC [Get started with Lakebase](https://docs.databricks.com/aws/en/oltp/projects/get-started)
# MAGIC
# MAGIC ### How It Fits in the Databricks Platform
# MAGIC
# MAGIC ![Lakebase integration with Databricks services](../docs/images/lakebase-architecture.png)
# MAGIC
# MAGIC - **Delta Lake** stores your analytical data (OLAP)
# MAGIC - **Lakebase** serves operational data at low latency (OLTP)
# MAGIC - **Synced Tables** push lakehouse data into Lakebase for low-latency serving
# MAGIC - **Lakebase CDF** *(Public Preview)* streams Lakebase changes back into Delta as a CDC change history
# MAGIC - **Applications**, **AI agents**, and **ML models** all connect to Lakebase as a backend
# MAGIC
# MAGIC *Source: [What is Lakebase?](https://docs.databricks.com/aws/en/oltp/projects/about)*

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
PG_VERSION = "17"  # 17 is the current default; "18" is also supported

print(f"User:       {user_email}")
print(f"Project ID: {PROJECT_ID}")
print(f"PG Schema:  {PG_SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Create the Lakebase Project
# MAGIC This creates the project and waits for the production endpoint to be ready.
# MAGIC Typically takes 2-3 minutes (occasionally longer).

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
# MAGIC The production branch gets a compute endpoint automatically. We wait for it
# MAGIC to finish provisioning — `ACTIVE`, or `IDLE` if it has scaled to zero and is
# MAGIC waiting for a connection to wake it.

# COMMAND ----------

print("Waiting for production endpoint to become available...")

# IDLE counts as ready: a scaled-to-zero endpoint only wakes when a client connects,
# so waiting for ACTIVE would time out on a healthy endpoint.
READY_STATES = ("ACTIVE", "IDLE", "DEGRADED")

endpoint = None
for attempt in range(90):
    try:
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{PROJECT_ID}/branches/production"
        ))
        if endpoints:
            ep = w.postgres.get_endpoint(name=endpoints[0].name)
            state = str(getattr(ep.status, "current_state", ""))
            if any(ready in state.upper() for ready in READY_STATES):
                endpoint = ep
                print(f"✓ Endpoint is available ({state.split('.')[-1]})")
                print(f"  Host: {ep.status.hosts.host}")
                print(f"  Name: {ep.name}")
                break
            print(f"  State: {state} (attempt {attempt + 1})...")
    except Exception as e:
        print(f"  Waiting... ({e})")
    time.sleep(5)

if not endpoint:
    raise TimeoutError("Endpoint is still provisioning after 7.5 minutes. Check the Lakebase UI.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Connect and Seed the Schema
# MAGIC Creates 6 tables, indexes, audit triggers, and inserts 8 sample products
# MAGIC in a per-user schema (`lakebase_lab_<your_username>`).

# COMMAND ----------

import psycopg
import time

host = endpoint.status.hosts.host
username = user_email


def connect_lakebase(**extra):
    """Connect with a fresh credential, retrying while the endpoint finishes waking.

    An endpoint that just reported ACTIVE can still stall a TLS handshake for a few
    seconds. connect_timeout turns that stall into an error we can retry instead of
    a hang that takes the Python kernel down with it.
    """
    global params
    last_err = None
    for attempt in range(3):
        cred = w.postgres.generate_database_credential(endpoint=endpoint.name)
        params = {"host": host, "dbname": "databricks_postgres", "user": username,
                  "password": cred.token, "sslmode": "require", "connect_timeout": 15}
        try:
            return psycopg.connect(**params, **extra)
        except psycopg.OperationalError as e:
            last_err = e
            print(f"  Connection attempt {attempt + 1} failed ({e}); retrying...")
            time.sleep(3)
    raise last_err


conn = connect_lakebase()
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

with connect_lakebase(row_factory=dict_row) as verify_conn:
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
# MAGIC every participant's Lakebase project. Lakebase has two independent permission
# MAGIC layers, and the SP needs a grant in each one:
# MAGIC
# MAGIC | Layer | Grant | Enables |
# MAGIC |-------|-------|---------|
# MAGIC | **Project ACL** (control plane) | `CAN_MANAGE` on your project | Branch Manager, Compute tabs |
# MAGIC | **PostgreSQL** (data plane) | Role + schema `GRANT` | Data Explorer, SQL playground |
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

# MAGIC %md
# MAGIC ### 6a. Project ACL — control plane
# MAGIC
# MAGIC `CAN_MANAGE` on the project lets the app create and delete branches and manage
# MAGIC computes on your behalf. Without it, the Branch Manager tab fails with
# MAGIC *"The user is not authorized to make the request... assign the user `<sp_id>`
# MAGIC 'Can Manage' for Database project"*.
# MAGIC
# MAGIC Attaching the app's `postgres` resource does **not** grant this — it only covers
# MAGIC the data plane.

# COMMAND ----------

from databricks.sdk.service.iam import AccessControlRequest, PermissionLevel

if sp_id:
    # PATCH semantics: additive, idempotent, and leaves your own CAN_MANAGE intact.
    w.permissions.update(
        request_object_type="database-projects",
        request_object_id=PROJECT_ID,
        access_control_list=[
            AccessControlRequest(
                service_principal_name=sp_id,
                permission_level=PermissionLevel.CAN_MANAGE,
            )
        ],
    )
    print(f"✓ Granted CAN_MANAGE on project '{PROJECT_ID}' to SP: {sp_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 6b. PostgreSQL role and schema grants — data plane
# MAGIC
# MAGIC > **Synced tables need one more grant.** This step covers the **Postgres** data plane
# MAGIC > for your seed schema. **Synced tables** (Reverse ETL / Feature Store labs) live in a
# MAGIC > **Unity Catalog** schema (`main.<your_schema>`) that doesn't exist yet, and the app
# MAGIC > discovers them via Unity Catalog **as its SP**. So those labs include a small extra
# MAGIC > step that grants the app SP `USE CATALOG` + `USE SCHEMA` + `SELECT` on your UC schema
# MAGIC > (see `labs/reverse-etl/` §5a). Without it, synced tables won't appear on the app's
# MAGIC > Synced Tables page.

# COMMAND ----------

if sp_id:
    grant_conn = connect_lakebase()

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
# MAGIC | 3 | **Lakehouse Sync** *(Public Preview)* | `labs/lakehouse-sync/` | Sync Lakebase → Unity Catalog Delta via Lakebase Change Data Feed (UI-configured) |
# MAGIC | 4 | **Development Experience** | `labs/development-experience/` | Git-like branching, autoscaling compute, scale-to-zero |
# MAGIC | 5 | **Observability** | `labs/observability/` | pg_stat views, index analysis, connection monitoring |
# MAGIC | 6 | **Authentication** | `labs/authentication/` | OAuth tokens, two-layer permissions, role grants |
# MAGIC | 7 | **Backup & Recovery** | `labs/backup-recovery/` | Point-in-time recovery, branch snapshots, instant restore |
# MAGIC | 8 | **Agentic Memory** | `labs/agentic-memory/` | Persistent AI agent memory with session/message storage |
# MAGIC | 9 | **Online Feature Store** | `labs/online-feature-store/` | Real-time ML feature serving powered by Lakebase |
# MAGIC | 10 | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |
# MAGIC | 11 | **Data API** | `labs/data-api/` | PostgREST REST access, OAuth bearer tokens, and row-level security |
# MAGIC | 12 | **Lakebase Search** *(Beta)* | `labs/lakebase-search/` | Vector + keyword search with hybrid RRF ranking |

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
