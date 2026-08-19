# Databricks notebook source
# MAGIC %md
# MAGIC # Lakebase Data API (PostgREST)
# MAGIC
# MAGIC **Path:** Data API &nbsp;|&nbsp; **Prerequisite:** `00_Setup_Lakebase_Project`
# MAGIC
# MAGIC **Lakebase feature:** RESTful (PostgREST-compatible) access to your Postgres data over HTTPS
# MAGIC
# MAGIC The Data API turns your database schema into REST endpoints — CRUD over HTTP with no custom
# MAGIC backend. In this notebook you will:
# MAGIC 1. Understand how the Data API authenticates (the `authenticator` role + OAuth bearer tokens)
# MAGIC 2. Create a sample table to expose
# MAGIC 3. Create a Postgres role for a **non-owner** identity and grant it access
# MAGIC 4. Protect the table with **row-level security (RLS)**
# MAGIC 5. Call the API over HTTP (`requests`) and see filtering, joins, and CRUD
# MAGIC
# MAGIC **Run `00_Setup_Lakebase_Project` first.** Table references use unqualified names; your schema is set via `search_path` in `_setup`.
# MAGIC
# MAGIC **Docs:** [Lakebase Data API](https://docs.databricks.com/aws/en/oltp/projects/data-api) |
# MAGIC [Row-level security](https://docs.databricks.com/aws/en/oltp/projects/data-api#row-level-security)

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⚠️ Two things to know before you start
# MAGIC
# MAGIC 1. **Enabling the Data API puts your database on the public internet.** It is off by default and
# MAGIC    this notebook will not turn it on unless you set the `enable_data_api` widget to `yes`.
# MAGIC    Enabling creates the `authenticator` role and the `pgrst` schema, exposes the schemas you
# MAGIC    choose, and returns the API URL — either from `w.postgres.create_data_api()` below or from the
# MAGIC    **Data API** page of your Lakebase project, whichever you prefer.
# MAGIC 2. **You cannot call the Data API as the project owner.** The `authenticator` role must be able
# MAGIC    to *assume* the caller's role, and that can't be granted for elevated accounts (the owner).
# MAGIC    So this notebook creates the role and grants as owner, then makes the actual HTTP calls
# MAGIC    through the **Lab Console app**, which runs as a non-owner service principal.
# MAGIC
# MAGIC > **Governance caveat:** the Data API talks **directly to Postgres** and enforces security with
# MAGIC > Postgres roles + RLS — it does **not** use Unity Catalog governance. Because it's reachable over
# MAGIC > the internet, RLS is essential. Treat it as a database-security surface, not a UC-governed one.

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "requests>=2.31" "protobuf>=5.29.5,<6" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

# Parameters. Leave rest_endpoint empty to resolve the URL from the API itself.
dbutils.widgets.dropdown("enable_data_api", "no", ["no", "yes"],
                         "Enable the Data API (exposes the database on the internet)")
dbutils.widgets.text("rest_endpoint", "", "Data API URL (optional override, no schema suffix)")
dbutils.widgets.text("sp_app_id", "", "Service principal application ID (defaults to the Lab Console app)")

ENABLE_DATA_API = dbutils.widgets.get("enable_data_api") == "yes"
REST_ENDPOINT = dbutils.widgets.get("rest_endpoint").rstrip("/")
SP_APP_ID = dbutils.widgets.get("sp_app_id").strip()

conn = get_connection("production")
print("✓ Connected to production branch")

APP_NAME = "lakebase-lab-console"

if not SP_APP_ID:
    try:
        _app = w.apps.get(name=APP_NAME)
        SP_APP_ID = (getattr(_app, "effective_service_principal_client_id", None)
                     or _app.service_principal_client_id)
        print(f"✓ Using the Lab Console service principal: {SP_APP_ID}")
    except Exception:
        print(f"App '{APP_NAME}' not found — set the sp_app_id widget to a non-owner "
              "service principal to run the API sections.")


