# Lakebase Workshop

A hands-on workshop for exploring **Databricks Lakebase** -- a fully managed PostgreSQL database that runs inside your Databricks workspace.

> **It's all one Lakebase now.** Databricks has unified its managed Postgres under a single **Lakebase** offering (the earlier "Provisioned" instances were upgraded to the unified platform by Jul 31, 2026). You'll still see **"Autoscaling"** in doc URLs and the SDK (`w.postgres.*`, the `oltp/projects` surface) — that's the API surface this workshop is built on.

## Quick Start

### Step 1: Clone the repo and run setup

Open a terminal and run:

```bash
git clone <this-repo-url>
cd Lakebase-Workshop
bash setup.sh
```

The setup script will walk you through everything: installing dependencies, connecting to your Databricks workspace, and deploying the workshop content. Just follow the prompts.

### Step 2: Run the setup notebook

In your Databricks workspace, open the **`00_Setup_Lakebase_Project`** notebook and click **Run All**.

This creates your personal Lakebase database and loads sample data. It takes about 2-3 minutes.

You can find the notebook at:
**Workspace > Users > *your email* > .bundle > lakebase-workshop > dev > files > notebooks**

### Step 3: Start exploring

You're all set. Pick any lab from the list below and dive in. Each lab is self-contained -- no need to follow a specific order.

## Prerequisites

Before you begin, make sure you have:

- **Your own Databricks workspace** with Lakebase enabled
- **Python 3.11+** on your computer (`python3 --version`)
- **Databricks CLI ≥ 0.294.0**, logged in via `databricks auth login` (do this ahead of time)
- **Node.js 18+** — only needed if you deploy the **Lab Console app**. `setup.sh` installs it for you (Homebrew, nvm, or apt) when you choose option 2. You can also install it ahead of time (`node --version`). Not needed for the notebook labs.

Share this with participants ahead of time: **[Prerequisites Guide](docs/PREREQUISITES.md)** (GitHub access, bring-your-own workspace, and auth login).

On workshop day, `setup.sh` installs the remaining Python packages into your active environment (no separate venv required). If you deploy the Lab Console app, it also installs Node.js when it is missing.

## Choose a Lab

Every lab is independent. Pick whichever sounds interesting, or follow one of the suggested tracks below.

### Application Builders

*Building apps, APIs, or AI agents? Start here.*

| Lab | What You'll Do |
|-----|----------------|
| **Data Operations** | Create, read, update, and delete data; work with JSON and arrays |
| **Data API** | Call Lakebase over REST (PostgREST) with an OAuth bearer token and row-level security |
| **Agentic Memory** | Store and query AI agent conversation history |
| **Lakebase Search** *(Beta)* | Add vector + keyword (BM25) search and hybrid ranking to your data |
| **App Deployment** *(capstone)* | Deploy a full-stack web app backed by Lakebase |

### Data & ML Engineers

*Working with data pipelines or machine learning? Start here.*

| Lab | What You'll Do |
|-----|----------------|
| **Reverse ETL** | Sync your Delta Lake tables into Lakebase for fast lookups |
| **Unity Catalog Access** | Register Postgres as a federated read-only UC catalog for Lakehouse SQL |
| **Lakehouse Sync** *(Public Preview)* | Sync Lakebase back to the lakehouse as Delta with full CDC change history |
| **Online Feature Store** | Serve ML features in real time from Lakebase |

### Platform Architects

*Evaluating Lakebase for your infrastructure? Start here.*

| Lab | What You'll Do |
|-----|----------------|
| **Development Experience** | Create isolated database branches, test autoscaling, and explore high availability + read replicas |
| **Authentication, Security & Compliance** | Explore token-based auth, role permissions, encryption/CMK, Private Link, and compliance profiles |
| **Backup & Recovery** | Try checkpoint branches, snapshots, and point-in-time restore |
| **Observability** | Monitor database performance, indexes, and query activity |

All labs are in the `labs/` folder, organized by topic.

## Lab Console App

Your facilitator may have deployed a shared **Lab Console** web app. This app mirrors all the labs in a visual interface -- you can use it alongside (or instead of) the notebooks.

Open it at: **Compute > Apps > lakebase-lab-console**

