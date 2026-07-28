"""
Lakebase Lab Console -- FastAPI application entry point.

Serves the React frontend as static files and exposes API routes
for branch management, compute, load testing, CRUD, and agent memory.

In shared-app mode, each logged-in user is routed to their own Lakebase
project based on their Databricks identity (forwarded by the Apps proxy).
"""

import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.user_context import UserContext, get_current_user
from backend.routes_branches import router as branches_router
from backend.routes_compute import router as compute_router
from backend.routes_loadtest import router as loadtest_router
from backend.routes_data import router as data_router
from backend.routes_agent import router as agent_router
from backend.routes_observability import router as observability_router
from backend.routes_online_tables import router as online_tables_router
from backend.routes_auth import router as auth_router
from backend.routes_data_api import router as data_api_router
from backend.routes_search import router as search_router

app = FastAPI(
    title="Lakebase Lab Console",
    description="Interactive workshop app for exploring Databricks Lakebase",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(branches_router)
app.include_router(compute_router)
app.include_router(loadtest_router)
app.include_router(data_router)
app.include_router(agent_router)
app.include_router(observability_router)
app.include_router(online_tables_router)
app.include_router(auth_router)
app.include_router(data_api_router)
app.include_router(search_router)

STATIC_DIR = Path(__file__).parent / "frontend" / "dist"


@app.get("/api/whoami")
def whoami(user: UserContext = Depends(get_current_user)):
    """Return the logged-in user's identity and derived Lakebase context."""
    return {
        "email": user.email,
        "project_id": user.project_id,
        "schema": user.schema,
        "branch_id": user.branch_id,
        "is_local": user._is_local,
    }


@app.get("/api/health")
def health(user: UserContext = Depends(get_current_user)):
    return {
        "status": "ok",
        "project_id": user.project_id,
        "schema": user.schema,
        "user": user.email,
        "frontend_built": STATIC_DIR.exists(),
    }


@app.get("/api/config")
def get_config(user: UserContext = Depends(get_current_user)):
    host = os.getenv("DATABRICKS_HOST", "")
    if host and not host.startswith("https://"):
        host = f"https://{host}"
    bundle_target = os.getenv("BUNDLE_TARGET", "dev")
    notebook_base_url = ""
    if host and user.email:
        notebook_base_url = (
            f"{host}/#workspace/Users/{user.email}"
            f"/.bundle/lakebase-workshop/{bundle_target}/files"
        )
    app_name = os.getenv("DATABRICKS_APP_NAME", "lakebase-lab-console")
    app_url = f"{host}/apps/{app_name}" if host else ""
    return {
        "project_id": user.project_id,
        "branch_id": user.branch_id,
        "database": "databricks_postgres",
        "schema": user.schema,
        "pghost_set": bool(os.getenv("PGHOST")),
        "workspace_host": host,
        "user_email": user.email,
        "notebook_base_url": notebook_base_url,
        "app_url": app_url,
    }


@app.get("/api/dbtest")
def db_test(user: UserContext = Depends(get_current_user)):
    try:
        from backend.db import execute_query
        result = execute_query(user, "SELECT version() as version, current_database() as db")
        return {"db_connected": True, "info": result[0]}
    except Exception as e:
        error_msg = str(e)
        is_no_project = "No endpoints" in error_msg or "setup notebook" in error_msg.lower()
        return {
            "db_connected": False,
            "error": error_msg,
            "needs_setup": is_no_project,
        }


# Serve the pre-built React SPA from frontend/dist/.
# The frontend must be built before deployment (npm run build).
if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = STATIC_DIR / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
