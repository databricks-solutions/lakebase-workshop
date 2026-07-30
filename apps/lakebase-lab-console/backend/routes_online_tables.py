"""Online Tables / Feature Store routes via Databricks SDK + REST API."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from databricks.sdk import WorkspaceClient

from .db import get_schema
from .security import log_and_sanitize
from .user_context import UserContext, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/online-tables", tags=["online-tables"])


def _get_client() -> WorkspaceClient:
    return WorkspaceClient()


def _get_user_identifier(user: UserContext) -> str:
    """Extract user identifier for filtering online stores."""
    local_part = user.email.split("@")[0]
    return local_part.replace(".", "_").replace("-", "_").lower()


def _safe_attr(obj, attr, default=None):
    return getattr(obj, attr, default) if obj else default


def _try_rest(w, method, path, body=None):
    """Call the Databricks REST API directly, bypassing SDK method gaps."""
    try:
        return w.api_client.do(method, path, body=body)
    except Exception as e:
        logger.warning("REST %s %s failed: %s", method, path, e)
        return None


# ── Online Stores (Database Instances) ──────────────────────────────────────

@router.get("/stores")
def list_online_stores(mine_only: bool = Query(True), user: UserContext = Depends(get_current_user)):
    """List database instances, optionally filtered to the current user."""
    result = []
    w = _get_client()
    user_id = _get_user_identifier(user)

    try:
        if hasattr(w, "database") and hasattr(w.database, "list_database_instances"):
            for inst in w.database.list_database_instances():
                info = {
                    "name": _safe_attr(inst, "name", ""),
                    "store_id": _safe_attr(inst, "name", ""),
                    "state": str(_safe_attr(inst, "state", "")),
                    "capacity": str(_safe_attr(inst, "capacity", "")),
                    "creator": _safe_attr(inst, "creator", ""),
                    "read_write_dns": _safe_attr(inst, "read_write_dns", ""),
                    "creation_time": str(_safe_attr(inst, "creation_time", "")),
                }
                result.append(info)
    except Exception as e:
        logger.warning("database.list_database_instances failed: %s", e)

    if not result:
        try:
            resp = _try_rest(w, "GET", "/api/2.0/database/database-instances")
            if resp and isinstance(resp, dict):
                for inst in resp.get("database_instances", []):
                    result.append({
                        "name": inst.get("name", ""),
                        "store_id": inst.get("name", ""),
                        "state": inst.get("state", ""),
                        "capacity": inst.get("capacity", ""),
                        "creator": inst.get("creator", ""),
                        "read_write_dns": inst.get("read_write_dns", ""),
                        "creation_time": inst.get("creation_time", ""),
                    })
        except Exception as e:
            logger.warning("REST list database instances failed: %s", e)

    if mine_only and user_id and result:
        user_parts = user_id.replace("_", "").replace("-", "").lower()
        filtered = [
            s for s in result
            if _matches_user(s, user_parts, user_id)
        ]
        result = filtered

    return result


def _matches_user(store: dict, user_normalized: str, user_id: str) -> bool:
    """Check if a database instance belongs to the current user."""
    creator = (store.get("creator") or "").lower()
    name = (store.get("name") or "").lower()
    creator_norm = creator.replace(".", "").replace("@", "").replace("-", "").replace("_", "")
    name_norm = name.replace(".", "").replace("-", "").replace("_", "")
    return user_normalized in creator_norm or user_normalized in name_norm


# ── Synced Tables (Reverse ETL) ────────────────────────────────────────────

@router.get("/synced-tables")
def list_synced_tables(user: UserContext = Depends(get_current_user)):
    """List synced tables by scanning UC tables and probing each for sync metadata.

    The SDK's list_synced_database_tables is officially unimplemented.
    We scan UC tables in the configured schema and use get_synced_database_table
    to check which are actual synced tables.
    """
    try:
        w = _get_client()
        schema = get_schema(user)
        catalog = "main"
        all_synced = []

        try:
            uc_tables = list(w.tables.list(catalog_name=catalog, schema_name=schema))
        except Exception as e:
            logger.warning("UC tables.list failed for %s.%s: %s", catalog, schema, e)
            return []

        for tbl in uc_tables:
            full_name = tbl.full_name if hasattr(tbl, "full_name") else f"{catalog}.{schema}.{tbl.name}"
            synced = _try_get_synced_table(w, full_name)
            if synced:
                all_synced.append(_extract_synced_info(synced, full_name))

        return all_synced

    except HTTPException:
        raise
    except Exception as e:
        if "not found" in str(e).lower() or "UNIMPLEMENTED" in str(e):
            return []
        raise HTTPException(500, f"Failed to list synced tables: {e}")


def _try_get_synced_table(w, full_name: str):
    """Probe whether a UC table is a synced table. Returns the object or None."""
    synced_name = f"synced_tables/{full_name}"
    try:
        if hasattr(w, "database") and hasattr(w.database, "get_synced_database_table"):
            return w.database.get_synced_database_table(name=synced_name)
    except Exception:
        pass
    try:
        if hasattr(w, "postgres") and hasattr(w.postgres, "get_synced_table"):
            return w.postgres.get_synced_table(name=synced_name)
    except Exception:
        pass
    try:
        resp = _try_rest(w, "GET", f"/api/2.0/database/synced-database-tables/{full_name}")
        if resp and isinstance(resp, dict) and resp.get("name"):
            return resp
    except Exception:
        pass
    return None


def _extract_synced_info(synced, full_name: str) -> dict:
    """Extract a serializable dict from a synced table object (SDK or dict)."""
    if isinstance(synced, dict):
        status = synced.get("status", {})
        spec = synced.get("spec", {})
        return {
            "name": synced.get("name", full_name),
            "table_id": full_name.split(".")[-1] if full_name else "",
            "branch_id": spec.get("branch", "").split("/")[-1] if spec.get("branch") else "production",
            "state": status.get("detailed_state") or status.get("current_state", ""),
            "pipeline_id": status.get("pipeline_id"),
            "source_table": spec.get("source_table_full_name", full_name),
            "primary_key_columns": spec.get("primary_key_columns", []),
            "scheduling_policy": str(spec.get("scheduling_policy", "")) if spec.get("scheduling_policy") else None,
            "message": status.get("message"),
        }

    status = _safe_attr(synced, "status")
    spec = _safe_attr(synced, "spec")
    branch_raw = _safe_attr(spec, "branch", "")
    return {
        "name": _safe_attr(synced, "name", full_name),
        "table_id": full_name.split(".")[-1] if full_name else "",
        "branch_id": branch_raw.split("/")[-1] if branch_raw else "production",
        "state": str(_safe_attr(status, "detailed_state", "") or _safe_attr(status, "current_state", "")),
        "pipeline_id": _safe_attr(status, "pipeline_id"),
        "source_table": _safe_attr(spec, "source_table_full_name", full_name),
        "primary_key_columns": list(_safe_attr(spec, "primary_key_columns", []) or []),
        "scheduling_policy": str(_safe_attr(spec, "scheduling_policy")) if _safe_attr(spec, "scheduling_policy") else None,
        "message": _safe_attr(status, "message"),
    }


@router.post("/synced-tables/{table_id}/trigger")
def trigger_synced_table(table_id: str, pipeline_id: str | None = None, user: UserContext = Depends(get_current_user)):
    """Trigger a sync pipeline update for a synced table in the caller's schema.

    The pipeline is resolved server-side from the caller's own synced table, so a
    client cannot start an arbitrary pipeline it happens to know the id of. Any
    client-supplied pipeline_id must match the resolved one.
    """
    try:
        w = _get_client()
        schema = get_schema(user)
        full_name = f"main.{schema}.{table_id}"

        synced = _try_get_synced_table(w, full_name)
        if not synced:
            raise HTTPException(404, "Synced table not found in your project")
        resolved_pipeline_id = _extract_synced_info(synced, full_name).get("pipeline_id")
        if not resolved_pipeline_id:
            raise HTTPException(404, "No sync pipeline found for this table")
        if pipeline_id and pipeline_id != resolved_pipeline_id:
            raise HTTPException(403, "pipeline_id does not match this synced table")

        w.pipelines.start_update(pipeline_id=resolved_pipeline_id)
        return {"message": f"Sync pipeline triggered for {table_id}"}
    except HTTPException:
        raise
    except Exception as e:
        log_and_sanitize(e, "Failed to trigger sync", context="/api/online-tables/trigger")
        raise HTTPException(500, "Failed to trigger sync")


# ── Feature Specs (UC Online Tables) ───────────────────────────────────────

@router.get("/feature-specs")
def list_feature_specs(user: UserContext = Depends(get_current_user)):
    """List online table specs by scanning UC tables and probing for OT metadata.

    The w.online_tables API has no list() method. We scan UC tables in the
    configured schema and check each ending in '_online' via w.online_tables.get().
    """
    w = _get_client()
    result = []
    schema = get_schema(user)
    catalog = "main"

    try:
        uc_tables = list(w.tables.list(catalog_name=catalog, schema_name=schema))
    except Exception as e:
        logger.warning("UC table scan for online tables failed: %s", e)
        return []

    for tbl in uc_tables:
        full_name = tbl.full_name if hasattr(tbl, "full_name") else f"{catalog}.{schema}.{tbl.name}"
        if not full_name.endswith("_online"):
            continue
        try:
            ot = w.online_tables.get(name=full_name)
            if ot:
                info = {
                    "name": _safe_attr(ot, "name", full_name),
                    "state": str(_safe_attr(_safe_attr(ot, "status"), "detailed_state", "")),
                    "triggered_update_status": str(
                        _safe_attr(_safe_attr(ot, "status"), "triggered_update_status", "")
                    ),
                    "source_table": _safe_attr(_safe_attr(ot, "spec"), "source_table_full_name"),
                    "primary_key_columns": list(
                        _safe_attr(_safe_attr(ot, "spec"), "primary_key_columns", []) or []
                    ),
                    "run_triggered": _safe_attr(_safe_attr(ot, "spec"), "run_triggered"),
                    "run_continuously": _safe_attr(_safe_attr(ot, "spec"), "run_continuously"),
                }
                result.append(info)
        except Exception:
            pass

    return result
