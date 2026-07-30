# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy the Lab Console App
# MAGIC
# MAGIC **Path:** App Deployment &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase feature:** Full-stack app using Lakebase as the backend
# MAGIC
# MAGIC This notebook walks through the patterns for connecting a **Databricks App**
# MAGIC to **Lakebase** — including Service Principal authentication, OAuth credential
# MAGIC generation, token refresh, and schema-level access grants.
# MAGIC
# MAGIC Every code cell is a **reusable reference pattern** you can adapt for your
# MAGIC own applications.
# MAGIC
# MAGIC **Docs:** [Connect an application](https://docs.databricks.com/aws/en/oltp/projects/connect-application) |
# MAGIC [Databricks Apps tutorial](https://docs.databricks.com/aws/en/oltp/projects/tutorial-databricks-apps-autoscaling)
# MAGIC
# MAGIC **What the Lab Console includes:**
# MAGIC - Branch Manager — create/delete branches from the UI
# MAGIC - Autoscaling Dashboard — resize compute and monitor CU ranges
# MAGIC - Load Tester — generate synthetic traffic and stream live metrics
# MAGIC - Data Playground — CRUD operations, audit log viewer
# MAGIC - Reverse ETL — check synced table status
# MAGIC - API Tester — raw SQL execution against any branch
# MAGIC - Agent Memory — session/message management UI

# COMMAND ----------

# MAGIC %md
# MAGIC ## Architecture: SP Auth + Email Routing
# MAGIC
# MAGIC The Lab Console is deployed **once** by the workshop facilitator and shared
# MAGIC by all participants. When you open the app, it automatically connects to
# MAGIC **your** Lakebase project using the app's Service Principal.
# MAGIC
# MAGIC ### How it works
# MAGIC
# MAGIC ```
# MAGIC Browser (React Lab Console)
# MAGIC     |
# MAGIC     v
# MAGIC Databricks App Proxy
# MAGIC     |  (injects X-Forwarded-Email header)
# MAGIC     v
# MAGIC FastAPI Backend
# MAGIC     |
# MAGIC     +---> Read user email → derive project ID (lakebase-lab-<you>)
# MAGIC     |
# MAGIC     +---> App SP (WorkspaceClient) → generate DB credential for YOUR project
# MAGIC     |
# MAGIC     +---> psycopg → connect as SP to YOUR Lakebase project
# MAGIC     |         (search_path = your schema)
# MAGIC     v
# MAGIC Your Lakebase Project (lakebase-lab-<your-username>)
# MAGIC ```
# MAGIC
# MAGIC ### Key design decisions
# MAGIC
# MAGIC | Decision | Details |
# MAGIC |----------|---------|
# MAGIC | **SP authentication** | The app's Service Principal performs all SDK calls and DB connections — it has the required `postgres` OAuth scope (forwarded user tokens do not) |
# MAGIC | **Email-based routing** | The `X-Forwarded-Email` header determines which project/schema to connect to — each user sees only their own data |
# MAGIC | **Per-user SP grants** | Each user must grant the SP access to their project (done in setup notebook or below) |
# MAGIC | **Per-project credential caching** | DB credentials are cached for 45 min per project (tokens expire at 60 min) |
# MAGIC | **Graceful fallback** | If a user hasn't run `00_Setup`, the Dashboard shows a friendly setup prompt |
# MAGIC
# MAGIC ### Why SP auth instead of user token passthrough?
# MAGIC
# MAGIC Databricks Apps injects a forwarded user token (`x-forwarded-access-token`),
# MAGIC but this token **does not include the `postgres` OAuth scope**. Without it,
# MAGIC Lakebase SDK calls (`list_endpoints`, `generate_database_credential`) fail.
# MAGIC
# MAGIC The app's Service Principal gets the `postgres` scope automatically when a
# MAGIC Lakebase database resource is attached to the app via `app.yaml`. This is
# MAGIC why we use SP auth for all Lakebase operations.

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" --quiet

# COMMAND ----------

dbutils.library.restartPython()

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

