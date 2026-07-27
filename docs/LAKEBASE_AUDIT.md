# Lakebase Workshop — Audit & Revamp (v2)

**Date:** July 23, 2026 · **Supersedes** the July 9 audit (v1).

**Scope:** A currency + accuracy pass over the whole workshop against the July 2026 canon, plus a build plan for now-shipped features. Graded on **accuracy**, **simplicity**, and **best-practice implementation**. Every finding is tied to an explicit trusted source.

---

> ## Source-of-truth tiering (this pass)
>
> Ordered by the tiering the workshop owner anchored on. **Public product docs win on hard facts; internal canon wins on positioning / pricing / status.**
>
> 1. **Public Lakebase docs** — `https://docs.databricks.com/aws/en/oltp/projects/*`. Verified this pass (with doc dates): [autoscaling](https://docs.databricks.com/aws/en/oltp/projects/autoscaling) (Jun 23), [high-availability](https://docs.databricks.com/aws/en/oltp/projects/high-availability) (Jul 21), [read-replicas](https://docs.databricks.com/aws/en/oltp/projects/read-replicas) (Jun 23), [point-in-time-restore](https://docs.databricks.com/aws/en/oltp/projects/point-in-time-restore) (Jun 12), [authentication](https://docs.databricks.com/aws/en/oltp/projects/authentication) (Jun 24), [data-api](https://docs.databricks.com/aws/en/oltp/projects/data-api) (Jul 13), [lakebase-search](https://docs.databricks.com/aws/en/oltp/projects/lakebase-search) (Jun 16), [lakehouse-sync / CDF](https://docs.databricks.com/aws/en/oltp/projects/lakehouse-sync), [projects hub](https://docs.databricks.com/aws/en/oltp/projects/) (Jul 21).
> 2. **Public release notes** — [June 2026](https://docs.databricks.com/aws/en/release-notes/product/2026/june).
> 3. **Internal canon** — Lakebase FAQ (`go/lakebase/faq`), Roadmap (`go/lakebase/roadmap`), Security FAQ (`go/lakebase/autoscaling/security/faqs`).

---

## v1 status: shipped

All P0/P1/P2 fixes from v1 were implemented (restore window 35→30, synced-table grants, Lakehouse Sync→CDF/Public Preview, `wait_for_endpoint()` poll + retry, snapshot `no_expiry=True`, cleanup order, doc-link/terminology polish, resources retiering). This v2 layers a July currency pass on top.

---

## Verified fact resolutions (close prior open questions)

| Item | Resolution | Source |
|---|---|---|
| **Restore/history window** | **2–30 days, default 7.** Prior 35→30 fix confirmed correct; the internal FAQ/roadmap "35 days" lags. Keep 30. | point-in-time-restore doc |
| **Autoscaling CU model** | **max − min ≤ 16 CU; autoscaling up to 64 CU; 2 GB RAM/CU; fixed-size computes above 64 CU.** The v1 wording ("0.5–32 autoscaling / up to 112 fixed") is now wrong on all three counts. | autoscaling + high-availability docs |
| **Auth CLI subcommand** | Confirmed: `databricks postgres generate-database-credential projects/{p}/branches/{b}/endpoints/{e} --output json`. | authentication doc |
| **`expire_time` shape** | It is an **ISO-8601 timestamp string** (e.g. `"2026-01-22T17:07:00Z"`), **not** a protobuf with `.seconds`. Fixed the `credential.expire_time.seconds` usage in the authentication lab (now parses the ISO string / prefers the fresh-token `CustomConnection` pattern). | authentication doc |
| **PITR SDK field** | Confirmed: the `BranchSpec` field is **`source_branch_time`** (protobuf `Timestamp`), **not** `parent_timestamp`. Fixed in the backup-recovery lab and the app. Restore creates a **new root branch**; **max 3 root branches**. | SDK `dbdataclasses/postgres`, PITR doc |
| **OFS version pins** | Confirmed correct: **DBR 16.4 LTS ML or serverless** and **`databricks-feature-engineering>=0.13.0`**. No change needed. | Online Feature Store doc (Jul 7) |
| **Lakebase Search maturity** | Public doc says **Beta** (needs Previews-page access; enabling is **irreversible** and **restarts all computes**). The roadmap's "GA Jun 18" is ahead of the public doc — follow the public doc: **Beta**. | lakebase-search doc |
| **MCP server for Lakebase** | Not present in any canon. Correctly absent; do not add. | FAQ/roadmap/security FAQ |

---

## July currency deltas (new since v1)

| Delta | Impact on workshop | Where |
|---|---|---|
| **"Provisioned vs Autoscaling" is gone — it's just "Lakebase"** (all Provisioned upgraded by Jul 31, 2026) | Reposition branding to unified "Lakebase" (hybrid: keep "Autoscaling" only where docs/APIs use it) | README, labs/README, docs, app |
| **Snapshot storage now billed** (Jun 1, 2026); billing has separate data / PITR / snapshot components | Soften "backups are free / no config"; add a cost note | backup-recovery |
| **Postgres 18 supported** (17 still default) | Add a version note | 00_Setup |
| **Autoscaling ≤16 CU spread, up to 64 CU** | Re-ground CU model (see above) | development-experience + app |
| **Lakebase Search (Beta)** — `lakebase_vector` (ANN, pgvector-compatible) + `lakebase_text` (BM25) + hybrid RRF | New standalone lab | labs/lakebase-search |
| **Data API (PostgREST) GA** — `authenticator` role, OAuth bearer, RLS, no UC governance | New standalone lab | labs/data-api |
| **High Availability GA** (multi-AZ failover) + **Read Replicas** (up to 6/branch, scale-to-zero-capable) | New notebook in development-experience | labs/development-experience |
| **CMK GA**, **inbound Private Link GA**, **TLS 1.2+ / AES-256**, **compliance profiles** (HIPAA/C5/TISAX/SOC2 Type 2) | New Security & Compliance section | labs/authentication |
| **Managed agent memory (Beta, Jun 23)** — governed UC alternative to DIY Postgres memory | Positioning note (when-to-use-which) | labs/agentic-memory |
| **Connection limits**: 24-hour idle timeout, 3-day max connection life; PgBouncer requires password auth (not OAuth); password connections off by default | Add notes | labs/authentication |
| **Cross-region DR** (Beta/roadmap, Q2 FY27) | Forward-looking note only | labs/backup-recovery |

---

## Section A — Accuracy & currency fixes (existing labs)

- **development-experience / `Autoscaling_and_Compute.py`** — re-ground CU model: `max − min ≤ 16 CU`, autoscaling **up to 64 CU**, **2 GB/CU**, fixed-size computes above 64. Fix the header (v1's "0.5–32 / up to 112") and the in-notebook CU table. Add the HA interaction note (secondaries ≥ primary; scale-to-zero unavailable on HA). Propagate to app `AutoscaleDemo.jsx` / `ComputePage.jsx`.
- **backup-recovery / `Backup_and_Recovery.py`** — add **"snapshot storage is now billed" (Jun 1)** with the three billing components; add **max 3 root branches** (PITR creates a new root branch); reframe the PITR example to the documented UI "Backup & Restore" flow and flag the `parent_timestamp` SDK path; add a forward-looking **cross-region DR** note. Propagate to app `BackupRecoveryPage.jsx`.
- **00_Setup** — add **Postgres 18 supported (17 default)** and the unified-"Lakebase" positioning note.
- **agentic-memory / `Agent_Memory.py`** — add **Managed agent memory (Beta)** positioning callout (governed UC alternative; this lab teaches the DIY Lakebase-backed pattern — still valid for custom schema / low-latency control).
- **reverse-etl / `Reverse_ETL.py`** — reframe prose to the public term **"synced tables"** (internal canon avoids "Reverse ETL / Forward ETL / sync"); keep folder name; note the storage-quota context (16 TB synced-table quota; default instance storage rising to 32 TB).
- **authentication / `Authentication_and_Permissions.py`** — confirm CLI subcommand (done); correct any `expire_time.seconds` usage to the fresh-token `CustomConnection` pattern; add the 24h-idle / 3-day connection limits and the "PgBouncer needs password auth" note. Then extend with the Security & Compliance section (Section C).

## Section B — Positioning / naming (hybrid)

- Reposition top-level branding to **"Lakebase"** across [README.md](../README.md), [labs/README.md](../labs/README.md), [docs/WORKSHOP_FACILITATOR.md](WORKSHOP_FACILITATOR.md), and the app shell; add a short **"It's all one Lakebase now"** note (Provisioned upgraded by Jul 31, 2026).
- Keep **"Autoscaling"** only where public docs/URLs/APIs use it (`w.postgres.*`, doc links, the `oltp/projects` surface).
- Fix the stale `setup.sh` string that still prints lakehouse-sync as "(Beta, UI-only)".

## Section C — New content (2 new labs + 2 folds)

**Consolidation:** only genuinely-distinct, runnable features get their own lab; the rest land as grounded sections. Workshop grows **10 → 12 labs**.

- **New: `labs/lakebase-search/`** (runnable, gated) — enable Lakebase Search (Beta; **irreversible, restarts computes** — opt-in with warnings + a graceful "is it enabled?" guard), `CREATE EXTENSION lakebase_vector CASCADE` + `lakebase_text`, `lakebase_ann` (pgvector operators) + `lakebase_bm25` indexes, hybrid **RRF** query. Optional tie-in: semantic recall over `agent_memory_store`.
- **New: `labs/data-api/`** (runnable) — enable Data API (UI), `databricks_create_role` + `GRANT … TO authenticator` + `GRANT USAGE/SELECT`, OAuth bearer requests via `requests`/curl, **RLS** for row-level isolation, and the **"Data API does not use Unity Catalog governance"** + "don't use the owner account" caveats.
- **Fold: HA + Read Replicas → `development-experience`** as `High_Availability_and_Replicas.py` (compute-topology theme): multi-AZ failover, `-ro` secondary connection, read replicas (up to 6/branch, scale-to-zero-capable), autoscaling+HA constraints, SLA. Config is UI; runnable parts inspect endpoints / connect to `-ro`.
- **Fold: Security & Compliance → `authentication`** (rename to "Authentication, Security & Compliance"): CMK, inbound Private Link, TLS 1.2+, AES-256, per-project DEK/KEK, compliance profiles, and the "no Postgres audit logs yet — use `pg_stat_statements`" limitation.

## Section D — Resources retiering

- Update Resources in [README.md](../README.md), [labs/README.md](../labs/README.md), [docs/CREDITS.md](CREDITS.md) to the canon order: go/lakebase hub → public docs → FAQ → roadmap → Security FAQ → June 2026 release notes → per-feature docs.

---

## Open items still needing a live workshop workspace

These are gated on a live workspace and are flagged inline in the new labs rather than blocking authoring:

- **Lakebase Search enablement** in the target workspace (Beta access via Previews; irreversible; restarts computes) — confirm before a live run. The lab guards for this and skips gracefully if the extensions aren't installable.
- **HA / read-replica SDK surface** — docs describe UI configuration; no documented `w.postgres.*` path for *enabling* HA or *adding* replicas today, so the HA notebook is authored as a UI walkthrough + runnable inspection (list/get endpoints, connect). Revisit if an SDK surface ships.
- **Data API HTTP call as owner** — the owner identity can't call the Data API; the lab's HTTP section requires a non-owner/SP token + the API URL from the UI (both parameterized via widgets).

**Resolved since first draft of this plan:** PITR SDK field (`source_branch_time`), restore-window max (30 days, public doc over the SDK docstring's lagging 35), and OFS version pins (all confirmed above).

## Bottom line

The workshop remains accurate and current after the v1 fixes. This v2 pass corrects the **autoscaling CU model** (the one hard-fact regression), lands the **July positioning + billing/PG18 currency notes**, and adds **four now-shipped capabilities** (Search, Data API, HA/Read Replicas, Security & Compliance) as two new labs plus two grounded folds — growing the workshop to 12 labs without adding filler.
