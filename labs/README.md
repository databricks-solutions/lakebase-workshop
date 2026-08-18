# Lab Paths

After **`notebooks/00_Setup_Lakebase_Project`**, pick labs by **what you want to learn**. Every lab is independent.

## How folders work

| Rule | What it means for you |
|------|------------------------|
| **One folder ≈ one topic** | Open `labs/<topic>/`, read its `README.md`, then run the notebook listed under **What to run** |
| **Almost all folders have one notebook** | e.g. `labs/reverse-etl/Reverse_ETL.py` |
| **One exception** | [`development-experience/`](development-experience/) has **three** short notebooks (branching, autoscaling, HA) — same topic, three exercises |
| **Tracks are not folders** | “Application Builders / Data & ML / Platform” below are **suggested orderings**, not nested directories |

Start here → [`labs/<folder>/README.md`](.) → open the file in **What to run**.

---

## Pick a track (recommended order)

### Application Builders

*Apps, APIs, and AI agents on Postgres.*

| # | Lab | Open / run | Learn |
|---|-----|------------|-------|
| 1 | [Data Operations](data-operations/) | [`Data_Operations.py`](data-operations/Data_Operations.py) · optional [`Advanced_Postgres.sql`](data-operations/Advanced_Postgres.sql) | CRUD, JSONB, arrays, triggers, transactions |
| 2 | [Data API](data-api/) | [`Data_API.py`](data-api/Data_API.py) | PostgREST, `authenticator` role, OAuth bearer, RLS |
| 3 | [Agentic Memory](agentic-memory/) | [`Agent_Memory.py`](agentic-memory/Agent_Memory.py) | Session + long-term agent memory |
| 4 | [Lakebase Search](lakebase-search/) *(Beta)* | [`Lakebase_Search.py`](lakebase-search/Lakebase_Search.py) | Vector + BM25 + hybrid RRF |
| 5 | [App Deployment](app-deployment/) | [`Deploy_Lab_Console_App.py`](app-deployment/Deploy_Lab_Console_App.py) | Capstone: React + FastAPI Lab Console |

### Data & ML Engineers

*Move data between the Lakehouse and Lakebase, serve features, **or** query Postgres live from UC.*

| # | Lab | Open / run | Learn |
|---|-----|------------|-------|
| 1 | [Reverse ETL](reverse-etl/) | [`Reverse_ETL.py`](reverse-etl/Reverse_ETL.py) | Synced tables: **copy** Delta → Postgres for serving |
| 2 | [Unity Catalog Access](unity-catalog-access/) | [`Unity_Catalog_Access.py`](unity-catalog-access/Unity_Catalog_Access.py) | Register Postgres as a **federated read-only** UC catalog (no copy) |
| 3 | [Lakehouse Sync](lakehouse-sync/) *(Public Preview)* | [README walkthrough](lakehouse-sync/README.md) (UI; no notebook yet) | CDF: **copy** Postgres → Delta change history |
| 4 | [Online Feature Store](online-feature-store/) | [`Online_Feature_Store.py`](online-feature-store/Online_Feature_Store.py) | Real-time ML feature serving |

**Lakehouse ↔ Lakebase at a glance**

| Pattern | Lab | Copies data? |
|---------|-----|--------------|
| Federated live **read** via UC | [Unity Catalog Access](unity-catalog-access/) | No |
| Delta → Postgres serving | [Reverse ETL](reverse-etl/) | Yes |
| Postgres → Delta CDC history | [Lakehouse Sync](lakehouse-sync/) | Yes |

### Platform Architects

* Branching, security, recovery, observability.*

| # | Lab | Open / run | Learn |
|---|-----|------------|-------|
| 1 | [Development Experience](development-experience/) | Run all three: [`Branches_and_Environments.py`](development-experience/Branches_and_Environments.py) → [`Autoscaling_and_Compute.py`](development-experience/Autoscaling_and_Compute.py) → [`High_Availability_and_Replicas.py`](development-experience/High_Availability_and_Replicas.py) | Branches, autoscaling, HA + read replicas |
| 2 | [Authentication, Security & Compliance](authentication/) | [`Authentication_and_Permissions.py`](authentication/Authentication_and_Permissions.py) | OAuth, roles, encryption, Private Link |
| 3 | [Backup & Recovery](backup-recovery/) | [`Backup_and_Recovery.py`](backup-recovery/Backup_and_Recovery.py) | Checkpoints, snapshots, PITR |
| 4 | [Observability](observability/) | [`Observability_and_Monitoring.py`](observability/Observability_and_Monitoring.py) | `pg_stat`, indexes, monitoring |

---

## All labs (A–Z inventory)

