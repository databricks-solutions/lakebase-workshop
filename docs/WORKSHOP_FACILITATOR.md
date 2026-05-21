# Workshop Facilitator Guide

## Overview

This guide helps facilitators run a Lakebase Autoscaling workshop. The workshop uses a **foundation + choose-your-track** model: participants complete a single setup notebook, then follow a track tailored to their role — or mix and match labs across tracks.

## Prerequisites Checklist

Before the workshop:

- [ ] Databricks workspace with Lakebase Autoscaling enabled
- [ ] Each participant has workspace access with permissions to create Lakebase projects
- [ ] Python 3.11+ installed on each participant's machine
- [ ] (Facilitator only) Node.js installed for building the Lab Console frontend

## Workshop Structure

### Foundation (required — all participants)

| Notebook | Location | What It Does |
|----------|----------|--------------|
| `00_Setup_Lakebase_Project` | `notebooks/` | Create project, seed user schema (6 tables, 8 products) |

### Participant Tracks

After the foundation, participants follow a track based on their role. Each track is a recommended sequence of labs — but every lab is independent, so participants can skip ahead or explore across tracks.

#### Application Builders

*For developers building apps, APIs, and AI agents on Lakebase.*

| Order | Lab | Location | What It Covers |
|-------|-----|----------|----------------|
| 1 | Data Operations | `labs/data-operations/` | CRUD, JSONB, arrays, triggers, transactions |
| 2 | Agentic Memory | `labs/agentic-memory/` | Persistent AI agent memory with sessions |
| 3 | App Deployment *(capstone)* | `labs/app-deployment/` | Full-stack React + FastAPI Lab Console app |

**Key narrative:** *"Lakebase gives your applications a production-grade PostgreSQL backend inside the Lakehouse — no separate infrastructure, no bespoke sync pipelines."*

#### Data & ML Engineers

*For teams connecting the Lakehouse to operational workloads and ML serving.*

| Order | Lab | Location | What It Covers |
|-------|-----|----------|----------------|
| 1 | Reverse ETL | `labs/reverse-etl/` | Sync Delta Lake tables into Lakebase |
| 2 | Lakehouse Sync *(Beta)* | `labs/lakehouse-sync/` | Sync Lakebase → Unity Catalog Delta with CDC + SCD Type 2 (UI-only placeholder) |
| 3 | Online Feature Store | `labs/online-feature-store/` | Real-time ML feature serving with Lakebase |

**Key narrative:** *"Move data both ways between Lakebase and the Lakehouse natively — and use Lakebase as the online feature store."*

#### Platform Architects

*For central IT, infrastructure, and security teams evaluating Lakebase for production readiness.*

| Order | Lab | Location | What It Covers |
|-------|-----|----------|----------------|
| 1 | Development Experience | `labs/development-experience/` | Branching, autoscaling, scale-to-zero |
| 2 | Authentication | `labs/authentication/` | OAuth tokens, roles, two-layer permissions |
| 3 | Backup & Recovery | `labs/backup-recovery/` | PITR, branch snapshots, instant restore |
| 4 | Observability | `labs/observability/` | pg_stat views, index analysis, monitoring |

**Key narrative:** *"Fully managed PostgreSQL with Git-like branching, OAuth security, instant recovery, and native Postgres observability — all governed by Unity Catalog."*

### All Labs Reference

Every lab lives directly in `labs/`. No track folder structure — tracks are a facilitation guide, not a file hierarchy.

| Lab | Location | What It Covers |
|-----|----------|----------------|
| Data Operations | `labs/data-operations/` | CRUD, JSONB, arrays, triggers, transactions |
| Reverse ETL | `labs/reverse-etl/` | Synced tables from Delta Lake |
| Lakehouse Sync *(Beta)* | `labs/lakehouse-sync/` | Lakebase → Unity Catalog Delta with CDC + SCD Type 2 (UI-only placeholder) |
| Development Experience | `labs/development-experience/` | Branching, autoscaling, scale-to-zero |
| Observability | `labs/observability/` | pg_stat views, index analysis, monitoring |
| Authentication | `labs/authentication/` | OAuth tokens, roles, permissions |
| Backup & Recovery | `labs/backup-recovery/` | PITR, branch snapshots, restore |
| Agentic Memory | `labs/agentic-memory/` | Persistent agent memory pattern |
| Online Feature Store | `labs/online-feature-store/` | Real-time ML feature serving with Lakebase |
| App Deployment | `labs/app-deployment/` | Full-stack Lab Console app (capstone) |

