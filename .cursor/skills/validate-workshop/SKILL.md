---
name: validate-workshop
description: >-
  Test and validate the Lakebase Workshop labs, notebooks, and Lab Console app
  before committing or deploying. Use when the user asks to validate, test,
  check, or verify the workshop/labs, or before committing changes to notebooks,
  labs, the Lab Console app, or workshop docs.
---

# Validate the Lakebase Workshop

Run before committing or deploying any change to notebooks, labs, the Lab
Console app, or workshop docs. Catches broken notebook syntax, missing labs,
stale facts, dead links, and app build failures without needing a live
Databricks workspace.

## Quick start (do this first)

From the repo root:

```bash
python3 scripts/validate_workshop.py          # fast, offline static checks
python3 scripts/validate_workshop.py --full   # + React build + bundle validate
```

Exit code `0` = pass (warnings allowed), `1` = failures present. **Fix every
failure before committing.** Then re-run until it passes.

Flags: `--frontend` (React build only), `--bundle` (`databricks bundle
validate` only), `--full` (everything).

## What the script checks

- **Notebook syntax** — compiles every Python cell in `notebooks/**` and
  `labs/**` (skips `%md`/`%sql`/magic cells).
- **Lab structure** — every `labs/*/` has a `README.md` and a runnable
  notebook; labs listed in `labs/README.md` actually exist.
- **Regression guard** — stale facts we've corrected before (e.g. `112 CU`,
  `35-day`, `parent_timestamp`, `Beta, UI-only`) must not reappear.
- **Relative links** — every relative Markdown link resolves.
- **Backend compile** — all `apps/lakebase-lab-console/backend/**` Python
  compiles.
- **`--full` adds:** React app build (`npm run build`) and
  `databricks bundle validate`.

Auth failures on `bundle validate` are reported as **warnings** (environmental,
not a repo defect) — a stale CLI token does not fail the run.

## Feedback loop

1. Run `python3 scripts/validate_workshop.py --full`.
2. If it fails, read the `✗` lines (each is `file:line: reason`), fix them.
3. Re-run. **Only proceed to commit when it passes.**

## Keeping the regression guard current

When an audit corrects a hard fact (a CU limit, a restore window, an SDK field,
a feature-maturity label), add a pattern to the `REGRESSIONS` list near the top
of `scripts/validate_workshop.py` so it can never silently return. Each entry is
`("human-readable reason", r"regex")`. Exclude source-of-truth docs that quote
old values on purpose via `REGRESSION_EXCLUDE` (already excludes
`docs/LAKEBASE_AUDIT.md`).

## Live validation (optional — needs a workspace)

Static checks do not execute notebooks. To validate against real Lakebase:

```bash
databricks bundle validate -t dev     # config sanity
databricks bundle deploy -t dev        # push notebooks/labs/app to the workspace
```

Then run `notebooks/00_Setup_Lakebase_Project.py` and the changed lab notebooks
in the workspace, and confirm the Lab Console app starts. Requires a configured
CLI profile (`dev`) with Lakebase enabled; if the token is expired, run
`databricks auth login -p dev` first.
