"""User identity extraction from Databricks Apps forwarded headers.

When a user accesses a Databricks App, the auth proxy injects identity headers
into every request. This module reads those headers, derives the user's Lakebase
project ID and schema, and provides a FastAPI dependency for injection.

The email is used for routing only (deriving project_id and schema). All SDK
calls and database connections are performed by the app's Service Principal.

Security model: in deployed ("apps") mode the forwarded identity is required —
if it is absent the request is rejected (401) rather than silently falling back
to an ambient Service Principal identity. The local-development fallback only
applies in "local" mode (or when explicitly opted in), so a deployed app can
never route to a project without a verified caller.

In local development (no headers), falls back to env vars or default SDK auth.
"""

import logging
import os
import re
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from .security import get_auth_mode

logger = logging.getLogger(__name__)


def _sanitize_email(email: str) -> str:
    """Match the sanitization logic from 00_Setup_Lakebase_Project.py."""
    name = email.split("@")[0]
    name = re.sub(r"[^a-z0-9-]", "-", name.lower())
    return re.sub(r"-+", "-", name).strip("-")


@dataclass
class UserContext:
    """Per-request user identity and Lakebase project context.

    The forwarded user access token is intentionally NOT stored: all SDK and
    database access uses the app's Service Principal, so retaining a user token
    only adds credential surface with no benefit.
    """

    email: str
    project_id: str = ""
    schema: str = ""
    branch_id: str = "production"
    _is_local: bool = field(default=False, repr=False)

    def __post_init__(self):
        if not self.project_id and self.email:
            sanitized = _sanitize_email(self.email)
            self.project_id = f"lakebase-lab-{sanitized}"
        if not self.schema and self.project_id:
            self.schema = self.project_id.replace("-", "_")


_local_context: UserContext | None = None


def _get_local_context() -> UserContext:
    """Build a UserContext from env vars and SDK auth for local development."""
    global _local_context
    if _local_context is not None:
        return _local_context

    email = os.getenv("LAKEBASE_USER_EMAIL", "")
    project_id = os.getenv("LAKEBASE_PROJECT_ID", "")
    schema = os.getenv("LAKEBASE_SCHEMA", "")
    branch_id = os.getenv("LAKEBASE_BRANCH_ID", "production")

    if not email:
        try:
            from databricks.sdk import WorkspaceClient
            w = WorkspaceClient()
            email = w.current_user.me().user_name
        except Exception as e:
            logger.warning("Could not resolve local user email: %s", e)
            email = "local-dev"

    ctx = UserContext(
        email=email,
        project_id=project_id,
        schema=schema,
        branch_id=branch_id,
        _is_local=True,
    )
    _local_context = ctx
    logger.info("Local dev context: email=%s project=%s", ctx.email, ctx.project_id)
    return ctx


def get_current_user(request: Request) -> UserContext:
    """FastAPI dependency: extract user identity from Databricks Apps headers.

    Headers injected by the Databricks App proxy:
      - X-Forwarded-Email: user's email from the IdP
      - X-Forwarded-User: user identifier from the IdP
      - X-Forwarded-Access-Token: user's Databricks access token
    """
    email = (
        request.headers.get("x-forwarded-email")
        or request.headers.get("x-forwarded-user")
        or request.headers.get("x-forwarded-preferred-username")
        or ""
    )

    if not email:
        # Deployed Apps mode fails closed: never fall back to an ambient Service
        # Principal identity when the proxy has not supplied a caller. Local
        # development is enabled by selecting local mode (LAKEBASE_AUTH_MODE=local
        # or auto-detected off-platform), which uses the explicit local context.
        if get_auth_mode() == "apps":
            raise HTTPException(
                status_code=401,
                detail="Missing authenticated identity. This app must be accessed "
                "through the Databricks Apps proxy.",
            )
        return _get_local_context()

    return UserContext(
        email=email,
        branch_id=os.getenv("LAKEBASE_BRANCH_ID", "production"),
    )
