"""Compute / autoscaling management routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, EndpointType, FieldMask

from .db import get_db_metrics, get_project_id
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/compute", tags=["compute"])


def _get_client() -> WorkspaceClient:
    return WorkspaceClient()


class EndpointInfo(BaseModel):
    name: str
    branch_id: str
    endpoint_type: str | None = None
    state: str | None = None
    host: str | None = None
    min_cu: float | None = None
    max_cu: float | None = None
    scale_to_zero_seconds: int | None = None
    db_active_connections: int | None = None
    db_cache_hit_ratio: float | None = None
    db_total_transactions: int | None = None


class UpdateComputeRequest(BaseModel):
    min_cu: float = Field(..., ge=0.5, le=64)
    max_cu: float = Field(..., ge=0.5, le=64)


@router.get("/{branch_id}", response_model=list[EndpointInfo])
def list_endpoints(branch_id: str, user: UserContext = Depends(get_current_user)):
    """List compute endpoints for a branch, enriched with live DB metrics."""
    w = _get_client()
    pid = get_project_id(user)
    endpoints = list(
        w.postgres.list_endpoints(
            parent=f"projects/{pid}/branches/{branch_id}"
        )
    )

    db_metrics = get_db_metrics(user, branch_id)

    result = []
    for ep in endpoints:
        detail = w.postgres.get_endpoint(name=ep.name)
        s = detail.status
        result.append(EndpointInfo(
            name=detail.name,
            branch_id=branch_id,
            endpoint_type=str(getattr(s, "endpoint_type", "")) if s else None,
            state=str(getattr(s, "current_state", "")) if s else None,
            host=getattr(s.hosts, "host", None) if s and s.hosts else None,
            min_cu=getattr(s, "autoscaling_limit_min_cu", None) if s else None,
            max_cu=getattr(s, "autoscaling_limit_max_cu", None) if s else None,
            db_active_connections=db_metrics.get("active_connections"),
            db_cache_hit_ratio=db_metrics.get("cache_hit_ratio"),
            db_total_transactions=db_metrics.get("total_transactions"),
        ))
    return result


@router.patch("/{branch_id}/{endpoint_id}", response_model=EndpointInfo)
def update_compute(branch_id: str, endpoint_id: str, req: UpdateComputeRequest, user: UserContext = Depends(get_current_user)):
    """Update autoscaling limits for a compute endpoint."""
    if req.max_cu - req.min_cu > 16:
        raise HTTPException(
            400,
            f"Autoscaling range too wide: {req.max_cu - req.min_cu} CU "
            f"(max spread is 16 CU)"
        )

    w = _get_client()
    pid = get_project_id(user)
    ep_name = f"projects/{pid}/branches/{branch_id}/endpoints/{endpoint_id}"

    try:
        w.postgres.update_endpoint(
            name=ep_name,
            endpoint=Endpoint(
                name=ep_name,
                spec=EndpointSpec(
                    endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
                    autoscaling_limit_min_cu=req.min_cu,
                    autoscaling_limit_max_cu=req.max_cu,
                ),
            ),
            update_mask=FieldMask(
                field_mask=[
                    "spec.autoscaling_limit_min_cu",
                    "spec.autoscaling_limit_max_cu",
                ]
            ),
        ).wait()
    except Exception as e:
        raise HTTPException(400, str(e))

    detail = w.postgres.get_endpoint(name=ep_name)
    s = detail.status
    return EndpointInfo(
        name=detail.name,
        branch_id=branch_id,
        endpoint_type=str(getattr(s, "endpoint_type", "")) if s else None,
        state=str(getattr(s, "current_state", "")) if s else None,
        host=getattr(s.hosts, "host", None) if s and s.hosts else None,
        min_cu=getattr(s, "autoscaling_limit_min_cu", None) if s else None,
        max_cu=getattr(s, "autoscaling_limit_max_cu", None) if s else None,
    )
