# Lab Paths

After completing the **foundation** (`notebooks/00_Setup_Lakebase_Project`), choose any of these paths based on your interest. Each path is independent — pick one, pick several, or do them all.

## Available Paths

Ordered from foundational to advanced:

| # | Path | Folder | What You'll Explore |
|---|------|--------|---------------------|
| 1 | [Data Operations](data-operations/) | `data-operations/` | CRUD, JSONB, arrays, audit triggers, transactions, advanced SQL |
| 2 | [Reverse ETL](reverse-etl/) | `reverse-etl/` | Sync Delta Lake tables into Lakebase for low-latency serving |
| 3 | [Lakehouse Sync](lakehouse-sync/) *(Public Preview)* | `lakehouse-sync/` | Sync Lakebase → Unity Catalog Delta via Lakebase Change Data Feed (CDC change history) |
| 4 | [Development Experience](development-experience/) | `development-experience/` | Git-like branching, autoscaling compute, scale-to-zero |
| 5 | [Observability](observability/) | `observability/` | pg_stat views, index analysis, connection monitoring |
| 6 | [Authentication](authentication/) | `authentication/` | OAuth tokens, two-layer permissions, role grants |
| 7 | [Backup & Recovery](backup-recovery/) | `backup-recovery/` | Point-in-time recovery, branch snapshots, instant restore |
| 8 | [Agentic Memory](agentic-memory/) | `agentic-memory/` | Persistent AI agent memory with session/message storage |
| 9 | [Online Feature Store](online-feature-store/) | `online-feature-store/` | Real-time ML feature serving powered by Lakebase Autoscaling |
| 10 | [App Deployment](app-deployment/) | `app-deployment/` | Full-stack React + FastAPI app using Lakebase (capstone) |

## Path Dependencies

Most paths only require the foundation. A few have soft recommendations:

```
Foundation (00_Setup)
    │
    ├── 1. Data Operations
    │       └── (recommended before) 5. Observability
    ├── 2. Reverse ETL
    ├── 3. Lakehouse Sync (Public Preview — UI-configured, no notebook yet)
    ├── 4. Development Experience
    ├── 6. Authentication
    ├── 7. Backup & Recovery
    ├── 8. Agentic Memory
    ├── 9. Online Feature Store (requires DBR 16.4 LTS ML or serverless)
    └── 10. App Deployment (best after exploring other paths)
```

## Connecting & Querying Lakebase

Before diving into a lab, it helps to know the ways you can connect to and query your Lakebase database. You'll use one or more of these across the labs.

### Connection Methods

| Method | Best For | Details |
|--------|----------|---------|
| **[Databricks SDK (OAuth)](https://docs.databricks.com/aws/en/oltp/projects/authentication)** | Notebooks, apps, automated pipelines | Generate short-lived OAuth tokens (1-hour TTL) via the SDK. Used by most labs in this workshop. |
| **[Postgres passwords](https://docs.databricks.com/aws/en/oltp/projects/authentication)** | Quick local connections, external tools | Create a password-based Postgres role for tools that don't support OAuth. |
| **[Connection strings](https://docs.databricks.com/aws/en/oltp/projects/connection-strings)** | Any standard Postgres driver | Standard `postgresql://` URI format. Works with psycopg, SQLAlchemy, JDBC, and any Postgres-compatible driver. |
| **[Connection pooling (PgBouncer)](https://docs.databricks.com/aws/en/oltp/projects/connection-pooling)** | High-concurrency apps | Built-in PgBouncer pooler reduces connection overhead. Append port `6543` to your connection string. |
| **[Framework examples](https://docs.databricks.com/aws/en/oltp/projects/framework-examples)** | Python, JavaScript, .NET, Go | Ready-to-use code snippets for popular languages and frameworks. |
| **[Connect an application](https://docs.databricks.com/aws/en/oltp/projects/connect-application)** | Databricks Apps, external services | Patterns for connecting Databricks Apps or external applications using standard Postgres drivers. |
| **[Data API (HTTP/REST)](https://docs.databricks.com/aws/en/oltp/projects/data-api)** | Lightweight clients, no driver needed | PostgREST-compatible REST interface — query your database over HTTP without a Postgres driver. |
| **[Private Link](https://docs.databricks.com/aws/en/oltp/projects/private-link)** | Enterprise / private network | Requires two endpoints: inbound Private Link for API access and inbound Private Link for Postgres connections. |

### Query Methods

| Method | Best For | Details |
|--------|----------|---------|
| **[Lakebase SQL Editor](https://docs.databricks.com/aws/en/oltp/projects/sql-editor)** | Interactive Postgres queries | Web-based editor in the Lakebase App. Supports Postgres-native features like `EXPLAIN`/`ANALYZE` and meta-commands. |
| **[SQL Editor (Lakehouse)](https://docs.databricks.com/aws/en/oltp/projects/query-sql-editor)** | Visualizations, dashboards, collaboration | Connect directly to Lakebase compute (full read-write) or register in Unity Catalog (read-only federated queries). |
| **[Tables editor](https://docs.databricks.com/aws/en/oltp/projects/table-editor)** | Visual data management | Browse, edit, and manage data and schemas through an interactive UI. |
| **[Postgres clients](https://docs.databricks.com/aws/en/oltp/projects/postgres-clients)** (psql, [pgAdmin](https://docs.databricks.com/aws/en/oltp/projects/connect-pgadmin), [DBeaver](https://docs.databricks.com/aws/en/oltp/projects/connect-dbeaver)) | Local development, ad-hoc queries | Any standard PostgreSQL client works — connect with OAuth tokens or Postgres passwords. |
| **[Point-in-time queries](https://docs.databricks.com/aws/en/oltp/projects/point-in-time-branching)** | Debugging, auditing, time-travel | Query your database as it existed at any past moment using historical branches. |

> **Tip:** The labs in this workshop primarily use the **Databricks SDK** for connections (OAuth tokens generated in notebook cells) and **psycopg** as the Postgres driver. If you prefer a different method, the patterns above all work with Lakebase Autoscaling.

For the full reference, see: [Connect to your database](https://docs.databricks.com/aws/en/oltp/projects/connect) | [Query your data](https://docs.databricks.com/aws/en/oltp/projects/query-data)

## Tracks by Role

Pick a track based on your role, or mix and match across tracks. Every lab is independent.

| Track | Who It's For | Labs (in recommended order) |
|-------|-------------|----------------------------|
| **Application Builders** | App developers, AI engineers | Data Operations → Agentic Memory → App Deployment |
| **Data & ML Engineers** | Data engineers, ML teams | Reverse ETL → Lakehouse Sync *(Public Preview)* → Online Feature Store |
| **Platform Architects** | Central IT, infrastructure, security | Development Experience → Authentication → Backup & Recovery → Observability |

## Suggested Combinations

| Goal | Paths |
|------|-------|
| **Quick overview (30 min)** | Development Experience |
| **Data-focused (60 min)** | Data Operations → Observability |
| **App builder (60 min)** | Data Operations → Agentic Memory → App Deployment |
| **ML serving (45 min)** | Reverse ETL → Online Feature Store |
| **Bi-directional sync (45 min)** | Reverse ETL → Lakehouse Sync *(Public Preview)* |
| **Platform deep-dive (90 min)** | Development Experience → Authentication → Backup & Recovery → Observability |
| **Full workshop (2.5 hours)** | All paths |
