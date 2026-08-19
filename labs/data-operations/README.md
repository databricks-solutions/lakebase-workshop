# Data Operations

Work with PostgreSQL's full feature set: CRUD, JSONB documents, array operators, audit triggers, and transactions.

## What to run

| Order | Open this | What You'll Learn |
|-------|-----------|-------------------|
| 1 | [`Data_Operations.py`](Data_Operations.py) | JSONB queries, array filtering, CRUD with audit trail, transactions |
| 2 | [`Advanced_Postgres.sql`](Advanced_Postgres.sql) | CTEs, window functions, advanced JSONB operators, system metadata queries |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)

## Key Concepts

- **JSONB** — Store and query semi-structured data with GIN indexes
- **Array operators** — Filter using `ANY`, `&&`, `@>` on array columns
- **Audit triggers** — Automatic change tracking via `AFTER` triggers
- **Transactions** — Full ACID guarantees with `BEGIN`/`COMMIT`/`ROLLBACK`

## Documentation

- [Connect to your database](https://docs.databricks.com/aws/en/oltp/projects/connect)
- [SQL Editor](https://docs.databricks.com/aws/en/oltp/projects/sql-editor)
- [Postgres clients](https://docs.databricks.com/aws/en/oltp/projects/postgres-clients)

## Notes

- **`Data_Operations`** uses the shared OAuth + `psycopg` helper (simplest for notebooks).
- **`Advanced_Postgres.sql`** — prefer the [Lakebase SQL Editor](https://docs.databricks.com/aws/en/oltp/projects/sql-editor). Set `search_path` to your user schema first. For desktop clients, use a [native Postgres password](https://docs.databricks.com/aws/en/oltp/projects/postgres-clients) role from **Connect** (not hourly OAuth). You can also paste statements into the Lab Console API Tester.