print(f"User:       {user_email}")
print(f"Project ID: {PROJECT_ID}")
print(f"PG Schema:  {PG_SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Pattern 1: Look Up an App's Service Principal
# MAGIC
# MAGIC Every Databricks App has a dedicated Service Principal. When you attach a
# MAGIC Lakebase database resource to the app, the SP gets the `postgres` OAuth
# MAGIC scope and a PostgreSQL role is created for it automatically.
# MAGIC
# MAGIC **Use this pattern when:** You need to grant an app's SP access to a
# MAGIC specific schema or table in your Lakebase project.

# COMMAND ----------

app_name = "lakebase-lab-console"
app_info = w.apps.get(name=app_name)
sp_id = getattr(app_info, 'effective_service_principal_client_id', None) or app_info.service_principal_client_id

print(f"App:          {app_name}")
print(f"SP Client ID: {sp_id}")
print(f"SP Name:      {getattr(app_info, 'service_principal_name', 'N/A')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Pattern 2: Grant SP Access to a Schema
# MAGIC
# MAGIC Lakebase has **two permission layers**:
# MAGIC
# MAGIC 1. **Workspace (Unity Catalog)** — controls who can see/manage the project
# MAGIC 2. **Database (PostgreSQL)** — controls SQL-level access to schemas/tables
# MAGIC
# MAGIC When you attach a Lakebase resource to an app, the platform creates the SP's
# MAGIC PostgreSQL role and grants `CONNECT` + `CREATE` on the database. But you still
# MAGIC need to grant access to **your specific schema** and its tables.
# MAGIC
# MAGIC **Use this pattern when:** You want an app to read/write data in a schema
# MAGIC it didn't create itself.
# MAGIC
# MAGIC ```sql
# MAGIC -- The databricks_auth extension provides the databricks_create_role()
# MAGIC -- function. Each Postgres database needs its own copy of the extension.
# MAGIC CREATE EXTENSION IF NOT EXISTS databricks_auth;
# MAGIC
# MAGIC -- Create the SP's OAuth role (idempotent — safe to re-run)
# MAGIC SELECT databricks_create_role('<SP_CLIENT_ID>', 'service_principal');
# MAGIC
# MAGIC -- Grant schema-level access
# MAGIC GRANT ALL ON SCHEMA my_schema TO "<SP_CLIENT_ID>";
# MAGIC GRANT ALL ON ALL TABLES IN SCHEMA my_schema TO "<SP_CLIENT_ID>";
# MAGIC GRANT ALL ON ALL SEQUENCES IN SCHEMA my_schema TO "<SP_CLIENT_ID>";
# MAGIC ALTER DEFAULT PRIVILEGES IN SCHEMA my_schema GRANT ALL ON TABLES TO "<SP_CLIENT_ID>";
# MAGIC ALTER DEFAULT PRIVILEGES IN SCHEMA my_schema GRANT ALL ON SEQUENCES TO "<SP_CLIENT_ID>";
# MAGIC ```

# COMMAND ----------

import psycopg

endpoints = list(w.postgres.list_endpoints(
    parent=f"projects/{PROJECT_ID}/branches/production"
))
if not endpoints:
    raise RuntimeError(f"No endpoints found. Run 00_Setup_Lakebase_Project first.")

endpoint = w.postgres.get_endpoint(name=endpoints[0].name)
cred = w.postgres.generate_database_credential(endpoint=endpoints[0].name)

conn = psycopg.connect(
    host=endpoint.status.hosts.host,
    dbname="databricks_postgres",
    user=user_email,
    password=cred.token,
    sslmode="require",
)

with conn.cursor() as cur:
    # The databricks_auth extension provides databricks_create_role().
    # It's per-database and idempotent — safe to run on every setup.
    cur.execute("CREATE EXTENSION IF NOT EXISTS databricks_auth")
    print("✓ databricks_auth extension ready")

    try:
        cur.execute(f"SELECT databricks_create_role('{sp_id}', 'service_principal')")
        print(f"✓ Created OAuth role for SP: {sp_id}")
    except Exception as e:
        if 'already exists' in str(e):
            conn.rollback()
            print(f"✓ OAuth role already exists for SP: {sp_id}")
        else:
            raise

    cur.execute(f'GRANT ALL ON SCHEMA {PG_SCHEMA} TO "{sp_id}"')
    cur.execute(f'GRANT ALL ON ALL TABLES IN SCHEMA {PG_SCHEMA} TO "{sp_id}"')
    cur.execute(f'GRANT ALL ON ALL SEQUENCES IN SCHEMA {PG_SCHEMA} TO "{sp_id}"')
    cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {PG_SCHEMA} GRANT ALL ON TABLES TO "{sp_id}"')
    cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {PG_SCHEMA} GRANT ALL ON SEQUENCES TO "{sp_id}"')
    print(f"✓ Granted SP access to schema: {PG_SCHEMA}")

conn.commit()
conn.close()
print(f"\n✓ The Lab Console app can now access your Lakebase project.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Pattern 3: OAuth Credential Generation & Token Refresh
# MAGIC
# MAGIC Lakebase uses **OAuth tokens** instead of static passwords. Tokens expire
# MAGIC after **1 hour**, so your application must handle credential refresh.
# MAGIC
# MAGIC The pattern:
# MAGIC 1. Call `generate_database_credential()` to get a short-lived token
# MAGIC 2. Use the token as the PostgreSQL password
# MAGIC 3. Cache the token and refresh before it expires (recommended: refresh at 45 min)
# MAGIC
# MAGIC **Use this pattern when:** Building any long-running application that
# MAGIC connects to Lakebase.

# COMMAND ----------

import time

cred = w.postgres.generate_database_credential(endpoint=endpoint.name)

# Show only a short, non-reusable prefix. Treat the full token like a password:
# clear this cell's output before exporting or screen-sharing the notebook.
print(f"Token preview:  {cred.token[:12]}...")
print(f"Token length:   {len(cred.token)} characters")
print(f"Expires at:     {cred.expire_time}")
print(f"Generated at:   {time.strftime('%H:%M:%S')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Token Refresh Pattern (Python)
# MAGIC
# MAGIC Here's the pattern the Lab Console uses for credential caching with
# MAGIC automatic refresh. Adapt this for any Lakebase-connected application:
# MAGIC
# MAGIC ```python
# MAGIC import time, threading
# MAGIC from databricks.sdk import WorkspaceClient
# MAGIC
# MAGIC REFRESH_INTERVAL = 2700  # 45 minutes (tokens expire at 60 min)
# MAGIC
# MAGIC _cache = {}
# MAGIC _lock = threading.Lock()
# MAGIC
# MAGIC def get_db_credential(project_id, branch_id="production"):
# MAGIC     """Generate or return a cached database credential."""
# MAGIC     cache_key = f"{project_id}:{branch_id}"
# MAGIC
# MAGIC     with _lock:
# MAGIC         cached = _cache.get(cache_key)
# MAGIC         if cached:
# MAGIC             token, timestamp = cached
# MAGIC             if (time.time() - timestamp) < REFRESH_INTERVAL:
# MAGIC                 return token  # Still fresh
# MAGIC
# MAGIC     # Token expired or not cached — generate a new one
# MAGIC     w = WorkspaceClient()
# MAGIC     endpoints = list(w.postgres.list_endpoints(
# MAGIC         parent=f"projects/{project_id}/branches/{branch_id}"
# MAGIC     ))
# MAGIC     cred = w.postgres.generate_database_credential(
# MAGIC         endpoint=endpoints[0].name
# MAGIC     )
# MAGIC
# MAGIC     with _lock:
# MAGIC         _cache[cache_key] = (cred.token, time.time())
# MAGIC
# MAGIC     return cred.token
# MAGIC ```
# MAGIC
# MAGIC **Key points:**
# MAGIC - Cache tokens for 45 min (safe margin before 60-min expiry)
# MAGIC - Use a lock for thread safety in multi-threaded apps (FastAPI, Flask)
# MAGIC - Key the cache by `project_id:branch_id` so each branch gets its own token
# MAGIC - The `WorkspaceClient()` in a Databricks App uses SP auth automatically

# COMMAND ----------

# MAGIC %md
# MAGIC ### Demonstrating Token Refresh

# COMMAND ----------

cred_1 = w.postgres.generate_database_credential(endpoint=endpoint.name)
time.sleep(2)
cred_2 = w.postgres.generate_database_credential(endpoint=endpoint.name)

tokens_differ = cred_1.token != cred_2.token
print(f"Token 1: {cred_1.token[:12]}...")
print(f"Token 2: {cred_2.token[:12]}...")
print(f"Tokens are different: {tokens_differ}")
print(f"\nEach call generates a fresh token. Cache them to avoid unnecessary API calls.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Pattern 4: Connecting to Lakebase from Application Code
# MAGIC
# MAGIC The full connection pattern for a Databricks App backend. This is exactly
# MAGIC what the Lab Console's `db.py` does:
# MAGIC
# MAGIC ```python
# MAGIC import os
# MAGIC import psycopg
# MAGIC from psycopg.rows import dict_row
# MAGIC from databricks.sdk import WorkspaceClient
# MAGIC
# MAGIC def connect_to_lakebase(project_id, schema, branch_id="production"):
# MAGIC     """Connect to a user's Lakebase project as the app SP."""
# MAGIC     w = WorkspaceClient()  # Uses SP auth in Databricks Apps
# MAGIC
# MAGIC     # Discover the endpoint
# MAGIC     endpoints = list(w.postgres.list_endpoints(
# MAGIC         parent=f"projects/{project_id}/branches/{branch_id}"
# MAGIC     ))
# MAGIC     ep = w.postgres.get_endpoint(name=endpoints[0].name)
# MAGIC
# MAGIC     # Generate a credential (SP authenticates as itself)
# MAGIC     cred = w.postgres.generate_database_credential(
# MAGIC         endpoint=endpoints[0].name
# MAGIC     )
# MAGIC
# MAGIC     # The SP's PG username is its client_id
# MAGIC     sp_username = os.getenv("PGUSER") or os.getenv("DATABRICKS_CLIENT_ID")
# MAGIC
# MAGIC     conn = psycopg.connect(
# MAGIC         host=ep.status.hosts.host,
# MAGIC         dbname="databricks_postgres",
# MAGIC         user=sp_username,
# MAGIC         password=cred.token,
# MAGIC         sslmode="require",
# MAGIC         options=f"-c search_path={schema},public",
# MAGIC         row_factory=dict_row,
# MAGIC     )
# MAGIC     return conn
# MAGIC ```
# MAGIC
# MAGIC **Key points:**
# MAGIC - `WorkspaceClient()` with no arguments uses SP auth (reads `DATABRICKS_CLIENT_ID`/`SECRET` from env)
# MAGIC - The `search_path` option routes queries to the correct user schema
# MAGIC - The SP username (`PGUSER`) is set automatically when a postgres resource is attached

# COMMAND ----------

# MAGIC %md
# MAGIC ## App Configuration Reference
# MAGIC
# MAGIC The `app.yaml` declares a postgres resource (for the SP's OAuth scope)
# MAGIC and sets the default branch:
# MAGIC
# MAGIC ```yaml
# MAGIC command:
# MAGIC   - python
# MAGIC   - -m
# MAGIC   - uvicorn
# MAGIC   - app:app
# MAGIC   - --host
# MAGIC   - 0.0.0.0
# MAGIC   - --port
# MAGIC   - "8000"
# MAGIC
# MAGIC env:
# MAGIC   - name: LAKEBASE_BRANCH_ID
# MAGIC     value: production
# MAGIC
# MAGIC resources:
# MAGIC   - name: lakebase-db
# MAGIC     type: postgres
# MAGIC ```
# MAGIC
# MAGIC ### What the `postgres` resource does
# MAGIC
# MAGIC | Effect | Details |
# MAGIC |--------|---------|
# MAGIC | **Grants `postgres` OAuth scope** | The SP can call `list_endpoints`, `generate_database_credential`, etc. |
# MAGIC | **Creates PG role** | A PostgreSQL role matching the SP's client_id is created automatically |
# MAGIC | **Grants `CONNECT` + `CREATE`** | The SP can connect and create schemas in the attached database |
# MAGIC | **Injects env vars** | `PGHOST`, `PGUSER`, `PGDATABASE`, `PGPORT`, `PGSSLMODE` are set |
# MAGIC
# MAGIC ### What you still need to do per user
# MAGIC
# MAGIC The resource attachment connects the SP to **one** project (the facilitator's).
# MAGIC To access other users' projects, each user must run the `GRANT` statements
# MAGIC from Pattern 2 above.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Deployment (Facilitator Only)
# MAGIC
# MAGIC The Lab Console is deployed once for the entire workshop via a
# MAGIC Databricks Asset Bundle (DAB):
# MAGIC
# MAGIC ```bash
# MAGIC # Build the frontend
# MAGIC cd apps/lakebase-lab-console/frontend
# MAGIC npm install && npm run build
# MAGIC cd ../../..
# MAGIC
# MAGIC # Deploy everything
# MAGIC databricks bundle deploy --target dev
# MAGIC databricks bundle run lakebase_lab_console --target dev
# MAGIC ```
# MAGIC
# MAGIC The app is named `lakebase-lab-console` and is accessible to all
# MAGIC workspace users: **Compute → Apps → lakebase-lab-console**
# MAGIC
# MAGIC After deployment, the facilitator attaches their Lakebase project as a
# MAGIC postgres resource on the app (done automatically by `setup.sh`). This
# MAGIC gives the SP the `postgres` OAuth scope needed for Lakebase SDK calls.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify
# MAGIC
# MAGIC Open the app from **Compute → Apps → lakebase-lab-console**.
# MAGIC
# MAGIC You should see:
# MAGIC - Your name in the sidebar
# MAGIC - Your project ID below the app title
# MAGIC - A green "Connected" status dot
# MAGIC - Your tables and data from the setup notebook
# MAGIC
# MAGIC If you see "Lakebase Project Not Found", run `00_Setup_Lakebase_Project`
# MAGIC first, then refresh the app.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Patterns Summary
# MAGIC
# MAGIC | Pattern | When to Use | Key API |
# MAGIC |---------|-------------|---------|
# MAGIC | **SP Lookup** | Find an app's Service Principal ID | `w.apps.get(name=...)` |
# MAGIC | **Schema Grants** | Grant an SP access to a schema it doesn't own | `databricks_create_role()` + `GRANT` SQL |
# MAGIC | **Token Refresh** | Any long-running app connecting to Lakebase | `w.postgres.generate_database_credential()` with 45-min cache |
# MAGIC | **App Connection** | Full connection pattern from a Databricks App | `WorkspaceClient()` + psycopg + `search_path` |

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Workshop Complete!
# MAGIC
# MAGIC You've explored a full-stack app backed by Lakebase with automatic
# MAGIC per-user routing. Here's a summary of every lab path in the workshop:
# MAGIC
# MAGIC | Path | Lab Folder | Feature |
# MAGIC |------|-----------|---------|
# MAGIC | **Foundation** | `notebooks/` | Project setup, architecture, schema seeding |
# MAGIC | **Data Operations** | `labs/data-operations/` | CRUD, JSONB, arrays, audit triggers, transactions |
# MAGIC | **Reverse ETL** | `labs/reverse-etl/` | Sync Delta Lake tables into Lakebase |
# MAGIC | **Development Experience** | `labs/development-experience/` | Git-like branching, autoscaling, scale-to-zero |
# MAGIC | **Observability** | `labs/observability/` | pg_stat views, index analysis, monitoring |
# MAGIC | **Authentication** | `labs/authentication/` | OAuth tokens, roles, two-layer permissions |
# MAGIC | **Backup & Recovery** | `labs/backup-recovery/` | PITR, branch snapshots, instant restore |
# MAGIC | **Agentic Memory** | `labs/agentic-memory/` | Persistent AI agent memory with sessions |
# MAGIC | **Online Feature Store** | `labs/online-feature-store/` | Real-time ML feature serving |
# MAGIC | **App Deployment** | `labs/app-deployment/` | Full-stack React + FastAPI app (this lab) |
# MAGIC
# MAGIC Explore any paths you haven't tried yet — each one is independent and self-contained.
