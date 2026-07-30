"""Data API (PostgREST) routes — guarded interactive helper.

The Lab Console's Service Principal is a *non-owner* identity, which makes it a
valid Data API caller (the project owner cannot call the Data API). These routes
let the workshop UI:

  - detect whether the Data API is enabled (the `authenticator` role exists) and
    whether the app SP's role is prepared,
  - prepare the app SP's Postgres role + grants (best-effort; usually must run as
    the project owner, so the equivalent SQL is always returned for manual use),
  - proxy sample HTTP calls to the Data API using the SP's OAuth token.

Tenant safety: the proxy target is resolved *server-side* from the caller's own
project (`w.postgres.get_data_api`), so a client cannot point the shared SP
token at another participant's project. Any client-supplied URL must normalize
to the caller's resolved endpoint. Redirects are never followed and response
bodies are size-capped (token-exfiltration / SSRF / DoS guards).
"""

import json
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .db import execute_query, execute_write, get_schema, _get_sp_username, _get_workspace_client
from .security import (
    OutboundHTTPError,
    is_valid_pg_ident,
    is_valid_schema,
    log_and_sanitize,
    outbound_request,
)
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/data-api", tags=["data-api"])

_DATABASE_ID = "databricks_postgres"


def _resolve_data_api_url(user: UserContext) -> str | None:
    """Resolve the caller's own Data API base URL via the Postgres SDK.

    This is the *trusted* endpoint for the caller's project. Returns None when
    the Data API is not enabled or the SDK/endpoint is unavailable.
    """
    w = _get_workspace_client()
    get_data_api = getattr(getattr(w, "postgres", None), "get_data_api", None)
    if get_data_api is None:
        return None
    name = (
        f"projects/{user.project_id}/branches/{user.branch_id}"
        f"/databases/{_DATABASE_ID}/data-api"
    )
    try:
        data_api = get_data_api(name=name)
    except Exception:
        return None
    url = getattr(getattr(data_api, "status", None), "url", None)
    return _normalize_url(url) if url else None


def _normalize_url(url: str) -> str:
    """Normalize scheme+host+path for equality comparison (drop query/fragment)."""
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower()
    port = f":{parts.port}" if parts.port else ""
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, f"{host}{port}", path, "", ""))


def _assert_matches_resolved(url: str, resolved: str | None) -> str:
    """Ensure a client-supplied Data API URL is the caller's own resolved endpoint.

    Returns the trusted base URL (the resolved one) to use for the call.
    """
    if resolved is None:
        raise HTTPException(
            400,
            "The Data API endpoint for your project could not be resolved. Enable "
            "the Data API in your Lakebase project's API tab first. The app only "
            "calls your own project's Data API.",
        )
    if url and _normalize_url(url) != resolved:
        raise HTTPException(
            403,
            "The provided Data API URL does not match your project's endpoint. For "
            "safety the app only calls your own project's Data API. Use the API URL "
            "shown for your project.",
        )
    return resolved


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
        # Trusted, server-resolved Data API base URL for THIS caller's project.
        # The UI prefills this so participants never paste another project's URL.
        "data_api_url": _resolve_data_api_url(user),
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
    if not is_valid_schema(schema):
        raise HTTPException(400, "Invalid schema name.")

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
    """Proxy an HTTP call to the caller's own Data API using the SP OAuth token.

    The base URL is always the caller's server-resolved endpoint; a client URL
    is only accepted when it exactly matches. Schema and resource are validated
    as identifiers, redirects are not followed, and the response is size-capped.
    """
    resolved = _resolve_data_api_url(user)
    base = _assert_matches_resolved(req.url, resolved)

    schema = (req.schema_path or get_schema(user)).strip("/")
    if not is_valid_schema(schema):
        raise HTTPException(400, "Invalid schema name.")
    resource = req.resource.strip("/")
    if not is_valid_pg_ident(resource):
        raise HTTPException(400, "Invalid resource (table) name.")

    target = f"{base}/{schema}/{resource}"
    if req.query:
        target += "?" + req.query.lstrip("?")

    method = req.method.upper()
    if method not in ("GET", "POST", "PATCH", "DELETE"):
        raise HTTPException(400, f"Unsupported method: {method}")

    # The SP bearer token is attached only after every check has passed, and the
    # request goes exclusively to the caller's own resolved Data API endpoint.
    w = _get_workspace_client()
    token = w.config.oauth_token().access_token
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    data = None
    if method in ("POST", "PATCH") and req.body is not None:
        data = json.dumps(req.body).encode()
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=representation"

    try:
        status_code, body = outbound_request(
            target, method=method, headers=headers, data=data
        )
    except OutboundHTTPError as e:
        log_and_sanitize(e, str(e), context="/api/data-api/call")
        raise HTTPException(e.status, str(e))
    return {"status": status_code, "url": target, "body": body}