## Timing Options

### Full Workshop — Multi-Track (2.5 hours)

Best for mixed audiences. Everyone does the foundation together, then splits into tracks.

| Time | Activity | Details |
|------|----------|---------|
| 0:00 – 0:15 | **Introduction**: What is Lakebase? Architecture overview | Slides + foundation |
| 0:15 – 0:30 | **Setup**: Clone repo, run `setup.sh`, deploy content | Terminal |
| 0:30 – 0:45 | **Foundation**: Create Lakebase project + seed schema | `notebooks/00_Setup_Lakebase_Project` |
| 0:45 – 1:45 | **Track Time**: Participants follow their track (3 labs, or 4 for Platform Architects) | See track tables above |
| 1:45 – 2:15 | **Cross-Track Exploration**: Try a lab from another track | Participant choice |
| 2:15 – 2:30 | **Wrap-up**: App Deployment overview, Q&A | `labs/app-deployment/` |

> **Facilitation tip:** Assign tracks at the start based on participant roles. Print or screen-share the track tables so participants know their sequence. Roaming facilitators can help across all three tracks simultaneously.

### Full Workshop — Single Track (2.5 hours)

Best for homogeneous audiences (e.g., all developers, all platform engineers). Run the foundation, then go deep on one track with time to explore others.

| Time | Activity | Details |
|------|----------|---------|
| 0:00 – 0:15 | **Introduction**: What is Lakebase? Architecture overview | Slides + foundation |
| 0:15 – 0:30 | **Setup**: Clone repo, run `setup.sh`, deploy content | Terminal |
| 0:30 – 0:45 | **Foundation**: Create Lakebase project + seed schema | `notebooks/00_Setup_Lakebase_Project` |
| 0:45 – 1:05 | **Track Lab 1** | First lab in the chosen track |
| 1:05 – 1:25 | **Track Lab 2** | Second lab in the chosen track |
| 1:25 – 1:45 | **Track Lab 3** | Third lab in the chosen track |
| 1:45 – 2:15 | **Bonus**: Explore labs from other tracks | Participant choice |
| 2:15 – 2:30 | **Wrap-up**: Q&A, next steps | Remaining paths as self-paced |

### Standard Workshop (90 min)

Pick one track and run it end-to-end.

| Time | Activity | Details |
|------|----------|---------|
| 0:00 – 0:10 | Introduction + architecture | Slides + foundation |
| 0:10 – 0:25 | Setup + Foundation | Terminal + `notebooks/00` |
| 0:25 – 0:45 | **Track Lab 1** | First lab in the chosen track |
| 0:45 – 1:05 | **Track Lab 2** | Second lab in the chosen track |
| 1:05 – 1:20 | **Track Lab 3** | Third lab in the chosen track |
| 1:20 – 1:30 | Wrap-up + Q&A | Remaining tracks as self-paced |

### Short Session (60 min)

Highlight one lab from each track to show breadth.

| Time | Activity | Details |
|------|----------|---------|
| 0:00 – 0:10 | Introduction + setup | Slides + terminal |
| 0:10 – 0:25 | **Foundation** | `notebooks/00` |
| 0:25 – 0:40 | **Development Experience** (Branching) | Platform Architects track highlight |
| 0:40 – 0:55 | **Data Operations** (CRUD + JSONB) | Application Builders track highlight |
| 0:55 – 1:00 | Wrap-up, point to full tracks for self-paced | All tracks |

## Step-by-Step Setup

### 1. Clone and configure (all participants)

```bash
git clone <this-repo-url>
cd Lakebase-Workshop
bash setup.sh
```

The script installs dependencies, authenticates the Databricks CLI, validates Lakebase access, and configures the bundle profile.

### 2. Deploy the Lab Console (facilitator only)

The Lab Console is a **shared app** — the facilitator deploys it once and all
participants use it. During `setup.sh`, choose **option 2 (Labs + App)** to deploy
everything including the app.

The setup script will also:
- **Ensure your Lakebase project exists** — if you haven't already run the setup
  notebook, you'll be prompted to either auto-create the project + seed schema
  inline, or pause and run `00_Setup_Lakebase_Project` first (then re-run setup.sh)
- **Attach a postgres resource** to the app (your Lakebase project), giving the SP the `postgres` OAuth scope
- **Grant the SP access** to your schema so the app can connect to your project

To deploy manually:

