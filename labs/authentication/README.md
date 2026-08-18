# Authentication, Security & Compliance

Understand Lakebase's security model end to end: workspace-level IAM, database-level PostgreSQL roles, and the platform's encryption, networking, and compliance posture.

## Labs

| Lab | What You'll Learn |
|-----|-------------------|
| `Authentication_and_Permissions` | Generate OAuth tokens, inspect JWT claims, manage role grants, connect external tools, and review encryption / Private Link / compliance |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)

## Key Concepts

- **Two-layer permissions** — Workspace IAM (who can access the project) + PostgreSQL roles (what they can do inside the database)
- **OAuth tokens** — 1-hour TTL at login; best for notebooks/apps that can rotate credentials
- **Postgres passwords** — preferred for psql/pgAdmin/DBeaver (no hourly refresh); disabled by default on new projects until enabled in Settings
- **Connection limits** — 24-hour idle timeout, 3-day max connection life; PgBouncer requires password auth (`-pooler` host, port 5432)
- **Encryption** — TLS 1.2+ in transit, AES-256 at rest, per-project DEK/KEK envelope; **Customer-Managed Keys (CMK)** GA for Enterprise (new projects)
- **Network isolation** — inbound **Private Link** (GA) for private connectivity
- **Compliance** — HIPAA, C5, TISAX, SOC 2 Type 2 (tier/region dependent)
- **Limitation** — no Postgres audit logs yet; use `pg_stat_statements` (Observability lab) + Databricks control-plane audit logs

## Documentation

- [Authentication](https://docs.databricks.com/aws/en/oltp/projects/authentication)
- [Manage Postgres roles](https://docs.databricks.com/aws/en/oltp/projects/postgres-roles)
- [Manage permissions](https://docs.databricks.com/aws/en/oltp/projects/manage-roles-permissions)
- [Roles and permissions](https://docs.databricks.com/aws/en/oltp/projects/roles-permissions)
- [Private Link](https://docs.databricks.com/aws/en/oltp/projects/private-link)
