"""Authentication & Permissions routes."""

import base64
import json
import os

from fastapi import APIRouter, Depends, HTTPException

from .db import execute_query, get_project_id, get_schema
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/credential")
def generate_credential(user: UserContext = Depends(get_current_user)):
    """Generate an OAuth database credential and decode its JWT payload."""
    try:
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        project_id = get_project_id(user)
        branch_id = user.branch_id

        endpoints = list(
            w.postgres.list_endpoints(
                parent=f"projects/{project_id}/branches/{branch_id}"
            )
        )
        if not endpoints:
            raise HTTPException(404, "No endpoints found")

        cred = w.postgres.generate_database_credential(endpoint=endpoints[0].name)

        jwt_claims = {}
        parts = cred.token.split(".")
        if len(parts) >= 2:
            payload = parts[1]
            payload += "=" * (4 - len(payload) % 4)
            try:
                jwt_claims = json.loads(base64.urlsafe_b64decode(payload))
            except Exception:
                pass

        return {
            "token_preview": cred.token[:40] + "...",
            "token_length": len(cred.token),
            "expire_time": str(cred.expire_time),
            "jwt_claims": jwt_claims,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to generate credential: {e}")


@router.get("/roles")
def list_roles(user: UserContext = Depends(get_current_user)):
    """List PostgreSQL roles (filtered)."""
    try:
        rows = execute_query(user, """
            SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin
            FROM pg_roles
            WHERE rolname NOT LIKE 'pg_%%' AND rolname != 'rdsadmin'
            ORDER BY rolname
        """)
        return rows
    except Exception as e:
        raise HTTPException(500, f"Failed to list roles: {e}")


@router.get("/grants")
def list_grants(user: UserContext = Depends(get_current_user)):
    """List table grants for the configured schema."""
    try:
        schema = get_schema(user)
        rows = execute_query(
            user,
            """
            SELECT grantee, privilege_type, table_name
            FROM information_schema.table_privileges
            WHERE table_schema = %s
            ORDER BY table_name, grantee, privilege_type
            """,
            (schema,),
        )
        return rows
    except Exception as e:
        raise HTTPException(500, f"Failed to list grants: {e}")


@router.get("/tls")
def tls_status(user: UserContext = Depends(get_current_user)):
    """Report the live TLS status of this connection (pg_stat_ssl).

    Guarded: returns ssl=False with a note if the view is unavailable rather
    than raising, so the Security & Compliance panel always renders.
    """
    try:
        rows = execute_query(
            user,
            """
            SELECT ssl, version, cipher, bits
            FROM pg_stat_ssl
            WHERE pid = pg_backend_pid()
            """,
        )
        if rows:
            return rows[0]
        return {"ssl": False, "note": "No pg_stat_ssl row for this backend"}
    except Exception as e:
        return {"ssl": None, "note": f"TLS status unavailable: {e}"}


@router.get("/connection-info")
def connection_info(user: UserContext = Depends(get_current_user)):
    """Return connection details for external tools."""
    try:
        from databricks.sdk import WorkspaceClient

        project_id = get_project_id(user)
        branch_id = user.branch_id

        w = WorkspaceClient()
        sp_username = os.getenv("PGUSER") or os.getenv("DATABRICKS_CLIENT_ID", "")
        host = ""
        if project_id:
            endpoints = list(
                w.postgres.list_endpoints(
                    parent=f"projects/{project_id}/branches/{branch_id}"
                )
            )
            if endpoints:
                ep = w.postgres.get_endpoint(name=endpoints[0].name)
                host = ep.status.hosts.host

        return {
            "host": host or "N/A",
            "port": 5432,
            "database": "databricks_postgres",
            "username": sp_username,
            "ssl_mode": "require",
            "project_id": project_id,
            "branch_id": branch_id,
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to get connection info: {e}")
