# Observability & Monitoring

Monitor your Lakebase database using built-in PostgreSQL statistics views and the workspace monitoring UI.

## Labs

| Lab | What You'll Learn |
|-----|-------------------|
| `Observability_and_Monitoring` | `pg_stat_user_tables`, index usage analysis, connection monitoring, cache hit ratios |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)
- **Recommended:** Run the **Data Operations** path first for richer statistics

## Key Concepts

- **pg_stat views** — Built-in PostgreSQL statistics for tables, indexes, and connections
- **Cache hit ratio** — Measure buffer cache effectiveness
- **Index analysis** — Identify unused or redundant indexes
- **Slow query detection** — Find long-running queries via `pg_stat_activity`

## Documentation

- [Monitor](https://docs.databricks.com/aws/en/oltp/projects/monitor)
- [Monitor with pg_stat_statements](https://docs.databricks.com/aws/en/oltp/projects/pg-stat-statements)
- [Metrics dashboard](https://docs.databricks.com/aws/en/oltp/projects/metrics)
