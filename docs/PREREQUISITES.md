# Workshop Prerequisites

Complete these items **before** the workshop so day-of setup stays short. You’ll use **your own Databricks workspace** (bring your own) and connect to it with the Databricks CLI ahead of time.

---

## 1. GitHub access (clone the repo)

The workshop materials are in a **public** GitHub repository — no special GitHub permissions required.

**Repo:** [https://github.com/databricks-solutions/lakebase-workshop](https://github.com/databricks-solutions/lakebase-workshop)

Clone it on the laptop you’ll use for the workshop:

```bash
git clone https://github.com/databricks-solutions/lakebase-workshop.git
cd lakebase-workshop
```

You need:

- A terminal (`Terminal` on macOS, or equivalent on Windows/Linux)
- `git` installed ([install Git](https://git-scm.com/downloads) if needed)

---

## 2. Your Databricks workspace

Bring a Databricks workspace you can use for the labs (customer / company workspace is expected).

Before the session, confirm:

- [ ] You can sign in to **your** workspace URL in a browser  
  (example shape: `https://dbc-xxxxxxxx-xxxx.cloud.databricks.com` or `https://<name>.cloud.databricks.com`)
- [ ] **Lakebase** is available in that workspace (ask your workspace admin if unsure)
- [ ] You can create notebooks and run them (standard user access is usually enough)
- [ ] **Unity Catalog:** participants either have a catalog named `main` with `USE CATALOG`, `CREATE SCHEMA`, and `CREATE TABLE`, **or** at least one participant has `CREATE CATALOG` on the metastore (so the group can create a catalog and point the UC labs at it). The **Unity Catalog Access** lab (`labs/unity-catalog-access/`) also needs `CREATE CATALOG` (or a facilitator who registers `lb_fed_<user>` catalogs) plus a **Serverless SQL Warehouse** for federated queries.

Keep your workspace URL handy for the auth step below.

---

## 3. Databricks CLI + Auth login (do this ahead of time)

Connecting with `databricks auth login` before the workshop is the main time-saver.

### What to install

| Tool | Minimum / guidance | Notes |
|------|--------------------|--------|
| **Databricks CLI** | **≥ v0.294.0** | Needed for Lakebase (`databricks postgres …`). Prefer a current install via Homebrew or the official installer. |
| **Python 3** | **3.11+** recommended | Used by `setup.sh` and local scripts. Check with `python3 --version`. |
| **pip** | Comes with Python | `setup.sh` installs Python packages when you run it (see below). |

There is **no separate workshop venv to set up ahead of time**. On workshop day, `bash setup.sh` installs the Python packages it needs (`databricks-sdk`, `psycopg`) into your **active** Python/pip environment. You do **not** need to create a virtualenv first unless you prefer to isolate packages yourself.

### Install the Databricks CLI

```bash
# macOS (Homebrew) — recommended
brew install databricks/tap/databricks

# or via pip (less preferred for the CLI binary)
pip install databricks-cli
```

Confirm version (should be **0.294.0 or newer**):

```bash
databricks --version
```

If you’re below `0.294.0`, upgrade before the workshop:

```bash
brew upgrade databricks
# or reinstall via the docs installer
```

Full install options: [Install the Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/install.html)

### Log in to *your* workspace

Use **your** workspace URL:

```bash
databricks auth login --host <your-workspace-url> --profile lakebase-workshop
```

Example:

```bash
databricks auth login --host https://dbc-xxxxxxxx-xxxx.cloud.databricks.com --profile lakebase-workshop
```

What happens:

1. Your browser opens a Databricks login page
2. Sign in with the account you use for **that** workspace
3. Approve access when prompted
4. Return to the terminal — login should succeed

### Verify

```bash
databricks auth profiles
```

You should see `lakebase-workshop` listed as valid (`YES`).

Optional Lakebase smoke check (workspace must have Lakebase enabled):

```bash
databricks postgres list-projects --profile lakebase-workshop
```

If that command is missing or fails with an unknown-command error, your CLI is too old — upgrade to ≥ 0.294.0.

---

## Quick checklist

| # | Prerequisite | Done? |
|---|--------------|-------|
| 1 | Cloned [databricks-solutions/lakebase-workshop](https://github.com/databricks-solutions/lakebase-workshop) | ☐ |
| 2 | Can sign into **your** Databricks workspace; Lakebase available; UC catalog `main` (or someone with `CREATE CATALOG`) | ☐ |
| 3 | Databricks CLI ≥ **0.294.0** (`databricks --version`) | ☐ |
| 4 | Ran `databricks auth login … --profile lakebase-workshop` successfully | ☐ |
| 5 | Python 3.11+ available (`python3 --version`) | ☐ |

---

## On workshop day

Auth and tooling should already be done. From the repo:

```bash
cd lakebase-workshop
bash setup.sh
```

`setup.sh` will:

1. Install/update Python packages into your current pip environment (prompts first)
2. Reuse your existing `lakebase-workshop` CLI profile if it’s already logged in
3. Deploy workshop content to **your** workspace

Then open and **Run All** on the **`00_Setup_Lakebase_Project`** notebook (details in the [README](../README.md)).

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| Browser doesn’t open during login | Re-run `databricks auth login`; ensure the host starts with `https://` |
| Profile not valid | Run `databricks auth profiles`; log in again with the correct `--host` |
| `postgres` commands missing / unknown | Upgrade the CLI to ≥ **0.294.0** |
| `pip` / PEP 668 errors on macOS | Let `setup.sh` retry, or create a venv yourself (`python3 -m venv .venv && source .venv/bin/activate`) and re-run setup |
| Lakebase not available | Ask your workspace admin to enable Lakebase, or use a workspace where it is enabled |

If something still blocks you, reach out **before** the workshop with your OS, `databricks --version`, `python3 --version`, and the exact error message.