def run(sql, params=None, show=True, label=None):
    with conn.cursor() as cur:
        try:
            cur.execute(sql, params or ())
            conn.commit()
        except Exception:
            # Without this the failed statement leaves the transaction aborted and
            # every later cell dies with InFailedSqlTransaction instead of its own error.
            conn.rollback()
            raise
        if cur.description is None:
            return []
        rows = cur.fetchall()
    if show:
        if label:
            print(f"— {label} —")
        for r in rows:
            print(dict(r))
    return rows

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Create a sample table to expose
# MAGIC
# MAGIC We create the table in your **per-user schema**. To expose a schema other than `public` through
# MAGIC the Data API, add it under **Advanced settings → Exposed schemas** in the Lakebase App (and make
# MAGIC sure the API role has `USAGE` on the schema and `SELECT` on the tables).

# COMMAND ----------

run("DROP TABLE IF EXISTS api_clients CASCADE;", show=False)
run("""
    CREATE TABLE api_clients (
        id      SERIAL PRIMARY KEY,
        name    TEXT NOT NULL,
        email   TEXT UNIQUE NOT NULL,
        company TEXT,
        owner   TEXT DEFAULT CURRENT_USER
    );
""", show=False)
run("""
    INSERT INTO api_clients (name, email, company) VALUES
      ('Acme Corp',        'contact@acme.com',          'Acme Corporation'),
      ('TechStart Inc',    'hello@techstart.com',       'TechStart Inc'),
      ('Global Solutions', 'info@globalsolutions.com',  'Global Solutions Ltd');
""", show=False)
run("SELECT id, name, email, company FROM api_clients ORDER BY id;", label="api_clients")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1b. Enable the Data API (opt-in)
# MAGIC
# MAGIC `w.postgres.create_data_api()` enables the API on one **database** of a branch and reports the
# MAGIC URL, so nothing has to be copied out of the UI. We enable it on `databricks_postgres` and expose
# MAGIC only your own schema — never `public` on a shared project.
# MAGIC
# MAGIC If `enable_data_api` is `no` (the default), this cell just reports the current state.
# MAGIC
# MAGIC > Deleting it again is one call: `w.postgres.delete_data_api(name=...)`, shown in Cleanup.

# COMMAND ----------

import time

from databricks.sdk.service.postgres import DataApi, DataApiDataApiSpec

DATA_API_DB = "databricks_postgres"


def data_api_resource(pg_database=DATA_API_DB, branch="production"):
    """Resolve the `.../databases/{id}/data-api` resource name for a Postgres database."""
    parent = f"projects/{PROJECT_ID}/branches/{branch}"
    for db in w.postgres.list_databases(parent=parent):
        if getattr(getattr(db, "status", None), "postgres_database", None) == pg_database:
            return f"{db.name}/data-api", db.name
    raise RuntimeError(f"no database named {pg_database} on branch {branch}")


api_name, database_name = data_api_resource()

try:
    data_api = w.postgres.get_data_api(name=api_name)
    print("✓ Data API already enabled")
except Exception:
    data_api = None
    if not ENABLE_DATA_API:
        print("Data API is not enabled on this project.")
        print("  Set the `enable_data_api` widget to `yes` to enable it from here, or click")
        print("  Enable Data API on the project's Data API page. Sections 2-4 need it.")
    else:
        print(f"Enabling the Data API on {DATA_API_DB}, exposing schema {PG_SCHEMA}...")
        w.postgres.create_data_api(
            parent=database_name,
            data_api=DataApi(spec=DataApiDataApiSpec(db_schemas=[PG_SCHEMA])),
        )
        # Enablement is asynchronous: the authenticator role and pgrst schema appear
        # a moment after the call returns.
        for _ in range(30):
            try:
                data_api = w.postgres.get_data_api(name=api_name)
                break
            except Exception:
                time.sleep(10)
        print("✓ Data API enabled" if data_api else "⚠ still enabling — re-run this cell shortly")

