# Lakebase Workshop — Accuracy & Best-Practice Audit

**Scope:** Per-lab correctness audit of the Lakebase Autoscaling workshop, graded on **accuracy**, **simplicity**, and **best-practice implementation**. Every finding is tied to an explicit trusted source.

**What was audited:** the foundation notebook + shared connection code, all 10 lab paths, the seed script, and the Lab Console app connection layer.

---

> ## ✅ Implementation status (updated)
>
> The audit findings below have now been **implemented**. Applied fixes:
>
> - **P0 — restore window 35 → 30 days** across `backup-recovery/Backup_and_Recovery.py` and `notebooks/00_Setup_Lakebase_Project.py`.
> - **P0 — synced-table grants** rewritten in `reverse-etl/Reverse_ETL.py` Part 5 and `docs/PERMISSIONS.md` to the documented `databricks_superuser` `GRANT USAGE/SELECT` + `databricks_synced_table_add_manager()` pattern (synced tables are owned by `databricks_writer_`).
> - **P0 — Lakehouse Sync status: VERIFIED.** The feature is now **Public Preview** and officially named **Lakebase Change Data Feed (CDF)** (powered by `wal2delta`). Relabeled *Beta → Public Preview* everywhere; corrected the "SCD Type 2" framing to a Delta-CDF-style change log (`lb_<table>_history`, `_pg_change_type`) in the lakehouse-sync README, `labs/README.md`, `README.md`, `notebooks/00_Setup`, `reverse-etl`, and `docs/WORKSHOP_FACILITATOR.md`. Enablement is still UI-configured (no create-API), so the lab remains a UI walkthrough, now with accurate runnable downstream-consumption guidance.
> - **P1 — fixed `sleep(10)` → poll:** added `wait_for_endpoint()` + connect-retry to `labs/_setup.py`; branch labs (`development-experience`, `backup-recovery`) now poll for `ACTIVE`.
> - **P1 — snapshot branch** now sets `no_expiry=True` explicitly; **cleanup order** fixed to delete child (`RECOVERY`) before parent (`SNAPSHOT`).
> - **P2 — polish:** feature-store SQL-editor link `oltp/instances` → `oltp/projects`; "Declarative Automation Bundle" → "Databricks Asset Bundle"; autoscale header clarified (0.5–32 autoscale / up to 112 fixed); timing wording aligned to "2–3 min"; top-level README Resources retiered to the canon.
>
> **Not changed (still needs live verification):** the PITR SDK example (`parent_timestamp` field / new-root-branch semantics), the Authentication CLI subcommand name and `expire_time.seconds` shape, and the feature-store DBR/`databricks-feature-engineering` version pins. These are markdown examples with low blast-radius; confirm against a live workspace before altering.

---

## Trusted sources used (source of truth)

Findings are graded against these, in priority order:

