# Lakehouse Sync

Sync data **from Lakebase back into the Lakehouse** — the inverse of Reverse ETL. Continuously replicate Lakebase Postgres tables into Unity Catalog–managed Delta tables, capturing row-level changes via CDC and preserving a full SCD Type 2 history.

> **Status: Beta (placeholder lab)**
>
> Lakehouse Sync is currently in Beta and is configured **through the workspace UI**. The SDK/API surface is not yet generally available, so this lab is provided as a placeholder — there is no notebook to run yet. Follow the documentation links below to enable the preview and try it in your workspace.

## Labs

| Lab | Status | What You'll Learn |
|-----|--------|-------------------|
| _Coming soon_ | Beta · UI-only | Enable the preview, configure a sync from Lakebase → Unity Catalog, observe SCD Type 2 history in Delta |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)
- **Workspace admin** must enable Lakehouse Sync from the workspace **Previews** page
- Lakebase Autoscaling project running **Postgres 17**
- Tables to sync must reside in the `databricks_postgres` database
- Source tables must have **`REPLICA IDENTITY FULL`** set
- Unity Catalog permissions on the destination: `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE`
- `CAN MANAGE` permission on the Lakebase project being synced

## Key Concepts

- **Bi-directional sync** — Pairs with **Synced Tables** (Reverse ETL) to move data both ways: Delta → Lakebase for serving, Lakebase → Delta for analytics
- **CDC capture** — Row-level inserts, updates, and deletes are captured continuously from Postgres
- **SCD Type 2 history** — Each change is appended to the destination Delta table as a new row, preserving full history of how data evolved
- **No external pipelines** — Native Lakebase feature; no Lakeflow Jobs, no external CDC tools, no separate compute

## Use Cases

- **Fast analytics on operational data** — Run aggregates and joins on Lakebase-originated data without hitting Postgres
- **Medallion source** — Use Lakebase as a Bronze source for medallion architectures
- **Full audit history** — Keep a complete time-series record of how operational data changed

## Documentation

- [Lakehouse Sync (Beta)](https://docs.databricks.com/aws/en/oltp/projects/lakehouse-sync) — official docs and UI walkthrough
- [Bi-directional data movement](https://docs.databricks.com/aws/en/oltp/projects/about) — how Lakehouse Sync pairs with Synced Tables
- [Reverse ETL (Synced Tables)](../reverse-etl/) — the inverse pattern, for context
- [Use Delta Lake change data feed](https://docs.databricks.com/aws/en/delta/delta-change-data-feed)

## Notes

- This lab will be expanded with a runnable notebook once the SDK/API for Lakehouse Sync is publicly available. For now, use the workspace UI to configure a sync and observe the resulting Delta tables in Unity Catalog.
- See `docs/PERMISSIONS.md` for service principal grants if you intend to automate the sync via a workflow once the API ships.