```bash
# Build the frontend
cd apps/lakebase-lab-console/frontend
npm install && npm run build
cd ../../..

# Deploy the bundle + start the app
databricks bundle deploy --target dev --profile lakebase-workshop
databricks bundle run lakebase_lab_console --target dev --profile lakebase-workshop
```

The app is named `lakebase-lab-console` and is accessible to all workspace users
at **Compute → Apps → lakebase-lab-console**.

> **Per-user SP grant required.** Each participant must grant the app's Service
> Principal access to their Lakebase project. This happens automatically in Step 6
> of `00_Setup_Lakebase_Project`, or can be done from the App Deployment lab.

### 3. Run the foundation (all participants)

Each participant opens `notebooks/00_Setup_Lakebase_Project` and clicks **Run All**.
This creates their personal Lakebase project (`lakebase-lab-<username>`), seeds a
per-user schema (`lakebase_lab_<username>`), and grants the Lab Console app's SP
access to their project (Step 6).

### 4. Open the Lab Console

Once the foundation is complete, participants can open the Lab Console from
**Compute → Apps → lakebase-lab-console**. The app will show their project,
tables, and data automatically.

### 5. Choose lab paths (notebooks or app — unified experience)

Every lab is available **two ways**, and participants can switch between them freely:

- **Notebook path:** Open a lab notebook and run cells step-by-step. Each notebook includes a clickable banner linking to the corresponding app page.
- **App path:** Open the Lab Console and navigate to a lab page. Each page includes a banner linking back to the corresponding notebook.

The cross-links use URL hashes (e.g., `#data`, `#agent`, `#branches`) so participants can deep-link between the two experiences. This means:
- A facilitator can say *"open the app and go to Data Ops"* or *"open the Data Operations notebook"* — both cover the same material.
- Participants who prefer visual UI can stay in the app; those who prefer code can stay in notebooks.

For a guided workshop, direct participants to specific paths based on the timing options above.

## Demo Script

### Foundation — Architecture & Setup (all tracks)

1. Walk through the architecture diagrams (resource hierarchy, platform fit)
2. Run the project creation — takes ~2 min
3. Show the seeded tables and products
4. Key talking point: *"Fully managed PostgreSQL, no infrastructure to configure."*

---

### Application Builders Track

#### Data Operations — CRUD & JSONB

1. Run a JSONB metadata query (`metadata @> '{"brand": "SoundMax"}'`)
2. Show array filtering with `ANY` and `&&`
3. Insert → update → delete a product, then check the audit log
4. Run a transaction, show atomicity
5. Key talking point: *"Full PostgreSQL — JSONB, arrays, triggers, transactions."*

#### Agentic Memory

1. Create a session, store a multi-turn conversation
2. Query conversation history
3. Show cross-session JSONB queries
4. Key talking point: *"Persistent agent memory with no extra infrastructure."*

#### App Deployment (capstone)

1. Walk through the Lab Console architecture (React + FastAPI + Lakebase)
2. Show how the app routes each user to their own project via email-based routing
3. Explain the SP auth model: why user tokens lack the `postgres` scope, and how the SP bridges the gap
4. Key talking point: *"A full-stack app running on Databricks, backed by Lakebase — deployed once, serves everyone."*

---

### Data & ML Engineers Track

#### Reverse ETL — Synced Tables

1. Create a Delta table with CDF enabled
2. Set up a synced table pointing to Lakebase
3. Check sync status
4. Key talking point: *"Your analytics lakehouse data, served at OLTP speed."*

#### Lakehouse Sync — Lakebase → Delta *(Beta, UI walkthrough)*

1. Confirm the **Lakehouse Sync** preview is enabled (workspace Previews page)
2. From the Lakebase project UI, configure a sync from a `databricks_postgres` table to a Unity Catalog destination
3. Make a few row-level changes in Postgres (inserts / updates / deletes)
4. Open the destination Delta table — show the SCD Type 2 history rows accumulating
5. Key talking point: *"Lakebase moves data both ways natively — Reverse ETL pushes Delta in, Lakehouse Sync streams Postgres changes back out with full CDC history."*
6. **Note:** This lab is a placeholder — the SDK/API is not yet GA, so the demo runs entirely from the workspace UI. See `labs/lakehouse-sync/README.md`.

#### Online Feature Store