1. **Public Lakebase Autoscaling docs** — `https://docs.databricks.com/aws/en/oltp/projects/*`. Specifically verified this pass:
   - [Serve lakehouse data with synced tables](https://docs.databricks.com/aws/en/oltp/projects/sync-tables) *(updated Jul 2, 2026)*
   - [Point-in-time restore](https://docs.databricks.com/aws/en/oltp/projects/point-in-time-restore) *(updated Jun 12, 2026)*
   - [Manage branches](https://docs.databricks.com/aws/en/oltp/projects/manage-branches) *(updated Jun 29, 2026)*
2. **Curated Databricks Lakebase skills** — `databricks-lakebase-autoscale` (`projects.md`, `branches.md`, `computes.md`, `connection-patterns.md`, `reverse-etl.md`).

> **Important calibration:** where the curated skills and the live public docs disagree, **the live public docs win** — they are more recent. This audit found the workshop is in several places *more current than the skills* (see Reverse ETL), and in one place *behind the live docs* (the 35-day restore-window claim).

---

## Method

For each lab: (1) identify the governing trusted doc, (2) diff the lab's code/claims against it, (3) grade three axes — **Accuracy** (does the API/number/wording match the doc?), **Simplicity** (is it the simplest correct pattern?), **Best practice** (token refresh, retry-on-wake, `sslmode=require`, pooling, idempotency, least-privilege, cleanup).

---

## Headline results

**The workshop is in very good shape.** The SDK surface (`w.postgres.*`), Postgres 17, OAuth credential flow, CU/connection tables, branching, and scale-to-zero behavior all match the current docs. Several labs are *more current than the curated skills*. The issues below are concentrated in a small number of concrete, fixable items.

| Severity | Count | Theme |
|---|---|---|
| **P0 — accuracy** | 3 | 35-day restore window (should be 30); synced-table SP grant won't work as written; Lakehouse Sync status/label needs verification |
| **P1 — best practice / robustness** | 4 | Fixed `sleep(10)` for branch endpoints; snapshot branch missing explicit `no_expiry`; backup cleanup order; PITR SDK example unverified |
| **P2 — polish** | 6 | Doc-link nits, terminology, timing-claim consistency, app config modernization, autoscale CU wording, resource retiering |

---

# Section A — Per-lab scorecard

Legend: ✅ accurate / good · ⚠️ needs fix · 🔎 verify against live workspace.

## Foundation — `notebooks/00_Setup_Lakebase_Project.py`, `labs/_setup.py`, `bootstrap/seed.sql`, `setup.sh`
**Anchor docs:** *Projects* (`projects.md`), *Connection patterns* (`connection-patterns.md`).

- **Accuracy** ✅ `create_project(Project(spec=ProjectSpec(display_name, pg_version="17")))` matches `projects.md` exactly. Endpoint polling (`list_endpoints` → `get_endpoint` → check `current_state` contains `ACTIVE`) is correct. `generate_database_credential(endpoint=…)` and `sslmode=require` correct. Timeout math is right (90 × 5 s = 7.5 min, matches the printed message).
- **Simplicity** ✅ Clean. `_ensure_schema()` self-healing (detect missing tables, re-seed) is a nice touch that makes labs order-independent.
- **Best practice** ✅ Project-create is idempotent (get-first, create-on-miss). Seed is idempotent (`CREATE … IF NOT EXISTS`, `WHERE NOT EXISTS`, `DROP TRIGGER IF EXISTS`). SP-grant handles `already exists` with rollback. Fresh token per connection is correct for notebooks.
- ⚠️ **P2 (consistency):** timing claims disagree — setup Step 2 says "1-3 minutes", `README.md` troubleshooting says "2-3 minutes", the endpoint loop tolerates 7.5 min. Pick one phrasing ("typically 2-3 min, up to ~7").
- 🔎 **Minor (DRY):** `_setup.py` keeps an embedded `_REPAIR_SQL` copy of the schema that must stay in sync with `bootstrap/seed.sql`. It prefers reading the file first (good), but the duplicate can drift. Optional: derive both from the file only.

## data-operations — `labs/data-operations/Data_Operations.py`
**Anchor docs:** *Connect / query*, SQL editor / Postgres clients.

- **Accuracy** ✅ JSONB (`@>`, `->>`, `||`), array operators (`ANY`, `&&`), `RETURNING`, `pg_stat_database` cache-hit math — all correct, idiomatic Postgres.
- **Simplicity** ✅ Well-sequenced CRUD → audit → transaction → stats.
- **Best practice** ✅ Uses explicit transactions and `conn.commit()`. ⚠️ **P2 (teaching):** the table-size query interpolates `PG_SCHEMA` via f-string. It's *safe* (the value derives from the authenticated user's email, not user input), but since this is a teaching asset, a one-line note "prefer parameterized queries; this identifier is trusted" would model the right habit.

## reverse-etl — `labs/reverse-etl/Reverse_ETL.py`
**Anchor doc:** [Serve lakehouse data with synced tables](https://docs.databricks.com/aws/en/oltp/projects/sync-tables).

- **Accuracy** ✅ **Verified against the live doc and the workshop is correct — the curated skill is stale.** The notebook's numbers match the current doc:
  - Throughput: notebook "~150 rows/sec (incremental) / ~2,000 rows/sec (snapshot) per CU" → doc: *"approximately 150 rows per second per CU … Snapshot writes at up to 2,000 rows per second per CU."* ✅ (The `reverse-etl.md` skill still says 1,200 / 15,000 — **outdated**.)
  - Size quota: notebook "16 TB across all synced tables" → doc: *"16 TB quota."* ✅ (Skill says 2 TB — **outdated**.)
  - 16 connections per synced table, Snapshot 10× efficiency >10%, Triggered <5 min expensive, Continuous ≥15 s — all ✅.
  - `w.postgres.create_synced_table(SyncedTable(spec=SyncedTableSyncedTableSpec(...)))` is the **autoscaling-native** API and is consistent with the whole workshop. (The skill's `w.database.create_synced_database_table` is the older namespace.)
- ⚠️ **P0 (accuracy — grants):** Part 5 tells users to grant the app SP access to synced tables with `GRANT ALL ON ALL TABLES IN SCHEMA <sync_schema> TO "<SP>"`. Per the live doc, **synced tables are owned by the internal `databricks_writer_` role**, and access is managed by the `databricks_superuser` via `GRANT SELECT ON <synced_table>` or by registering managers with `databricks_synced_table_add_manager('"schema"."table"'::regclass, '[user]')`. A plain `GRANT ALL ON ALL TABLES` issued by a non-superuser will silently miss the pipeline-owned tables. **Fix:** replace the Part 5 snippet (and the matching note in `docs/PERMISSIONS.md`) with the documented `databricks_synced_table_add_manager` / superuser-`SELECT` pattern.
- 🔎 **Verify:** the doc slug `oltp/projects/sync-tables` resolves (it does today); keep the deep-link anchors (`#sync-modes`, `#schedule-or-trigger-subsequent-syncs`) in sync with the doc's current headings.

## development-experience — `Branches_and_Environments.py`, `Autoscaling_and_Compute.py`
**Anchor docs:** [Manage branches](https://docs.databricks.com/aws/en/oltp/projects/manage-branches), *Computes* (`computes.md`).

- **Accuracy** ✅ `create_branch(BranchSpec(source_branch=…, ttl=Duration(seconds=86400)))` matches `branches.md`. CU table (0.5→104 … 32→4,000), RAM = 2 GB/CU, and the **max−min ≤ 8 CU** autoscale spread all match `computes.md`. Scale-to-zero: production disabled / others 5-min default ✅. `update_endpoint` + `FieldMask` pattern ✅.
- ⚠️ **P1 (robustness):** `Branches_and_Environments.py` line ~94 does `time.sleep(10)` then immediately `get_connection(DEV_BRANCH)`. A newly created branch's compute may take longer than 10 s to reach `ACTIVE`, so this can fail intermittently. **Fix:** poll for `ACTIVE` (reuse the 90×5 s loop from `00_Setup`) instead of a fixed sleep. Same pattern recurs in backup-recovery (below).
- ⚠️ **P2 (wording):** the `Autoscaling_and_Compute` header says "Autoscaling compute (0.5–112 CU)". Per `computes.md`, **autoscaling** is 0.5–32 CU (≤8 spread); 36–112 CU are **fixed-size, non-autoscaling**. The in-notebook table correctly caps at 32 ("Maximum autoscale"), so just tighten the header to "0.5–32 CU autoscaling (up to 112 CU fixed-size)".
- **Best practice** ✅ Branch creation handles `already exists`; 24 h TTL demonstrates auto-cleanup; cleanup cell intentionally commented.

## observability — `labs/observability/Observability_and_Monitoring.py`
**Anchor docs:** *Monitor*, *pg_stat_statements*.

- **Accuracy** ✅ `pg_stat_database`, `pg_stat_user_tables`, `pg_stat_user_indexes`, `pg_stat_activity`, `pg_stat_statements` all used correctly; connection-limit table matches `computes.md`; note that stats reset on scale-to-zero is correct.
- **Simplicity / best practice** ✅ Strong lab; `CREATE EXTENSION IF NOT EXISTS pg_stat_statements` guarded with a friendly fallback.
- 🔎 **P2 (verify UI path):** Section 7 says navigate **Catalog → Lakebase** (or **Compute → Lakebase**) → **Monitoring** tab. The live docs now refer to the **Lakebase App** with a project dashboard; confirm the current in-product navigation label and update if it's changed.

## authentication — `labs/authentication/Authentication_and_Permissions.py`
**Anchor docs:** *Authentication*, *Roles & permissions*, *Manage roles*.

- **Accuracy** ✅ OAuth 1-hour TTL, "expiration enforced only at login, open connections persist" matches `connection-patterns.md`. JWT decode (`sub`/`exp`/`iss`) is correct. Two-layer permission model is well explained. Token-rotation examples (psycopg pool `CustomConnection`, SQLAlchemy `do_connect` listener) are the sanctioned patterns.
- 🔎 **P2 (verify):** two items to confirm against the live *Authentication* doc: (a) the CLI subcommand name `databricks postgres generate-database-credential`; (b) in the SQLAlchemy example, `credential.expire_time.seconds` — confirm `expire_time` exposes `.seconds` (protobuf `Timestamp`) vs a `datetime`. These are in markdown examples, so low blast-radius, but worth a spot-check.
- **Best practice** ✅ Least-privilege GRANT examples, external-tool (psql/DBeaver) guidance with `sslmode=require`.

## backup-recovery — `labs/backup-recovery/Backup_and_Recovery.py`
**Anchor docs:** [Point-in-time restore](https://docs.databricks.com/aws/en/oltp/projects/point-in-time-restore), [Manage branches](https://docs.databricks.com/aws/en/oltp/projects/manage-branches).

- ⚠️ **P0 (accuracy — the 35-day claim):** the lab says the recovery window max is **"35 days"** (§1 table, §5 "Maximum: 35 days", and the best-practices table). The **live doc says the restore/history window is 2–30 days, default 7**. The **default of 7 days is correct**; the **max is now 30, not 35**. This 35-day figure also appears in `notebooks/00_Setup_Lakebase_Project.py` (Key Capabilities table) and the setup architecture prose. **Fix:** change every "35 days" restore/history-window claim to **30 days**. *(Note: the `projects.md` skill still says 35 — the live doc supersedes it. This is the clearest "skill is stale" case.)*
- ⚠️ **P1 (correctness — snapshot branch):** the snapshot branch is created with **neither `ttl` nor `no_expiry`**:
  ```python
  BranchSpec(source_branch=f"projects/{PROJECT_ID}/branches/production")  # no expiry policy set
  ```
  The notebook comment correctly explains *why* it must be non-expiring (the doc confirms: *"Cannot expire branches that have children or create children from expiring branches"* — and we branch a recovery branch off it). But relying on the implicit default is fragile. **Fix:** set it explicitly:
  ```python
  BranchSpec(source_branch=..., no_expiry=True)
  ```
- ⚠️ **P1 (bug — cleanup order):** the commented cleanup loops `[WORK_BRANCH, SNAPSHOT_BRANCH, RECOVERY_BRANCH]`. `RECOVERY_BRANCH` is a **child of** `SNAPSHOT_BRANCH`, and the doc states *"You cannot delete a branch that has child branches."* Deleting the snapshot before the recovery branch fails. **Fix:** reorder to delete children first — `[WORK_BRANCH, RECOVERY_BRANCH, SNAPSHOT_BRANCH]`.
- 🔎 **P1 (verify — PITR SDK example):** the PITR code sample uses `BranchSpec(source_branch=production, parent_timestamp=ts)` with a protobuf `Timestamp`. The live doc frames PITR as creating a **new root branch** (and documents it primarily via the UI "Backup & Restore" flow). Confirm (a) the SDK field name (`parent_timestamp`) still exists and (b) that the example's semantics match "new root branch." If the SDK path has changed, reframe as the documented UI flow or update the field.
- ⚠️ **P1 (robustness):** same fixed `time.sleep(10)` before connecting to the work/recovery branches — replace with an `ACTIVE` poll.
- **Best practice** ✅ "backups are always on / no config needed", snapshot-before-migration framing, and the WAL/PITR mental model are all accurate.

## agentic-memory — `labs/agentic-memory/Agent_Memory.py`
**Anchor doc:** *AI agent memory* (agent framework / stateful agents).

- **Accuracy / best practice** ✅ Best-in-class SQL hygiene: **parameterized queries throughout** (`%s`), `ON CONFLICT … DO UPDATE` upserts, sensible short-term (`agent_sessions`/`agent_messages`) vs long-term (`agent_memory_store`) split. LangGraph `PostgresSaver` checkpoint snippet is correct.
- 🔎 **P2 (verify):** confirm (a) the doc slug `generative-ai/agent-framework/stateful-agents`, (b) the template names `agent-langgraph-advanced` / `agent-openai-advanced` and the clone URL `github.com/databricks/app-templates.git`, and (c) the demo model id `databricks-meta-llama-3-3-70b-instruct` (it's in metadata only, so cosmetic, but model ids age quickly).

## online-feature-store — `labs/online-feature-store/Online_Feature_Store.py`
**Anchor doc:** [Online Feature Store](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store).

- **Accuracy** ✅ `fe.create_table` (with PK), CDF enablement, `fe.get_online_store(name=PROJECT_ID)`, `fe.publish_table`, `fe.list_online_stores`, `w.online_tables.get`, `w.feature_store.delete_online_table` are consistent with current Feature Engineering usage. The "reuse one online store" guidance is **quoted directly from the doc** — excellent grounding. The dedup guard and "use `delete_online_table`, not `DROP TABLE`" warning are correct.
- ⚠️ **P2 (doc-link accuracy):** line ~267 links the SQL editor as `.../oltp/instances/query/sql-editor`. `oltp/instances/…` is the **Lakebase Provisioned** path; the autoscaling equivalent is under `oltp/projects/…`. **Fix:** point to the projects SQL-editor doc (the data-operations lab already uses `oltp/projects/sql-editor`).
- 🔎 **P2 (verify):** the "DBR 16.4 LTS ML or serverless" requirement and `databricks-feature-engineering>=0.13.0` pin — confirm against the current doc's prerequisites.

## app-deployment — `labs/app-deployment/Deploy_Lab_Console_App.py`, `apps/lakebase-lab-console/backend/db.py`, `app.yaml`, `docs/PERMISSIONS.md`
**Anchor docs:** *Connect an application*, *Databricks Apps + Lakebase tutorial*.

- **Accuracy / best practice** ✅ SP auth rationale (forwarded user token lacks `postgres` scope), `databricks_auth` + `databricks_create_role`, per-user schema grants, `search_path` routing, and **token cache at 45 min (< 60-min expiry)** are all correct and even *safer* than the skills' 50-min guidance. Thread-safe cache keyed by `project_id:branch_id` is a good pattern.
- ⚠️ **P2 (terminology):** the deployment section calls the bundle a **"Declarative Automation Bundle"** — it's a **Databricks Asset Bundle (DAB)**. Fix the label.
- 🔎 **P2 (modernization, optional):** `app.yaml` uses `resources: [{name, type: postgres}]` + `env: LAKEBASE_BRANCH_ID` and the backend discovers the endpoint via `list_endpoints`. The current AppKit convention exposes `LAKEBASE_ENDPOINT` via `valueFrom: postgres` and injects `PGHOST/PGUSER/PGDATABASE/PGPORT/PGSSLMODE`. The workshop's approach **works**; note it as an optional modernization, not a bug.

## lakehouse-sync — `labs/lakehouse-sync/README.md` (no runnable notebook)
**Anchor doc:** [Lakehouse Sync](https://docs.databricks.com/aws/en/oltp/projects/lakehouse-sync).

- **Accuracy** ✅ (better than expected) The README is an accurate UI-walkthrough placeholder: correct prerequisites (`REPLICA IDENTITY FULL`, admin enablement via **Previews**, `databricks_postgres` DB, PG 17), correct concepts (CDC, SCD Type 2, native — no external pipelines), correct pairing with Reverse ETL.
- 🔎 **P0 (verify status label):** the README and the setup notebook both label it **"Beta."** Confirm the current maturity — if it has moved to **Public Preview** and/or exposes an SDK/REST surface, (a) update the label from *Beta* → *Public Preview*, and (b) promote this from placeholder to a runnable lab. If it's still UI-only Beta, the current README is fine as-is.

---

# Section B — Cross-cutting findings

These repeat across labs; each is cited to a trusted source.

1. **`sslmode=require` everywhere** ✅ — verified in `_setup.py`, `00_Setup`, authentication, online-feature-store, app-deployment. Matches `connection-patterns.md` rule #1. No gaps found.

2. **Token lifecycle** ✅ — 1-hour TTL is stated consistently; refresh at 45 min (app) / documented rotation patterns (authentication). Matches `connection-patterns.md` (refresh ≤ 50 min).

3. **Retry-on-wake for scale-to-zero** ⚠️ **P1** — `connection-patterns.md` best practice #6 ("first connection after idle may take a couple seconds; implement retry") is **not** implemented anywhere. The production branch has scale-to-zero **disabled** (so `get_connection("production")` is safe), but the branch labs connect to freshly-created/idle branches with a flat `sleep(10)` and no retry. Recommend a small `connect-with-retry` helper in `_setup.py` and use it for non-production branches.

4. **Idempotency** ✅ — project create, seed, triggers, SP grants, and branch creation all handle "already exists." Strong.

5. **Intentional cleanup-commented cells** ✅ (not a bug) — every destructive step is commented with clear instructions. This is the right choice for a workshop; keep it.

6. **Stale-skill reconciliation** 🔎 — the audit confirmed the workshop is **ahead of** the curated `databricks-lakebase-autoscale` skills in two places (synced-table throughput/size numbers, and the fact that **Online Feature Store + agent memory are now supported** on autoscaling). Treat the **live public docs** as the tiebreaker, not the skills. The one place the workshop is *behind* the live docs is the **35-day restore window (should be 30)**.

7. **Doc-path / naming nits (P2):**
   - online-feature-store SQL-editor link uses `oltp/instances/…` (Provisioned) instead of `oltp/projects/…`.
   - app-deployment "Declarative Automation Bundle" → "Databricks Asset Bundle."
   - Timing claims (1-3 vs 2-3 vs 7.5 min) should be aligned.
   - Autoscale header "0.5–112 CU" → clarify autoscale is 0.5–32.

8. **Resource / source-of-truth alignment (P2):** the top-level `README.md` Resources block (lines ~99-102) lists only 4 generic links. Recommend retiering to your canon: **hub / official docs / FAQ / roadmap / quick-reference first**, then feature docs (sync-tables, authentication, point-in-time-restore, online-feature-store, lakehouse-sync), then example repos / fieldkit. Apply the same ordering to `labs/README.md` and `docs/CREDITS.md`.

---

# Section C — Secondary: newer features (clearly lower priority than A/B)

Brief specs only — proposed *after* the Section A fixes land.

- **Lakebase Search (Beta)** — pgvector-compatible `lakebase_vector`/`lakebase_ann` + full-text `lakebase_text`/`lakebase_bm25`, hybrid ranking via RRF. Enablement is irreversible and restarts compute. **Natural tie-in:** extend the **Agentic Memory** lab with semantic recall over `agent_memory_store` (embed `memory`, ANN search). Verify the extension is enabled in the target workshop workspace before authoring.
- **Data API (PostgREST)** — RESTful access over HTTPS with an `authenticator` role and OAuth bearer token. **Caveat to call out:** the DB-owner account can't be used directly — needs a non-owner Postgres role / SP. Good fit as a lightweight alternative to the FastAPI app for "call Lakebase from anywhere" demos.
- **Lakehouse Sync** — see Section A; promote to runnable once the SDK/REST surface is confirmed GA/Preview; otherwise keep the accurate UI walkthrough.

---

# Section D — Prioritized fix list

### P0 — accuracy (do first)
1. **Restore/history window: change "35 days" → "30 days"** in `backup-recovery/Backup_and_Recovery.py` (§1, §5, best-practices table) **and** `notebooks/00_Setup_Lakebase_Project.py` (Key Capabilities + architecture prose). Keep "default 7 days." *(Source: point-in-time-restore doc.)*
2. **Reverse ETL synced-table grants:** replace `GRANT ALL ON ALL TABLES …` with the documented `databricks_synced_table_add_manager()` / superuser-`SELECT` pattern in `reverse-etl/Reverse_ETL.py` Part 5 and `docs/PERMISSIONS.md`. *(Source: sync-tables doc, "Ownership and permissions.")*
3. **Lakehouse Sync status:** verify Beta vs Public Preview; relabel and, if the API has shipped, promote to a runnable lab.

### P1 — best practice / robustness
4. Replace fixed `time.sleep(10)` with an `ACTIVE` poll (or a connect-with-retry helper) for new-branch connections in `development-experience` and `backup-recovery`.
5. Set `no_expiry=True` explicitly on the backup-recovery **snapshot** branch.
6. Fix backup-recovery cleanup order: delete `RECOVERY` before `SNAPSHOT` (child before parent).
7. Verify the PITR SDK example (`parent_timestamp`, new-root-branch semantics) or reframe to the documented UI flow.

### P2 — polish
8. Fix the online-feature-store SQL-editor doc link (`oltp/instances` → `oltp/projects`).
9. "Declarative Automation Bundle" → "Databricks Asset Bundle" (app-deployment).
10. Align the endpoint-timing wording across setup notebook / README.
11. Tighten the autoscale "0.5–112 CU" header to distinguish autoscale (0.5–32) from fixed-size.
12. Retier the Resources links (README / labs README / CREDITS) to your canon.
13. (Optional) Modernize `app.yaml` to `LAKEBASE_ENDPOINT` + `valueFrom: postgres`.

### Open questions (need a live workspace / doc re-check)
- Restore-window max: **30 (live doc) vs 35 (skills)** — confirm the number currently shown in-product for this workspace's region.
- PITR SDK field `parent_timestamp` — still present and behaves as "new root branch"?
- Authentication doc: exact CLI subcommand (`generate-database-credential`) and `expire_time.seconds` shape.
- Lakebase Search enablement state in the target workshop workspace (needed before authoring the Section C lab).

---

## Bottom line
Ship the **three P0 fixes** and the **four P1 items** and the workshop is both accurate and exemplary. The most important single change is the **35 → 30 day restore-window correction** (it appears in multiple learner-facing places) and the **synced-table grant pattern** (the current instructions won't actually grant the app access to pipeline-owned tables). Everything else is polish.
