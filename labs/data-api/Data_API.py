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
# MAGIC 1. **Enable the Data API in the UI first.** There is no create-API SDK call. In your Lakebase
# MAGIC    project, open the **Data API** page and click **Enable Data API**. This creates the
# MAGIC    `authenticator` role, the `pgrst` schema, and exposes the `public` schema. Copy the **API URL**
# MAGIC    from the API tab — you'll paste it into a widget below.
# MAGIC 2. **You cannot call the Data API as the project owner.** The `authenticator` role must be able
# MAGIC    to *assume* the caller's role, and that can't be granted for elevated accounts (the owner).
# MAGIC    Use a **service principal (recommended)** or a **different, non-owner Databricks user**. This
# MAGIC    notebook creates the role + grants (runnable as owner), but the **HTTP calls must be made with a
# MAGIC    non-owner token**.
# MAGIC
# MAGIC > **Governance caveat:** the Data API talks **directly to Postgres** and enforces security with
# MAGIC > Postgres roles + RLS — it does **not** use Unity Catalog governance. Because it's reachable over
# MAGIC > the internet, RLS is essential. Treat it as a database-security surface, not a UC-governed one.

# COMMAND ----------

# MAGIC %pip install "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" "requests>=2.31" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../_setup

# COMMAND ----------

# Parameters — fill these in from the Data API tab in the Lakebase App.
dbutils.widgets.text("rest_endpoint", "", "Data API URL (from the API tab, no schema suffix)")
dbutils.widgets.text("sp_app_id", "", "Service principal application ID (UUID) to grant API access")

REST_ENDPOINT = dbutils.widgets.get("rest_endpoint").rstrip("/")
SP_APP_ID = dbutils.widgets.get("sp_app_id").strip()

conn = get_connection("production")
print("✓ Connected to production branch")


def run(sql, params=None, show=True, label=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        conn.commit()
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
        # Create a Postgres role for the service principal identity
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
# MAGIC With the API URL and a **non-owner** OAuth token, calls are plain HTTPS. Remember to append the
# MAGIC schema name to the URL (e.g. `/public`, or your exposed per-user schema). The examples below use a
# MAGIC token minted for *this* notebook's identity — **if you're the project owner these calls will be
# MAGIC rejected**; run them as a service principal / non-owner instead.

# COMMAND ----------

import requests

def _oauth_token():
    """Mint a workspace OAuth token for the current identity (owner tokens are rejected by the Data API)."""
    return w.config.oauth_token().access_token

if not REST_ENDPOINT:
    print("Set the `rest_endpoint` widget to your Data API URL (from the API tab) to run the HTTP calls.")
else:
    schema_path = PG_SCHEMA  # the exposed schema; use "public" if you exposed public instead
    base = f"{REST_ENDPOINT}/{schema_path}"
    headers = {"Authorization": f"Bearer {_oauth_token()}"}
    try:
        # GET with a filter + column selection
        r = requests.get(f"{base}/api_clients", params={"select": "id,name,company", "id": "gte.2"},
                         headers=headers, timeout=30)
        print("GET /api_clients?id=gte.2 ->", r.status_code)
        print(r.text[:500])
    except Exception as e:
        print(f"Request failed: {e}")

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
# MAGIC Configure these on the **Settings** tab in the Lakebase App:
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

# COMMAND ----------

# MAGIC %md
# MAGIC ## What's Next?
# MAGIC
# MAGIC | Path | Folder | What You'll Learn |
# MAGIC |------|--------|-------------------|
# MAGIC | **Data Operations** | `labs/data-operations/` | The SQL behind the tables you just exposed |
# MAGIC | **Authentication, Security & Compliance** | `labs/authentication/` | OAuth, roles, RLS, encryption, Private Link |
# MAGIC | **App Deployment** | `labs/app-deployment/` | A full-stack app backend as an alternative to the Data API (capstone) |