Numbered for the workshop validator and facilitators. Prefer the **track tables** above when choosing what to run.

| # | Path | Folder | What You'll Explore |
|---|------|--------|---------------------|
| 1 | [Data Operations](data-operations/) | `data-operations/` | CRUD, JSONB, arrays, audit triggers, transactions, advanced SQL |
| 2 | [Reverse ETL](reverse-etl/) | `reverse-etl/` | Sync Delta Lake tables into Lakebase for low-latency serving |
| 3 | [Unity Catalog Access](unity-catalog-access/) | `unity-catalog-access/` | Register Postgres as a federated read-only UC catalog for Lakehouse SQL |
| 4 | [Lakehouse Sync](lakehouse-sync/) *(Public Preview)* | `lakehouse-sync/` | Sync Lakebase → Unity Catalog Delta via Lakebase Change Data Feed (CDC change history) |
| 5 | [Development Experience](development-experience/) | `development-experience/` | Git-like branching, autoscaling compute, scale-to-zero, high availability + read replicas |
| 6 | [Observability](observability/) | `observability/` | pg_stat views, index analysis, connection monitoring |
| 7 | [Authentication, Security & Compliance](authentication/) | `authentication/` | OAuth tokens, two-layer permissions, role grants, encryption/CMK, Private Link, compliance profiles |
| 8 | [Backup & Recovery](backup-recovery/) | `backup-recovery/` | Checkpoint branches, snapshots, point-in-time restore |
| 9 | [Agentic Memory](agentic-memory/) | `agentic-memory/` | Persistent AI agent memory with session/message storage |
| 10 | [Online Feature Store](online-feature-store/) | `online-feature-store/` | Real-time ML feature serving powered by Lakebase Autoscaling |
| 11 | [App Deployment](app-deployment/) | `app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |
| 12 | [Data API](data-api/) | `data-api/` | PostgREST REST access with an `authenticator` role, OAuth bearer tokens, and row-level security |
| 13 | [Lakebase Search](lakebase-search/) *(Beta)* | `lakebase-search/` | Vector (ANN) + keyword (BM25) search and hybrid RRF ranking with `lakebase_vector` / `lakebase_text` |

## Path Dependencies

Most paths only require the foundation. Soft recommendations:

```
Foundation (00_Setup)
    │
    ├── Data Operations ──(recommended before)──► Observability
    ├── Reverse ETL
    ├── Unity Catalog Access (needs CREATE CATALOG + Serverless SQL warehouse)
    ├── Lakehouse Sync (Public Preview — UI-configured, no notebook yet)
    ├── Development Experience
    │       ├── 1. Branches_and_Environments
    │       ├── 2. Autoscaling_and_Compute
    │       └── 3. High_Availability_and_Replicas
    ├── Authentication, Security & Compliance
    ├── Backup & Recovery
    ├── Agentic Memory ──(optional next)──► Lakebase Search
    ├── Online Feature Store (requires DBR 16.4 LTS ML or serverless)
    ├── App Deployment (best after exploring other paths)
    ├── Data API (pairs with Data Operations)
    └── Lakebase Search (Beta — enablement is irreversible; opt-in per project)