The setup notebook (Step 2 above) automatically grants the app access to your database, so it will show your data as soon as you log in.

## Troubleshooting

| Problem | What to Do |
|---------|------------|
| `setup.sh` fails during login | Run `databricks auth login --host <your-workspace-url> --profile lakebase-workshop` manually |
| Setup notebook hangs on "Waiting for endpoint" | This is normal -- it can take 2-3 minutes. Let it finish. |
| "password authentication failed" | Your database token expired (they last 1 hour). Re-run the connection cell in your notebook. |
| Opening the app shows `{"detail":"Not Found"}` | You're on an older deployment whose UI was never built. Re-run `bash setup.sh`, choose **option 2**, and accept the Node.js install when prompted. Current builds show an explanatory page instead. |
| Opening the app shows "the app is running, but its user interface was not deployed" | The app was deployed without a frontend build. Re-run `bash setup.sh` → **option 2** (setup installs Node.js if needed). The notebook labs are unaffected. |
| Lab Console shows "Project Not Found" | You haven't run the setup notebook yet. Go back to Step 2. |
| `function databricks_create_role(...) does not exist` | The `databricks_auth` extension isn't installed in your Postgres database. Run `CREATE EXTENSION IF NOT EXISTS databricks_auth;` once per database — the setup notebook now does this automatically in Step 6. |
| Deploying the app errors with "No endpoints" before running the setup notebook | Re-run `bash setup.sh` and choose **option 2** — the script auto-creates your Lakebase project before deploying the app. If auto-create fails, run `00_Setup_Lakebase_Project` and re-run setup. |

## Resources

**Start here (canonical Lakebase docs):**
- [What is Lakebase?](https://docs.databricks.com/aws/en/oltp/projects/about)
- [Lakebase documentation (hub)](https://docs.databricks.com/aws/en/oltp/projects/)
- [Get started with Lakebase](https://docs.databricks.com/aws/en/oltp/projects/get-started)
- [June 2026 release notes](https://docs.databricks.com/aws/en/release-notes/product/2026/june) — latest launches & changes

**Feature docs (mapped to the labs):**
- [Authentication](https://docs.databricks.com/aws/en/oltp/projects/authentication) · [Roles & permissions](https://docs.databricks.com/aws/en/oltp/projects/roles-permissions) · [Private Link](https://docs.databricks.com/aws/en/oltp/projects/private-link)
- [Branches](https://docs.databricks.com/aws/en/oltp/projects/branches) · [Autoscaling](https://docs.databricks.com/aws/en/oltp/projects/autoscaling) · [Scale to zero](https://docs.databricks.com/aws/en/oltp/projects/scale-to-zero) · [High availability](https://docs.databricks.com/aws/en/oltp/projects/high-availability) · [Read replicas](https://docs.databricks.com/aws/en/oltp/projects/read-replicas)
- [Serve lakehouse data with synced tables (Reverse ETL)](https://docs.databricks.com/aws/en/oltp/projects/sync-tables) · [Register Lakebase in Unity Catalog](https://docs.databricks.com/aws/en/oltp/projects/register-uc) · [Lakebase Change Data Feed (Lakehouse Sync)](https://docs.databricks.com/aws/en/oltp/projects/lakehouse-sync)
- [Point-in-time restore](https://docs.databricks.com/aws/en/oltp/projects/point-in-time-restore) · [Monitor](https://docs.databricks.com/aws/en/oltp/projects/monitor)
- [Data API (PostgREST)](https://docs.databricks.com/aws/en/oltp/projects/data-api) · [Lakebase Search](https://docs.databricks.com/aws/en/oltp/projects/lakebase-search) *(Beta)*
- [Online Feature Store](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store) · [Connect an application](https://docs.databricks.com/aws/en/oltp/projects/connect-application)

**Reference:**
- [Databricks Apps documentation](https://docs.databricks.com/en/dev-tools/databricks-apps/)
- [PostgreSQL documentation](https://www.postgresql.org/docs/)

## For Facilitators

If you're running this workshop for a group, see the [Facilitator Guide](docs/WORKSHOP_FACILITATOR.md) for deployment instructions, timing options, demo scripts, and detailed troubleshooting.

## License

See [LICENSE.md](LICENSE.md).
