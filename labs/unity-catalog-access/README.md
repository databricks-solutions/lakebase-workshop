# Unity Catalog Access (Federated Catalog)

Register your Lakebase Postgres database as a **read-only Unity Catalog catalog** so Lakehouse tools can discover and query live operational data without copying it.

This is the **federated read** pattern — complementary to Reverse ETL (copy into Lakebase) and Lakehouse Sync / CDF (copy out to Delta).

## What to run

| Step | Open this | What you'll do |
|------|-----------|----------------|
| 1 | [`Unity_Catalog_Access.py`](Unity_Catalog_Access.py) | Compare connection methods, register the catalog via SDK, verify registration, then query from the SQL Editor |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)
- **`CREATE CATALOG`** on the Unity Catalog metastore (or a facilitator who can register once and grant you `USE CATALOG` + `SELECT`)
- A **Serverless SQL Warehouse** to run federated queries (Pro / Classic warehouses return `PERMISSION_DENIED`)

## Key Concepts

- **Federated catalog** — Unity Catalog mirrors your Postgres schemas/tables for discovery and read-only SQL; data stays in Lakebase
- **Live reads** — no sync pipeline, no Delta copy; freshness is “query-time”
- **UC governance** — permissions, lineage, and audit apply to queries through SQL warehouses; direct Postgres connections still use Postgres roles
- **Read-only through UC** — writes still go through Lakebase (SQL Editor, drivers, Data API, apps)

## When to use which Lakehouse ↔ Lakebase path

| Pattern | Direction | Copies data? | Best for |
|---------|-----------|--------------|----------|
| **Unity Catalog registration** *(this lab)* | Live federated **read** of Postgres via UC | No | Dashboards, ad-hoc joins of OLTP + lakehouse tables, centralized discovery |
| **Direct SQL Editor → Lakebase compute** | Read-write to one project/branch | No | Interactive Postgres work without UC federation |
| **Synced tables (Reverse ETL)** | Delta → Postgres | Yes | Low-latency serving of lakehouse data to apps |
| **Lakehouse Sync / CDF** | Postgres → Delta change history | Yes | Analytics, medallion bronze, audit history on operational changes |
| **OAuth / password drivers** | App ↔ Postgres | No | Application backends, notebooks with `psycopg` |
| **Data API** | HTTP ↔ Postgres | No | Lightweight REST clients (Postgres RLS, not UC) |

## Documentation

- [Register a Lakebase database in Unity Catalog](https://docs.databricks.com/aws/en/oltp/projects/register-uc)
- [Query from SQL editor in the workspace](https://docs.databricks.com/aws/en/oltp/projects/query-sql-editor)
- [Reverse ETL (Synced Tables)](../reverse-etl/) — copy lakehouse → Lakebase
- [Lakehouse Sync](../lakehouse-sync/) — copy Lakebase → Delta via CDF

## Notes

- One Postgres database → one UC catalog. Workshop catalogs are named `lb_fed_<you>` so they do not collide with `main` (used by other UC labs).
- Child branches inherit parent registration metadata — do not try to register a branched database as a second catalog while the parent registration exists.
- Metadata can lag; refresh in Catalog Explorer if new tables are missing.