1. Create a feature table with primary key and CDF
2. Provision an online store — show that it creates a Lakebase Autoscaling instance
3. Publish features, add new rows, re-publish
4. Connect directly to the online store via PostgreSQL
5. Key talking point: *"Your online feature store IS Lakebase — same managed PostgreSQL, optimized for ML serving."*
6. **Note:** Requires DBR 16.4 LTS ML or serverless. Online store provisioning takes 2–4 minutes.

---

### Platform Architects Track

#### Development Experience — Branching

1. Show the production branch (default, protected)
2. Create `lab-dev-01` with a 24h TTL
3. Create a `reviews` table on the dev branch
4. Show it does NOT exist on production
5. Key talking point: *"This is like Git for your database — instant, isolated clones."*

#### Development Experience — Autoscaling

1. Show the production endpoint's current CU range
2. Walk through the CU sizing reference table
3. Explain the max 8 CU spread constraint
4. Mention scale-to-zero for non-production branches
5. Key talking point: *"You pay for what you use. Dev branches cost nothing when idle."*

#### Authentication — Tokens & Permissions

1. Generate a credential, decode the JWT
2. Show the 1-hour expiry and refresh pattern
3. List roles — show how identities map
4. Show connection details for external tools
5. Key talking point: *"No static passwords. OAuth tokens with automatic rotation."*

#### Backup & Recovery — PITR

1. Create a snapshot branch (instant)
2. Simulate disaster on a work branch (drop table)
3. Recover by branching from the snapshot
4. Explain PITR and the 35-day window
5. Key talking point: *"Backups are always on. Recovery is instant via branching."*

#### Observability — Monitoring

1. Show database-level stats (cache hit %, connections, commits)
2. Walk through table-level activity (seq scans vs index scans)
3. Show index usage — point out any unused indexes
4. Show active connections
5. Key talking point: *"All standard PostgreSQL observability — plus the workspace monitoring UI."*

## Architecture

### App Request Flow

```
Browser (React Lab Console)
    |
    v
Databricks App Proxy (injects X-Forwarded-Email header)
    |
    v
FastAPI Backend (shared Databricks App: lakebase-lab-console)
    |
    +---> X-Forwarded-Email → derive project_id + schema (routing)
    |
    +---> App SP (WorkspaceClient) → generate_database_credential()
    |          for the user's project endpoint
    |
    +---> psycopg3 (user=SP_CLIENT_ID) → user's Lakebase project
    |          (search_path = user's schema)
    |
    v
User's Lakebase Project (lakebase-lab-<username>)
    Project > Branch > Endpoint
```

### Per-User Resource Hierarchy

```
Databricks Workspace
└── Lakebase Project: lakebase-lab-<username>    (one per user)
    └── Branch: production
        └── Endpoint (autoscaling, 0.5+ CU)
            └── Database: databricks_postgres
                └── Schema: lakebase_lab_<username>
                    └── Tables: products, events, agent_sessions, ...
```

### Lab Console — App Page / Notebook Cross-Reference

| App Page | Feature | Corresponding Notebook |
|----------|---------|----------------------|
| Data Ops (`#data`) | CRUD, JSONB queries, audit log | `labs/data-operations/Data_Operations` |
| Branch Manager (`#branches`) | Create/delete branches | `labs/development-experience/Branches_and_Environments` |
| Autoscale Demo (`#autoscale`) | Load testing + live CU tracking | `labs/development-experience/Autoscaling_and_Compute` |
| Compute (`#compute`) | Resize CU ranges | `labs/development-experience/Autoscaling_and_Compute` |
| Observability (`#observability`) | pg_stat views, index stats | `labs/observability/Observability_and_Monitoring` |
| Reverse ETL (`#sync`) | Synced table status | `labs/reverse-etl/Reverse_ETL` |
| Feature Store (`#feature-store`) | Online store status | `labs/online-feature-store/Online_Feature_Store` |
| Agent Memory (`#agent`) | Session/message management | `labs/agentic-memory/Agent_Memory` |
| Auth & Permissions (`#auth`) | OAuth tokens, roles, grants | `labs/authentication/Authentication_and_Permissions` |
| Backup & Recovery (`#backup`) | Snapshots, PITR | `labs/backup-recovery/Backup_and_Recovery` |
| API Tester (`#api`) | Raw SQL execution | *(tools-only, no notebook)* |

### Shared App with Per-User Routing (SP Auth + Email Routing)

The Lab Console is deployed **once** and shared by all workshop participants. When a user
opens the app, it reads their email from the Databricks Apps proxy headers and
connects to **their** Lakebase project automatically:

