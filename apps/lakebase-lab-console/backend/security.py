"""Shared security helpers for the Lakebase Lab Console.

This module centralizes the small, reusable guards that the workshop app relies
on to keep the shared Service Principal boundary safe:

  - auth mode detection (deployed Databricks Apps vs local development),
  - identifier validation for schemas, branch/endpoint ids, and PostgREST
    resource names that get interpolated into SQL or URLs,
  - bounded numeric limits for list endpoints,
  - safe static-file resolution (path-traversal containment),
  - sanitized, request-id-tagged error responses,
  - a redirect-free, size-capped outbound HTTP helper for the Data API proxy.

None of these change workshop behavior; they make the existing flows fail
closed instead of fail open.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


# --- Auth mode -------------------------------------------------------------

def get_auth_mode() -> str:
    """Return the identity trust mode: 'apps' (deployed) or 'local'.

    Deployed Databricks Apps inject identity via the reverse proxy, so the app
    must require a forwarded identity and never fall back to an ambient
    Service Principal identity. Local development has no proxy, so it uses an
    explicit local context.

    Resolution order:
      1. LAKEBASE_AUTH_MODE ("apps" | "local"), if set explicitly.
      2. Auto-detect: the Databricks Apps runtime sets DATABRICKS_APP_NAME.
      3. Default to "local".
    """
    mode = os.getenv("LAKEBASE_AUTH_MODE", "").strip().lower()
    if mode in ("apps", "local"):
        return mode
    if os.getenv("DATABRICKS_APP_NAME"):
        return "apps"
    return "local"


# --- Identifier validation -------------------------------------------------

# Postgres schema derived from a sanitized email (see user_context._sanitize_email).
_SCHEMA_RE = re.compile(r"^[a-z0-9_]{1,63}$")
# Lakebase resource ids: RFC 1123-ish, lowercase alnum + hyphen.
_RESOURCE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
# PostgREST resource (table/view) name.
_PG_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def is_valid_schema(schema: str) -> bool:
    return bool(schema) and bool(_SCHEMA_RE.match(schema))


def assert_valid_schema(schema: str) -> str:
    """Return the schema if it is a safe identifier, else raise ValueError.

    Used before any place a schema is interpolated into SQL or a URL path.
    """
    if not is_valid_schema(schema):
        raise ValueError(f"Unsafe schema identifier: {schema!r}")
    return schema


def is_valid_resource_id(value: str) -> bool:
    """Validate a Lakebase branch/endpoint id used in SDK resource names."""
    return bool(value) and bool(_RESOURCE_ID_RE.match(value))


def is_valid_pg_ident(value: str) -> bool:
    """Validate a PostgREST resource (table/view) name."""
    return bool(value) and bool(_PG_IDENT_RE.match(value))


# --- Bounded limits --------------------------------------------------------

def clamp_limit(value: int | None, default: int = 50, maximum: int = 500) -> int:
    """Clamp a user-supplied row limit into [1, maximum]."""
    try:
        n = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    if n < 1:
        return 1
    if n > maximum:
        return maximum
    return n


# --- Static file containment ----------------------------------------------

def resolve_static_file(static_dir: Path, full_path: str) -> Path | None:
    """Resolve an SPA static path, guarding against directory traversal.

    Returns the resolved file Path only when it stays within static_dir and is
    an existing regular file; otherwise None (caller should fall back to
    index.html).
    """
    if not full_path:
        return None
    base = static_dir.resolve()
    try:
        candidate = (base / full_path).resolve()
    except (OSError, ValueError):
        return None
    if base != candidate and base not in candidate.parents:
        return None
    if candidate.is_file():
        return candidate
    return None


# --- Sanitized errors ------------------------------------------------------

def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def log_and_sanitize(exc: Exception, message: str, *, context: str = "") -> dict:
    """Log the full exception server-side; return a safe client payload.

    The client sees a stable message and a request id (for support), never the
    raw driver/SDK exception text (which can leak hosts, SQL, or role names).
    """
    request_id = new_request_id()
    logger.error("[%s] %s (context=%s): %s", request_id, message, context or "-", exc)
    return {"error": message, "request_id": request_id}


# --- Outbound HTTP (Data API proxy) ---------------------------------------

class OutboundHTTPError(Exception):
    """Raised when a guarded outbound request fails or violates a constraint."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


# 5 MB cap on proxied Data API responses (workshop tables are tiny).
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


def outbound_request(
    url: str,
    *,
    method: str,
    headers: dict,
    data: bytes | None = None,
    timeout: int = 30,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[int, str]:
    """Perform an HTTPS request that never follows redirects and caps the body.

    Redirect following is disabled so a bearer token cannot be leaked to a
    redirect target off the intended host. The response body is truncated at
    max_bytes to bound memory use.
    """
    import urllib.error
    import urllib.request

    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise OutboundHTTPError("Outbound requests must use https://", status=400)

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):  # noqa: D401
            return None  # never auto-follow

    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read(max_bytes + 1)
            return resp.status, _decode_capped(body, max_bytes)
    except urllib.error.HTTPError as e:
        # Redirects surface here (handler returns None). Do not follow them.
        if e.code in (301, 302, 303, 307, 308):
            raise OutboundHTTPError(
                "The Data API returned a redirect, which is not followed for "
                "security reasons. Verify the API URL from your project's API tab.",
                status=502,
            )
        body = e.read(max_bytes + 1) if hasattr(e, "read") else b""
        return e.code, _decode_capped(body, max_bytes)
    except OutboundHTTPError:
        raise
    except Exception as e:  # noqa: BLE001 - normalize network errors
        raise OutboundHTTPError(f"Request to Data API failed: {e}") from e


def _decode_capped(body: bytes, max_bytes: int) -> str:
    truncated = len(body) > max_bytes
    text = body[:max_bytes].decode(errors="replace")
    if truncated:
        text += "\n\n[response truncated at 5 MB by the Lab Console proxy]"
    return text
