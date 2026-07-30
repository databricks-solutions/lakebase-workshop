# Backup & Recovery

Explore Lakebase's built-in backup architecture: instant branch snapshots and point-in-time recovery.

## Labs

| Lab | What You'll Learn |
|-----|-------------------|
| `Backup_and_Recovery` | Create snapshot branches, simulate data loss, recover via branching, PITR concepts |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)

## Key Concepts

- **Always-on backups** — Continuous backup with no configuration needed
- **Branch snapshots** — Instant, named copies of your database state
- **Point-in-time recovery (PITR)** — Restore to any moment within a configurable window (up to 30 days)
- **Recovery via branching** — Create a new branch from any point in time, no downtime

## Documentation

- [Point-in-time restore](https://docs.databricks.com/aws/en/oltp/projects/point-in-time-restore)
- [Branches](https://docs.databricks.com/aws/en/oltp/projects/branches)
- [Manage branches](https://docs.databricks.com/aws/en/oltp/projects/manage-branches)
