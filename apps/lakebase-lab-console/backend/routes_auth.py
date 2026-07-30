"""Authentication & Permissions routes."""

import base64
import json
import os

from fastapi import APIRouter, Depends, HTTPException

from .db import execute_query, get_project_id, get_schema
from .security import log_and_sanitize
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Only these JWT claims are surfaced to the browser for the teaching demo. This
# avoids echoing back every claim (which can include internal ids/scopes) while
# still showing the identity + validity window the lesson is about.
_ALLOWED_JWT_CLAIMS = ("sub", "iss", "aud", "exp", "iat", "nbf", "token_type")


@router.get("/credential")
def generate_credential(user: UserContext = Depends(get_current_user)):
    """Generate an OAuth database credential and decode its JWT payload.

    The token itself is never returned; only a short non-reusable preview, its
    length/expiry, and an allowlisted subset of JWT claims for the lesson.
    """
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
                decoded = json.loads(base64.urlsafe_b64decode(payload))
                jwt_claims = {k: decoded[k] for k in _ALLOWED_JWT_CLAIMS if k in decoded}
            except Exception:
                pass

        return {
            "token_preview": cred.token[:12] + "...",
            "token_length": len(cred.token),
            "expire_time": str(cred.expire_time),
            "jwt_claims": jwt_claims,
        }
    except HTTPException:
        raise
    except Exception as e:
        log_and_sanitize(e, "Failed to generate credential", context="/api/auth/credential")
        raise HTTPException(500, "Failed to generate credential")


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
        log_and_sanitize(e, "Failed to list roles", context="/api/auth/roles")
        raise HTTPException(500, "Failed to list roles")


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
        log_and_sanitize(e, "Failed to list grants", context="/api/auth/grants")
        raise HTTPException(500, "Failed to list grants")


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
        log_and_sanitize(e, "TLS status unavailable", context="/api/auth/tls")
        return {"ssl": None, "note": "TLS status unavailable"}


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
        log_and_sanitize(e, "Failed to get connection info", context="/api/auth/connection-info")
        raise HTTPException(500, "Failed to get connection info")