if data_api:
    status = getattr(data_api, "status", None)
    REST_ENDPOINT = REST_ENDPOINT or (getattr(status, "url", "") or "").rstrip("/")
    print(f"  URL:              {REST_ENDPOINT or '(not reported)'}")
    print(f"  Exposed schemas:  {getattr(status, 'db_schemas', None)}")
    print(f"  Max rows:         {getattr(status, 'db_max_rows', None)}")
    show_view_link(
        "View your Lakebase project (Data API settings)",
        lakebase_project_url(),
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create a Postgres role for the caller and let `authenticator` assume it
# MAGIC
# MAGIC Each Databricks identity that calls the Data API needs a corresponding Postgres role, created
# MAGIC with `databricks_create_role` (a role added via the **Roles & Databases** UI can't be granted to
# MAGIC `authenticator`). We use a **service principal** here — pass its application ID (UUID) in the widget.
# MAGIC
# MAGIC > These statements only succeed once the Data API is **enabled** (that's what creates the
# MAGIC > `authenticator` role). They're wrapped so the notebook keeps going if it isn't enabled yet.

# COMMAND ----------

if not SP_APP_ID:
    print("Set the `sp_app_id` widget to a service principal application ID (UUID) to run this section.")
else:
    try:
        run("CREATE EXTENSION IF NOT EXISTS databricks_auth;", show=False)
        # Create a Postgres role for the service principal identity. databricks_create_role
        # has no IF NOT EXISTS, and the Lab Console may already have created this one.
        exists = run("SELECT 1 FROM pg_roles WHERE rolname = %s;", (SP_APP_ID,), show=False)
        if exists:
            print(f"  Role {SP_APP_ID} already exists — reusing it")
        else:
            run("SELECT databricks_create_role(%s, 'SERVICE_PRINCIPAL');", (SP_APP_ID,), show=False)
        # Let the authenticator assume that role, then grant table access to it
        run(f'GRANT "{SP_APP_ID}" TO authenticator;', show=False)
        run(f'GRANT USAGE ON SCHEMA {PG_SCHEMA} TO "{SP_APP_ID}";', show=False)
        run(f'GRANT SELECT, INSERT, UPDATE, DELETE ON api_clients TO "{SP_APP_ID}";', show=False)
        run(f'GRANT USAGE ON ALL SEQUENCES IN SCHEMA {PG_SCHEMA} TO "{SP_APP_ID}";', show=False)
        print(f"✓ Role created and granted for SP {SP_APP_ID}")
    except Exception as e:
        print("✗ Could not create/grant the API role.")
        print("  Most likely the Data API isn't enabled yet (no `authenticator` role), or the role")
        print("  was created via the Roles & Databases UI instead of databricks_create_role.")
        print(f"  Underlying error: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Protect the table with row-level security
# MAGIC
# MAGIC The Data API is internet-reachable and every caller shares one HTTP endpoint, so table-level
# MAGIC grants aren't enough — enable **RLS** and write policies. When a request comes in, `authenticator`
# MAGIC assumes the caller's identity and Postgres enforces the policies automatically. In Lakebase,
# MAGIC `current_user` is the caller's email (or the SP's application ID).

# COMMAND ----------

run("ALTER TABLE api_clients ENABLE ROW LEVEL SECURITY;", show=False)
# Example policy: a caller only sees rows they own. Adjust to your tenancy model.
run("DROP POLICY IF EXISTS api_clients_owner ON api_clients;", show=False)
run("CREATE POLICY api_clients_owner ON api_clients USING (owner = current_user);", show=False)
run("""
    SELECT polname, polcmd
    FROM pg_policy
    WHERE polrelid = 'api_clients'::regclass;
""", label="Policies on api_clients")
print("Note: table owners bypass RLS. Use FORCE ROW LEVEL SECURITY to apply it to the owner too.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Call the Data API over HTTP
# MAGIC
# MAGIC Calls are plain HTTPS: the URL is `{api}/{schema}/{table}`, the filters are PostgREST query
# MAGIC parameters, and the bearer token is an OAuth token for a **non-owner** identity.
# MAGIC
# MAGIC That last part is why we don't call it directly from here. This notebook runs as you, the project
# MAGIC owner, and the `authenticator` role cannot assume an owner's role — the API answers `401` no
# MAGIC matter how the request is shaped. The Lab Console app runs as a service principal, so we ask it
# MAGIC to make the call and hand back the response. Both paths below are shown: the owner call that
# MAGIC proves the rejection, then the same request through the app.

# COMMAND ----------

import requests


def owner_call():
    """The direct call, as the owner. Expected to be rejected — that is the lesson."""
    token = w.config.oauth_token().access_token
    r = requests.get(
        f"{REST_ENDPOINT}/{PG_SCHEMA}/api_clients",
        params={"select": "id,name,company", "id": "gte.2"},
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    return r.status_code, r.text[:300]


def app_call(method="GET", resource="api_clients", query=None, body=None):
    """The same call through the Lab Console, which authenticates as its service principal."""
    app_url = w.apps.get(name=APP_NAME).url.rstrip("/")
    token = w.config.oauth_token().access_token
    r = requests.post(
        f"{app_url}/api/data-api/call",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": REST_ENDPOINT, "schema_path": PG_SCHEMA, "resource": resource,
              "method": method, "query": query, "body": body},
        timeout=60,
    )
    return r.status_code, r.text[:600]


if not REST_ENDPOINT:
    print("No Data API URL — enable the Data API in section 1b first.")
else:
    status, text = owner_call()
    print(f"Direct call as the project owner -> {status}")
    print(f"  {text}")
    print("  A 401 here is correct: owner roles cannot be assumed by `authenticator`.\n")

    status, text = app_call(query="select=id,name,company&id=gte.2")
    print(f"Same request via the Lab Console service principal -> {status}")
    print(f"  {text}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### More HTTP operations (reference)
# MAGIC
# MAGIC ```bash
# MAGIC # Insert
# MAGIC curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
# MAGIC   -d '{"name":"New Client","email":"new@example.com","company":"New Co"}' \
# MAGIC   "$REST_ENDPOINT/public/api_clients"
# MAGIC
# MAGIC # Update (filter with eq)
# MAGIC curl -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
# MAGIC   -d '{"company":"Renamed Co"}' "$REST_ENDPOINT/public/api_clients?id=eq.1"
# MAGIC
# MAGIC # Delete
# MAGIC curl -X DELETE -H "Authorization: Bearer $TOKEN" "$REST_ENDPOINT/public/api_clients?id=eq.5"
# MAGIC
# MAGIC # Pagination + sorting
# MAGIC curl -H "Authorization: Bearer $TOKEN" "$REST_ENDPOINT/public/api_clients?order=name.asc&limit=10&offset=0"
# MAGIC ```
# MAGIC
# MAGIC Common filter operators: `eq`, `neq`, `gte`, `lte`, `like`, `in`. Resource embedding (joins) uses
# MAGIC `select=id,name,projects(id,name)`. After schema changes, click **Refresh schema cache** in the App.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Advanced settings & security checklist
# MAGIC
# MAGIC These map to the `DataApiSpec` fields you can pass to `create_data_api` / `update_data_api`
# MAGIC (`db_schemas`, `db_max_rows`, `server_cors_allowed_origins`, `openapi_mode`), and to the
# MAGIC **Settings** tab in the Lakebase App:
# MAGIC
# MAGIC | Setting | Why it matters |
# MAGIC |---------|----------------|
# MAGIC | **Exposed schemas** | Only `public` is exposed by default; add your schema explicitly |
# MAGIC | **Maximum rows** | Caps rows per response — guards against runaway queries / egress cost |
# MAGIC | **CORS allowed origins** | Lock to your app domains in production (empty = allow all) |
# MAGIC | **OpenAPI spec** | Optional `/openapi.json` for typed clients / Swagger |
# MAGIC
# MAGIC **Security checklist:** enable RLS on every exposed table · grant minimal privileges · use a
# MAGIC dedicated role per app · never expose via the owner account · review policies regularly. And
# MAGIC remember: **no Unity Catalog governance** — Postgres roles + RLS are the control plane here.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Clean Up (Optional)

# COMMAND ----------

# UNCOMMENT TO CLEAN UP:
# run("DROP TABLE IF EXISTS api_clients CASCADE;", show=False)
# conn.close()

# UNCOMMENT TO TURN THE DATA API BACK OFF (removes the internet-facing endpoint):
# w.postgres.delete_data_api(name=api_name)
# print(f"✓ Data API disabled for {DATA_API_DB}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC | Path | Folder | What You'll Learn |
# MAGIC |------|--------|-------------------|
# MAGIC | **Data Operations** | `labs/data-operations/` | The SQL behind the tables you just exposed |
# MAGIC | **Authentication, Security & Compliance** | `labs/authentication/` | OAuth, roles, RLS, encryption, Private Link |
# MAGIC | **App Deployment** | `labs/app-deployment/` | A full-stack app backend as an alternative to the Data API (capstone) |
