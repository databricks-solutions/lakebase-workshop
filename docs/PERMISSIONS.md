# Permissions Guide

## Shared App Architecture

The Lab Console runs as a **single shared Databricks App** (`lakebase-lab-console`).
When a user opens the app, it reads their email from the Databricks Apps proxy headers
and routes them to their own Lakebase project. All SDK calls and database connections
are performed by the app's **Service Principal** (SP).

## Two-Step Permission Model

The app requires two things to work:

### 1. SP gets the `postgres` OAuth scope (facilitator — once)

The app declares a `postgres` resource in `app.yaml`. After deployment, the facilitator
attaches their Lakebase project to this resource (done automatically by `setup.sh`).
This gives the SP the `postgres` OAuth scope, which is required for Lakebase SDK calls
like `list_endpoints` and `generate_database_credential`.

### 2. Each user grants the SP access to their project (per-user — once)

Each participant runs Step 6 in `00_Setup_Lakebase_Project` (or the equivalent cells
in the App Deployment lab). This:

1. Looks up the app's SP client_id
2. Grants the SP `CAN_MANAGE` on the project ACL (Step 6a) — required for branch and
   compute management. See [Control Plane Permissions](#control-plane-permissions-branchendpoint-management).
3. Ensures the `databricks_auth` extension is installed: `CREATE EXTENSION IF NOT EXISTS databricks_auth`
   — this extension provides the `databricks_create_role()` function, and each
   Postgres database needs its own copy.
4. Creates a PostgreSQL OAuth role for the SP: `SELECT databricks_create_role('<SP_CLIENT_ID>', 'service_principal')`
5. Grants schema access: `GRANT ALL ON SCHEMA ... TO "<SP_CLIENT_ID>"`

## What Each User Needs

| Requirement | Details |
|-------------|---------|
| **Workspace access** | User must be able to access the Databricks workspace and the app |
| **Lakebase project** | User must have run `00_Setup_Lakebase_Project` to create their project |
| **SP grant** | User must have completed Step 6 in setup (or the App Deployment lab) |

## How Authentication Works

### Request Flow

1. User opens the Lab Console app in their browser
2. Databricks Apps proxy authenticates the user via workspace SSO
3. Proxy injects `X-Forwarded-Email` into every request
4. The FastAPI backend reads this header and:
   - Derives the project ID from the email: `lakebase-lab-<sanitized-username>`
   - Derives the schema: `lakebase_lab_<sanitized_username>`
   - Uses the app's SP (`WorkspaceClient()`) to call Lakebase SDK
   - Generates a database credential via `w.postgres.generate_database_credential()`
   - Connects to PostgreSQL using the SP's client_id as username

### Two Permission Layers

Lakebase has two independent permission layers:

1. **Project ACLs (control plane)** — the SP needs `CAN_MANAGE` on each user's
   Lakebase project to create branches and manage computes. Granted via the
   Permissions API in Step 6a of the setup notebook.
2. **Database permissions (data plane)** — the SP needs a PostgreSQL role with schema
   grants. This is handled by `databricks_create_role` (from the `databricks_auth`
   extension) + `GRANT` in Step 6b of the setup notebook.

The two layers are independent. Attaching the app's `postgres` resource satisfies
layer 2 only; it does not grant any project ACL.

### Why Not User Token Passthrough?

The Databricks Apps proxy forwards a user token (`x-forwarded-access-token`), but
this token **does not include the `postgres` OAuth scope**. Without this scope,
Lakebase SDK calls fail. The SP approach works because the postgres resource
declaration in `app.yaml` gives the SP the required scope.

### Local Development Fallback

When running the app locally (outside the Databricks Apps runtime), the forwarded
headers are not available. In this case, the app falls back to:

- Environment variables: `LAKEBASE_USER_EMAIL`, `LAKEBASE_PROJECT_ID`, `LAKEBASE_SCHEMA`
- Default Databricks SDK authentication (from `~/.databrickscfg`)

This fallback only applies in **local** auth mode. The deployed app sets
`LAKEBASE_AUTH_MODE=apps` (in `app.yaml`), which **fails closed**: if a request
arrives without a forwarded identity, the app returns `401` instead of falling
back to an ambient Service Principal identity. For local testing, select local
mode explicitly with `LAKEBASE_AUTH_MODE=local` (this is also auto-detected when
running off-platform).

## Shared Service Principal — Threat Model

Because every participant shares one app Service Principal, and each participant
grants that SP access to their own project, **the SP can technically reach every
project that has completed setup**. Correct per-request routing (email →
`project_id`/`schema`) is therefore the tenant boundary. The app enforces this
in depth:

| Risk | Control |
|------|---------|
| Spoofed / missing identity | Deployed mode requires the Apps-proxy `X-Forwarded-Email`; missing identity → `401` (`backend/user_context.py`). |
| Cross-project Data API access | The Data API base URL is resolved server-side from the caller's own project (`w.postgres.get_data_api`); client URLs must match it exactly (`backend/routes_data_api.py`). |
| Token exfiltration via redirects | The Data API proxy never follows redirects and caps response size (`backend/security.py`). |
| "Read-only" SQL that writes | The SQL playground runs inside a `READ ONLY` transaction with a statement timeout and row cap (`backend/db.py`, `backend/routes_data.py`). |
| Cross-user load tests | Load-test status/stop/stream are owner-scoped (`backend/routes_loadtest.py`). |
| Arbitrary pipeline triggers | Sync triggers resolve the pipeline from the caller's own synced table (`backend/routes_online_tables.py`). |
| Data exposed over the Data API | Governed by Postgres roles + **row-level security**, not Unity Catalog — enable RLS on every exposed table and never expose data through the project owner account. |

RLS remains valuable defense-in-depth for Data-API-exposed tables, but it does
not replace the server-side project binding above.

## Control Plane Permissions (Branch/Endpoint Management)

The app uses the SP for SDK calls (branch create/delete, endpoint management). These
are governed by the project ACL, not by PostgreSQL grants and not by the app's
`postgres` resource attachment. The grantable levels are `CAN_USE` and `CAN_MANAGE`;
`CAN_CREATE` is inherited by all workspace users and cannot be set explicitly.

Step 6a of the setup notebook grants the SP `CAN_MANAGE` on the participant's project:

```python
from databricks.sdk.service.iam import AccessControlRequest, PermissionLevel

w.permissions.update(                      # PATCH — additive, idempotent
    request_object_type="database-projects",
    request_object_id=PROJECT_ID,
    access_control_list=[
        AccessControlRequest(
            service_principal_name=SP_CLIENT_ID,
            permission_level=PermissionLevel.CAN_MANAGE,
        )
    ],
)
```

The equivalent REST call is
`PATCH /api/2.0/permissions/database-projects/{project_id}`.

Without this grant, Branch Manager and Compute fail with:

> The user is not authorized to make the request, please contact the workspace admin
> to assign the user `<sp_client_id>` 'Can Manage' for Database project `<uuid>`.

The UUID in that message is the project's internal object ID. The Permissions API
takes the human-readable `project_id` instead (for example
`lakebase-lab-jane-doe`) — you can confirm the mapping with
`GET /api/2.0/permissions/database-projects/{project_id}`, whose `object_id` field
contains the UUID.

Use `w.permissions.set()` (PUT) to downgrade or revoke; `update()` (PATCH) can only
add. PUT replaces the entire explicit ACL, so include every identity that should
retain access.

See [Grant permissions programmatically](https://docs.databricks.com/aws/en/oltp/projects/grant-permissions-programmatically).

## Synced Table Permissions

Synced tables (Reverse ETL) need the app SP granted at **two layers**. Both are
required for the app's Synced Tables page to work.

### Layer 1 — Unity Catalog (discovery + trigger)

The app lists synced tables via `w.tables.list("main", "<schema>")` and resolves
each table's sync pipeline through Unity Catalog — **all as the app SP**
(`backend/routes_online_tables.py`). Setup Step 6 only grants Postgres access, so
the SP cannot see the participant's UC schema and **synced tables won't appear in
the app** (and the "Sync now" button can't resolve the pipeline). The Reverse ETL
lab §5a grants this UC access as the schema owner:

```python
from databricks.sdk.service.catalog import PermissionsChange, Privilege, SecurableType
w.grants.update(SecurableType.CATALOG.value, "main",
    changes=[PermissionsChange(principal=app_sp, add=[Privilege.USE_CATALOG])])
w.grants.update(SecurableType.SCHEMA.value, "main.<schema>",
    changes=[PermissionsChange(principal=app_sp, add=[Privilege.USE_SCHEMA, Privilege.SELECT])])
```

Pass `.value` (or the literal `"CATALOG"` / `"SCHEMA"`). The enum is not a `str` subclass
and the SDK interpolates this argument directly into the request path, so passing the enum
member itself sends its Python repr and the API rejects the call with
`InvalidParameterValue: ... SECURABLETYPE.CATALOG is not a valid securable type`.

The UC schema (`main.<schema>`) is created by the Reverse ETL / Feature Store labs,
not by base setup — which is why this grant lives in those labs rather than
`notebooks/00`.

### Layer 2 — Postgres (read the rows)

Synced tables are created by the Lakebase sync pipeline and are owned by the
internal `databricks_writer_` role — **not** by the user who created them. Because
of this, the ordinary schema-level `GRANT ALL ON ALL TABLES` in the setup notebook
does **not** cover pipeline-owned synced tables. To give the app's SP read access
to the synced rows over Postgres, the `databricks_superuser` must grant it
explicitly:

```sql
GRANT USAGE ON SCHEMA <sync_schema> TO "<SP_CLIENT_ID>";
GRANT SELECT ON <sync_schema>.<synced_table> TO "<SP_CLIENT_ID>";
```

For allowed management operations on a synced table (`CREATE/ALTER/DROP INDEX`,
`DROP TABLE`), register the identity as a manager instead:

```sql
CREATE EXTENSION IF NOT EXISTS databricks_auth;
SELECT databricks_synced_table_add_manager(
    '"<sync_schema>"."<synced_table>"'::regclass, '<SP_CLIENT_ID>');
```

See [Synced tables — Ownership and permissions](https://docs.databricks.com/aws/en/oltp/projects/sync-tables#ownership-and-permissions).