- User email → project ID (`lakebase-lab-<username>`) and schema
- The app's Service Principal → SDK calls and database credentials
- Each user grants the SP access to their project during setup (Step 6)

The facilitator deploys the app once with `databricks bundle deploy`. Each user runs
`00_Setup_Lakebase_Project` (which includes granting SP access) and opens the app.

See [PERMISSIONS.md](PERMISSIONS.md) for full details on the two-layer permission model.

## Repository Structure

```
Lakebase-Workshop/
├── setup.sh                                    # ← Start here
├── databricks.yml                              # Bundle config
├── notebooks/                                  # Foundation (run first)
│   └── 00_Setup_Lakebase_Project.py
├── labs/                                       # Lab paths (pick your adventure)
│   ├── _setup.py                               # Shared setup (auto-loaded by each lab)
│   ├── README.md                               # Path index
│   ├── development-experience/                 # Branching + Autoscaling
│   │   ├── Branches_and_Environments.py
│   │   └── Autoscaling_and_Compute.py
│   ├── data-operations/                        # CRUD, JSONB, Advanced SQL
│   │   ├── Data_Operations.py
│   │   └── Advanced_Postgres.sql
│   ├── reverse-etl/                            # Synced tables from Delta
│   │   └── Reverse_ETL.py
│   ├── lakehouse-sync/                         # Lakebase → Delta CDC (Beta, UI-only placeholder)
│   │   └── README.md
│   ├── observability/                          # pg_stat views, monitoring
│   │   └── Observability_and_Monitoring.py
│   ├── backup-recovery/                        # PITR, snapshots
│   │   └── Backup_and_Recovery.py
│   ├── agentic-memory/                         # Agent memory pattern
│   │   └── Agent_Memory.py
│   ├── authentication/                         # OAuth, roles, permissions
│   │   └── Authentication_and_Permissions.py
│   ├── online-feature-store/                   # Online Feature Store (ML serving)
│   │   └── Online_Feature_Store.py
│   └── app-deployment/                         # Lab Console (capstone)
│       └── Deploy_Lab_Console_App.py
├── apps/lakebase-lab-console/                  # Lab Console app (shared)
│   ├── app.yaml                                # Databricks Apps config (postgres resource + env)
│   ├── app.py                                  # FastAPI entry point
│   ├── backend/                                # FastAPI routes, user context, connection manager
│   │   ├── user_context.py                     # User identity from forwarded headers
│   │   ├── db.py                               # SP-based connection manager with per-user routing
│   │   └── routes_*.py                         # API routes
│   └── frontend/                               # React (Vite) UI
├── bootstrap/
│   ├── seed.sql                                # Demo schema DDL (used by notebook 00)
│   └── requirements.txt                        # Python deps for local use
└── docs/
    ├── WORKSHOP_FACILITATOR.md
    ├── PERMISSIONS.md
    └── CREDITS.md
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `setup.sh` fails at auth | Run `databricks auth login --host <url> --profile lakebase-workshop` manually |
| Foundation hangs on "Waiting for endpoint" | Endpoint creation can take 2–3 minutes. Let it run. |
| "password authentication failed" | Token expired (1h TTL). Re-run the connection cell. |
| Lab Console shows "Project Not Found" | The user hasn't run `00_Setup_Lakebase_Project` yet. |
| Lab Console shows "permission denied for schema" | The user hasn't granted the SP access (Step 6 in setup notebook). Run the App Deployment lab. |
| Lab Console shows "Loading..." forever | Check `/api/dbtest` — likely a token or endpoint issue |
| Lab Console shows wrong user | Hard-refresh the browser to pick up fresh headers |
| "does not have required scopes: postgres" | The app's postgres resource is not attached. Re-run `setup.sh` with option 2, or attach manually in the Apps UI. |
| `function databricks_create_role(...) does not exist` | The `databricks_auth` extension isn't installed in the Postgres database. Run `CREATE EXTENSION IF NOT EXISTS databricks_auth;` (idempotent, per-database). The current setup notebook + App Deployment lab do this automatically in Step 6. |
| Facilitator deploys app and sees "project wasn't there" | `setup.sh` now performs a pre-flight check before option 2 and offers to auto-create the project (or run the notebook manually first). |

## Cleanup

Participants can delete their projects by uncommenting the cleanup cell at the bottom of the foundation notebook, or by running:

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
w.postgres.delete_project(name="projects/lakebase-lab-<username>")
```

Or leave them running — branches with TTLs will auto-expire.
