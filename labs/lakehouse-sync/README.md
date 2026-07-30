# Lakehouse Sync (Lakebase Change Data Feed)

Sync data **from Lakebase back into the Lakehouse** — the inverse of Reverse ETL. Every insert, update, and delete on a Lakebase Postgres table is captured from the write-ahead log and written as a new row into a Unity Catalog–managed Delta table, giving you a complete, queryable change history in open format.

> **Status: Public Preview**
>
> This feature is officially **Lakebase Change Data Feed (CDF)**, powered by the `wal2delta` Postgres extension. Enablement and configuration are done **through the Lakebase app UI** (there is no create-API yet), so this lab is a **UI walkthrough** — there is no enablement notebook to run. The *downstream* consumption patterns, however, are fully runnable (see below). Follow the documentation links to enable the preview and try it in your workspace.

## Labs

| Lab | Status | What You'll Learn |
|-----|--------|-------------------|
| _UI walkthrough_ | Public Preview · UI-configured | Enable the preview, start a change data feed on a Lakebase schema, and observe the `lb_<table>_history` Delta tables in Unity Catalog |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)
- **Workspace admin** must enable the Lakebase Change Data Feed preview from the workspace **Previews** page
- Lakebase Autoscaling project running **Postgres 17**
- Tables to sync must reside in the `databricks_postgres` database
- Source tables must have **`REPLICA IDENTITY FULL`** set (`ALTER TABLE <table> REPLICA IDENTITY FULL;`)
- Unity Catalog permissions on the destination: `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE`
- `CAN MANAGE` permission on the Lakebase project being synced

## Key Concepts

- **Bi-directional data movement** — Pairs with **Synced Tables** (Reverse ETL) to move data both ways: Delta → Lakebase for serving, Lakebase → Delta for analytics
- **CDC change history** — Row-level inserts, updates, and deletes are captured continuously from Postgres and flushed to Delta about every ~15 seconds
- **Delta-CDF-style format** — Each destination table `lb_<table_name>_history` carries system columns: `_pg_change_type` (`insert`, `delete`, `update_preimage`, `update_postimage`), `_pg_lsn`, `_pg_xid`, `_timestamp`, and `_sort_by`. These are the same change semantics as Delta Change Data Feed, so the same downstream patterns apply. *(This is a change-event log, not a classic SCD Type 2 dimension — an update emits a preimage + postimage row pair.)*
- **No external pipelines** — Native Lakebase feature (the `wal2delta` extension runs inside the Lakebase compute); no external CDC tools required

## Use Cases

- **Fast analytics on operational data** — Run aggregates and joins on Lakebase-originated data without hitting Postgres
- **Medallion bronze source** — Use the change feed as a Bronze source for medallion architectures (SDP / Structured Streaming)
- **Full audit history** — Keep a complete, immutable time-series record of how operational data changed

## Downstream Consumption (runnable)

Enablement is UI-only, but once the `lb_<table>_history` tables exist you can consume them with standard tools:

- **SQL materialized view** over the history table (refreshes incrementally)
- **Spark Declarative Pipelines (SDP)** reading the history table with `readStream` for a bronze → silver → gold flow
- **Spark Structured Streaming** with `foreachBatch` for custom merges

See the doc's "Build downstream pipelines" section and the CDC ETL tutorial linked below for full examples.

## Documentation

- [Lakebase Change Data Feed (Public Preview)](https://docs.databricks.com/aws/en/oltp/projects/lakehouse-sync) — official docs, setup, and downstream patterns
- [Bi-directional data movement](https://docs.databricks.com/aws/en/oltp/projects/about) — how CDF pairs with Synced Tables
- [Reverse ETL (Synced Tables)](../reverse-etl/) — the inverse pattern, for context
- [Use Delta Lake change data feed](https://docs.databricks.com/aws/en/delta/delta-change-data-feed)

## Notes

- This lab will be expanded with a runnable enablement notebook if/when a create-API for Lakebase CDF ships. For now, use the Lakebase app UI (Branch overview → **Change Data Feed** tab) to start a feed and observe the resulting Delta tables in Unity Catalog.
- Inspect feed state from Postgres with `SELECT * FROM wal2delta.tables;`.
- See `docs/PERMISSIONS.md` for service principal grants if you intend to automate downstream consumption via a workflow.
