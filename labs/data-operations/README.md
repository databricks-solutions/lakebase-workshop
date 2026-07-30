# Data Operations

Work with PostgreSQL's full feature set: CRUD, JSONB documents, array operators, audit triggers, and transactions.

## Labs

| Order | Lab | What You'll Learn |
|-------|-----|-------------------|
| 1 | `Data_Operations` | JSONB queries, array filtering, CRUD with audit trail, transactions |
| 2 | `Advanced_Postgres.sql` | CTEs, window functions, advanced JSONB operators, system metadata queries |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)

## Key Concepts

- **JSONB** — Store and query semi-structured data with GIN indexes
- **Array operators** — Filter using `ANY`, `&&`, `@>` on array columns
- **Audit triggers** — Automatic change tracking via `AFTER` triggers
- **Transactions** — Full ACID guarantees with `BEGIN`/`COMMIT`/`ROLLBACK`

## Documentation

- [SQL Editor](https://docs.databricks.com/aws/en/oltp/projects/sql-editor)
- [Postgres clients](https://docs.databricks.com/aws/en/oltp/projects/postgres-clients)

## Notes

`Advanced_Postgres.sql` is a standalone SQL file — run it via `psql`, a SQL client, or the API Tester in the Lab Console app.
