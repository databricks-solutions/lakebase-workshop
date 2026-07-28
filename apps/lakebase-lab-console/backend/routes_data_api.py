"""Data API (PostgREST) routes — guarded interactive helper.

The Lab Console's Service Principal is a *non-owner* identity, which makes it a
valid Data API caller (the project owner cannot call the Data API). These routes
let the workshop UI:

  - detect whether the Data API is enabled (the `authenticator` role exists) and
    whether the app SP's role is prepared,
  - prepare the app SP's Postgres role + grants (best-effort; usually must run as
    the project owner, so the equivalent SQL is always returned for manual use),
  - proxy sample HTTP calls to the Data API using the SP's OAuth token.

Nothing here is irreversible. The proxy only sends the SP token to Databricks
hosts (SSRF / token-exfiltration guard).
"""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .db import execute_query, execute_write, get_schema, _get_sp_username, _get_workspace_client
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/data-api", tags=["data-api"])

# The SP OAuth token is only ever sent to hosts under these suffixes.
_ALLOWED_HOST_SUFFIXES = (
    ".databricks.com",
    ".azuredatabricks.net",
    ".gcp.databricks.com",
    ".databricks.net",
)


def _workspace_domain() -> str:
    host = os.getenv("DATABRICKS_HOST", "")
    return urlparse(host if host.startswith("http") else f"https://{host}").hostname or ""


def _assert_allowed(url: str) -> str:
    """Validate the Data API URL: https + a Databricks host. Returns the hostname."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise HTTPException(400, "Data API URL must use https://")
    host = parsed.hostname or ""
    ws = _workspace_domain()
    allowed = host.endswith(_ALLOWED_HOST_SUFFIXES) or (ws and host == ws)
    if not allowed:
        raise HTTPException(
            400,
            "For safety the app only calls the Data API on Databricks hosts "
            f"(got '{host}'). Paste the API URL from your Lakebase project's API tab.",
        )
    return host


@router.get("/status")
def status(user: UserContext = Depends(get_current_user)):
    """Report Data API enablement and whether the app SP's role is prepared."""
    sp = _get_sp_username()
    schema = get_schema(user)
    enabled = sp_role_exists = sp_can_assume = False

    try:
        enabled = bool(execute_query(user, "SELECT 1 FROM pg_roles WHERE rolname = 'authenticator'"))
    except Exception:
        pass

    if sp:
        try:
            sp_role_exists = bool(execute_query(user, "SELECT 1 FROM pg_roles WHERE rolname = %s", (sp,)))
        except Exception:
            pass
        try:
            sp_can_assume = bool(execute_query(
                user,
                """
                SELECT 1
                FROM pg_auth_members m
                JOIN pg_roles r   ON m.roleid = r.oid
                JOIN pg_roles mem ON m.member = mem.oid
                WHERE r.rolname = 'authenticator' AND mem.rolname = %s
                """,
                (sp,),
            ))
        except Exception:
            pass

    return {
        "enabled": enabled,
        "sp_app_id": sp,
        "schema": schema,
        "sp_role_exists": sp_role_exists,
        "sp_can_assume": sp_can_assume,
        "workspace_domain": _workspace_domain(),
    }


def _prepare_statements(sp: str, schema: str) -> list[tuple[str, tuple | None]]:
    return [
        ("CREATE EXTENSION IF NOT EXISTS databricks_auth;", None),
        ("SELECT databricks_create_role(%s, 'SERVICE_PRINCIPAL');", (sp,)),
        (f'GRANT "{sp}" TO authenticator;', None),
        (f'GRANT USAGE ON SCHEMA {schema} TO "{sp}";', None),
        (f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO "{sp}";', None),
        (f'GRANT USAGE ON ALL SEQUENCES IN SCHEMA {schema} TO "{sp}";', None),
    ]


def _prepare_sql_text(sp: str, schema: str) -> str:
    return "\n".join(
        s.replace("%s", f"'{sp}'") if p else s
        for s, p in _prepare_statements(sp, schema)
    )


@router.post("/prepare")
def prepare(user: UserContext = Depends(get_current_user)):
    """Best-effort: create + grant the app SP's Postgres role for the Data API.

    Role creation typically requires the project owner, so this may fail when run
    as the SP. The equivalent SQL is always returned so it can be run in a
    notebook as the owner.
    """
    sp = _get_sp_username()
    schema = get_schema(user)
    if not sp:
        raise HTTPException(400, "No Service Principal application id is configured for this app.")

    sql = _prepare_sql_text(sp, schema)
    errors = []
    for stmt, params in _prepare_statements(sp, schema):
        try:
            execute_write(user, stmt, params)
        except Exception as e:
            errors.append({"statement": stmt, "error": str(e)})

    return {
        "ok": not errors,
        "sql": sql,
        "errors": errors,
        "note": (
            "If statements failed, the app's Service Principal likely lacks role-management "
            "privileges. Run the SQL above in a notebook as the project owner, or from the "
            "Data API lab (labs/data-api/)."
        ),
    }


class CallRequest(BaseModel):
    url: str
    schema_path: str | None = None
    resource: str = "api_clients"
    method: str = "GET"
    query: str | None = None
    body: dict | None = None


@router.post("/call")
def call(req: CallRequest, user: UserContext = Depends(get_current_user)):
    """Proxy an HTTP call to the Data API using the app SP's OAuth token."""
    _assert_allowed(req.url)
    base = req.url.rstrip("/")
    schema = (req.schema_path or get_schema(user)).strip("/")
    target = f"{base}/{schema}/{req.resource.lstrip('/')}"
    if req.query:
        target += "?" + req.query.lstrip("?")

    method = req.method.upper()
    if method not in ("GET", "POST", "PATCH", "DELETE"):
        raise HTTPException(400, f"Unsupported method: {method}")

    w = _get_workspace_client()
    token = w.config.oauth_token().access_token
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    data = None
    if method in ("POST", "PATCH") and req.body is not None:
        data = json.dumps(req.body).encode()
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=representation"

    request_obj = urllib.request.Request(target, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request_obj, timeout=30) as resp:
            return {"status": resp.status, "url": target, "body": resp.read().decode(errors="replace")}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "url": target, "body": e.read().decode(errors="replace")}
    except Exception as e:
        raise HTTPException(502, f"Request to Data API failed: {e}")
