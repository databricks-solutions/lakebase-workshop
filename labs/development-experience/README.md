# Development Experience

Explore Lakebase's developer-focused features: Git-like database branching, autoscaling serverless compute, and compute resilience (high availability + read replicas).

> **Layout note:** This is the only lab folder with **three notebooks**. Run them in order (1 → 2 → 3). Every other workshop topic is a single notebook in its own folder — see [`labs/README.md`](../README.md).

## What to run

| Order | Open this | What You'll Learn |
|-------|-----------|-------------------|
| 1 | [`Branches_and_Environments.py`](Branches_and_Environments.py) | Create isolated dev branches, verify schema isolation, set branch TTLs |
| 2 | [`Autoscaling_and_Compute.py`](Autoscaling_and_Compute.py) | Inspect CU ranges, resize endpoints, understand scale-to-zero |
| 3 | [`High_Availability_and_Replicas.py`](High_Availability_and_Replicas.py) | Multi-AZ failover, `-ro` read routing, read replicas, HA + autoscaling constraints |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)

## Key Concepts

- **Copy-on-write branching** — Instant, isolated database clones for dev/test/CI
- **Autoscaling compute** — Autoscales up to 64 CU (2 GB RAM/CU, max−min spread ≤ 16 CU); computes above 64 CU are fixed-size
- **Scale-to-zero** — Non-production branches suspend when idle (no cost); not available on HA
- **Branch TTL** — Auto-expire dev branches after a configurable duration
- **High availability** — Primary + 1–3 secondaries across AZs; automatic failover; unchanged connection string
- **Read replicas** — Independent read-only computes (up to 6/branch) that read from the same storage, scale-to-zero-capable

## Documentation

- [Branches](https://docs.databricks.com/aws/en/oltp/projects/branches)
- [Manage branches](https://docs.databricks.com/aws/en/oltp/projects/manage-branches)
- [Autoscaling](https://docs.databricks.com/aws/en/oltp/projects/autoscaling)
- [Scale to zero](https://docs.databricks.com/aws/en/oltp/projects/scale-to-zero)
- [High availability](https://docs.databricks.com/aws/en/oltp/projects/high-availability)
- [Read replicas](https://docs.databricks.com/aws/en/oltp/projects/read-replicas)
- [Manage computes](https://docs.databricks.com/aws/en/oltp/projects/manage-computes)
