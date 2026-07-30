# App Deployment

Deploy the Lab Console — a full-stack React + FastAPI application that uses Lakebase as its backend database.

## Labs

| Lab | What You'll Learn |
|-----|-------------------|
| `Deploy_Lab_Console_App` | Build the frontend, deploy via Databricks Apps, configure Lakebase as an app resource |

## Prerequisites

- Complete **`00_Setup_Lakebase_Project`** (foundation)
- Run `setup.sh` and deploy via DABs (the pre-built frontend is included)

## What the Lab Console Includes

| Module | Feature |
|--------|---------|
| Branch Manager | Create/delete branches from the UI |
| Autoscaling Dashboard | Resize compute and monitor CU ranges |
| Load Tester | Generate synthetic traffic, stream live metrics |
| Data Playground | CRUD operations, audit log viewer |
| Reverse ETL | Synced table status |
| API Tester | Raw SQL execution against any branch |
| Agent Memory | Session/message management |

## Notes

This path is best done after exploring other lab paths, since the app ties together all the features covered across the workshop. See `docs/PERMISSIONS.md` for Service Principal grants required by the app.

## Documentation

- [Connect an application](https://docs.databricks.com/aws/en/oltp/projects/connect-application)
- [Databricks Apps tutorial (Lakebase)](https://docs.databricks.com/aws/en/oltp/projects/tutorial-databricks-apps-autoscaling)
