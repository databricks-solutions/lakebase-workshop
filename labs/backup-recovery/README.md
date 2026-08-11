# Backup & Recovery

Explore Lakebase's built-in backup architecture: checkpoint branches, managed snapshots, and point-in-time restore.

## Labs

| Lab | What You'll Learn |
|-----|-------------------|
| `Backup_and_Recovery` | Create checkpoint branches, simulate data loss, recover via branching, how snapshots and PITR differ |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)

## Key Concepts

- **Always-on backups** — Continuous backup with no configuration needed
- **Checkpoint branches** — Instant, named copy-on-write branches you create yourself as restore points. Scriptable via the SDK/CLI, which is why the hands-on exercise uses them.
- **Snapshots** — The managed backup feature: a point-in-time capture of a *root* branch, created manually or on a schedule from **Backup & Restore** in the Lakebase App. No SDK or CLI surface today.
- **Point-in-time restore (PITR)** — Restore to any second within a configurable window (up to 30 days)
- **Recovery is always "branch and re-point"** — snapshots and PITR both produce a *new* branch rather than modifying the damaged one, so you can verify before cutting over

> Checkpoint branches and snapshots both give you a restore point, but they are different objects with different limits and billing. The lab spells out the differences.

## Documentation

- [Backup and restore methods](https://docs.databricks.com/aws/en/oltp/projects/backup-methods)
- [Snapshots](https://docs.databricks.com/aws/en/oltp/projects/snapshots)
- [Point-in-time restore](https://docs.databricks.com/aws/en/oltp/projects/point-in-time-restore)
- [Branches](https://docs.databricks.com/aws/en/oltp/projects/branches)
- [Manage branches](https://docs.databricks.com/aws/en/oltp/projects/manage-branches)
