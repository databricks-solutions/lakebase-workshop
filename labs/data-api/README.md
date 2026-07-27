# Data API (PostgREST)

Expose your Lakebase tables as **REST endpoints over HTTPS** — CRUD, filtering, joins, and pagination with no custom backend. Compatible with the PostgREST specification.

## Labs

| Order | Lab | What You'll Learn |
|-------|-----|-------------------|
| 1 | `Data_API` | Enable the API, create a role for a non-owner identity, grant access, protect with RLS, and call it over HTTP |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)
- **Enable the Data API** in the Lakebase App (creates the `authenticator` role and exposes `public`)
- A **service principal** or **non-owner Databricks user** to call the API (the project owner can't)

## Key Concepts

- **`authenticator` role** — a single login-only role the API uses; it *assumes* each caller's Postgres identity per request.
- **OAuth bearer auth** — every request carries a Databricks OAuth token in the `Authorization` header. Each identity needs a Postgres role created with `databricks_create_role`.
- **Not the owner** — the `authenticator` role can't assume an elevated (owner) account; use a service principal or a different user.
- **Row-level security** — the API is internet-reachable through one endpoint, so RLS (not just table grants) is what isolates data per caller.
- **No Unity Catalog governance** — access is governed by Postgres roles + RLS, not UC. This is a database-security surface.

## Documentation

- [Lakebase Data API](https://docs.databricks.com/aws/en/oltp/projects/data-api)
- [Row-level security](https://docs.databricks.com/aws/en/oltp/projects/data-api#row-level-security)
- [Manage Postgres roles](https://docs.databricks.com/aws/en/oltp/projects/roles-permissions)