```

## Connecting & Querying Lakebase

Before diving into a lab, it helps to know the ways you can connect to and query your Lakebase database. You'll use one or more of these across the labs.

### What to use when (simplest path)

| Goal | Recommended approach |
|------|----------------------|
| Run a workshop lab notebook | Shared `get_connection()` helper — Databricks SDK OAuth + `psycopg` + `sslmode=require` (already wired in `%run ../_setup`) |
| Ad-hoc SQL / `Advanced_Postgres.sql` | **[Lakebase SQL Editor](https://docs.databricks.com/aws/en/oltp/projects/sql-editor)** in the Lakebase App (no local client or token refresh) |
| Live Lakehouse SQL over Postgres (federated, read-only) | **[Register in Unity Catalog](unity-catalog-access/)** then query from the SQL Editor with a **Serverless** warehouse |
| psql, pgAdmin, DBeaver, DataGrip | **[Native Postgres password](https://docs.databricks.com/aws/en/oltp/projects/postgres-clients)** role from the Connect dialog (OAuth expires hourly — impractical for interactive tools) |
| Long-running / high-concurrency apps | App-side pool with OAuth token rotation, **or** password role + built-in **[PgBouncer](https://docs.databricks.com/aws/en/oltp/projects/connection-pooling)** (`-pooler` hostname, still port `5432`) |

### Connection Methods

| Method | Best For | Details |
|--------|----------|---------|
| **[Databricks SDK (OAuth)](https://docs.databricks.com/aws/en/oltp/projects/authentication)** | Notebooks, apps, automated pipelines | Short-lived OAuth tokens (1-hour TTL) via `generate_database_credential`. Used by most labs. Open connections stay alive after token expiry; new logins need a fresh token. |
| **[Postgres passwords](https://docs.databricks.com/aws/en/oltp/projects/authentication)** | Interactive Postgres clients, tools that cannot refresh hourly | Native password roles (passwords don't expire). **Disabled by default** on new projects — enable under project Settings → Database connections, then create a password role in Roles & Databases. |
| **[Connection strings](https://docs.databricks.com/aws/en/oltp/projects/connection-strings)** | Any standard Postgres driver | `postgresql://…?sslmode=require` (SSL required). Copy from the Lakebase App **Connect** dialog. |
| **[Connection pooling (PgBouncer)](https://docs.databricks.com/aws/en/oltp/projects/connection-pooling)** | High-concurrency apps with password auth | Built-in pooler — use the **`-pooler`** hostname from Connect (port stays **5432**). Password roles only; not available with OAuth. Transaction mode does not persist `SET search_path` across transactions. |
| **[Framework examples](https://docs.databricks.com/aws/en/oltp/projects/framework-examples)** | Python, JavaScript, .NET, Go | Ready-to-use snippets (examples use password auth; OAuth needs token rotation). |
| **[Connect an application](https://docs.databricks.com/aws/en/oltp/projects/connect-application)** | Databricks Apps, external services | Patterns for apps using standard Postgres drivers. |
| **[Data API (HTTP/REST)](https://docs.databricks.com/aws/en/oltp/projects/data-api)** | Lightweight clients, no driver needed | PostgREST-compatible REST over HTTPS. |
| **[Private Link](https://docs.databricks.com/aws/en/oltp/projects/private-link)** | Enterprise / private network | Two endpoints: inbound Private Link for API access and for Postgres connections. |

### Query Methods

| Method | Best For | Details |
|--------|----------|---------|
| **[Lakebase SQL Editor](https://docs.databricks.com/aws/en/oltp/projects/sql-editor)** | Interactive Postgres queries | Web editor in the Lakebase App — simplest path for SQL-only labs (`EXPLAIN`/`ANALYZE`, meta-commands). Set `search_path` to your user schema first. |
| **[SQL Editor (Lakehouse)](https://docs.databricks.com/aws/en/oltp/projects/query-sql-editor)** | Visualizations, dashboards, collaboration | Connect directly to Lakebase compute (read-write) or via Unity Catalog (federated read-only). See [Unity Catalog Access](unity-catalog-access/). |
| **[Tables editor](https://docs.databricks.com/aws/en/oltp/projects/table-editor)** | Visual data management | Browse and edit schemas/data in the UI. |
| **[Postgres clients](https://docs.databricks.com/aws/en/oltp/projects/postgres-clients)** (psql, [pgAdmin](https://docs.databricks.com/aws/en/oltp/projects/connect-pgadmin), [DBeaver](https://docs.databricks.com/aws/en/oltp/projects/connect-dbeaver)) | Local development | Prefer a **password** role from Connect; OAuth works but needs hourly refresh. |
| **[Point-in-time queries](https://docs.databricks.com/aws/en/oltp/projects/point-in-time-branching)** | Debugging, auditing, time-travel | Historical branches for past database state. |

> **Tip:** Workshop notebooks use the **Databricks SDK (OAuth) + psycopg** path on purpose — no password setup, no client install. For SQL-only exploration, prefer the **Lakebase SQL Editor**. For desktop clients, prefer a **native Postgres password** role.

For the full reference, see: [Connect to your database](https://docs.databricks.com/aws/en/oltp/projects/connect) | [Query your data](https://docs.databricks.com/aws/en/oltp/projects/query-data)

## Suggested Combinations

| Goal | Paths |
|------|-------|
| **Quick overview (30 min)** | Development Experience |
| **Data-focused (60 min)** | Data Operations → Observability |
| **App builder (60 min)** | Data Operations → Data API → Agentic Memory → App Deployment |
| **AI search (45 min)** | Agentic Memory → Lakebase Search *(Beta)* |
| **ML serving (45 min)** | Reverse ETL → Online Feature Store |
| **Lakehouse connectivity (45 min)** | Unity Catalog Access → Reverse ETL → Lakehouse Sync *(Public Preview)* |
| **Bi-directional sync (45 min)** | Reverse ETL → Lakehouse Sync *(Public Preview)* |
| **Platform deep-dive (90 min)** | Development Experience → Authentication → Backup & Recovery → Observability |
| **Full workshop (2.5 hours)** | All paths |
