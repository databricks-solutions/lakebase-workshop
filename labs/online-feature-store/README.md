# Online Feature Store

Use your existing Lakebase Autoscaling project as a high-performance online feature store for real-time ML serving — recommendation systems, fraud detection, and personalization engines.

## Labs

| Lab | What You'll Learn |
|-----|-------------------|
| `Online_Feature_Store` | Create feature tables, publish features to your existing Lakebase project, query via PostgreSQL |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)
- **DBR 16.4 LTS ML** or **serverless** compute
- A Unity Catalog catalog & schema with write access

## Key Concepts

- **Online Feature Store** — A Lakebase Autoscaling project that serves feature data at low latency. You can reuse an existing project rather than provisioning a dedicated instance ([docs](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store)).
- **Feature table** — A Delta table in Unity Catalog with a primary key and [Change Data Feed](https://docs.databricks.com/aws/en/delta/delta-change-data-feed) enabled
- **Publish modes** — [TRIGGERED (on-demand sync), CONTINUOUS (streaming), or SNAPSHOT (full copy)](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store#publish-modes)
- **Feature Serving endpoints** — [REST API endpoints](https://docs.databricks.com/aws/en/machine-learning/feature-store/feature-function-serving) that resolve features from online stores automatically
- **Lakebase under the hood** — The online store IS a Lakebase PostgreSQL instance, queryable with standard tools

## Architecture

```
Lakebase Autoscaling Project (lakebase-lab-<you>)
  └── Branch: production
        └── Database: databricks_postgres
              ├── Schema: lakebase_lab_<you>   (workshop tables: products, events, etc.)
              └── Schema: main__lakebase_*     (feature tables published by FE client)

Offline Feature Table (Delta/UC)
    │
    │  fe.publish_table()
    │  (TRIGGERED / CONTINUOUS / SNAPSHOT)
    ▼
Same Lakebase Project (no separate instance)
    │
    ├──→ Feature Serving Endpoint (REST API for real-time apps)
    │
    └──→ Direct PostgreSQL access (SQL editor, psycopg, etc.)
```

## Cost Notes

- This lab reuses your existing Lakebase project — no additional instance costs
- The [docs recommend](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store) sharing a single online store across multiple feature tables
- Multiple feature tables can be published to the same project

## Documentation

- [Databricks Online Feature Stores](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store)
- [Feature Serving endpoints](https://docs.databricks.com/aws/en/machine-learning/feature-store/feature-function-serving)
- [Use features in online workflows](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-workflows)
- [Feature Engineering in Databricks](https://docs.databricks.com/aws/en/machine-learning/feature-store/)
- [Lakebase Autoscaling](https://docs.databricks.com/aws/en/oltp/projects/)
