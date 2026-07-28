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
    read_only_host: str | None = None
    min_cu: float | None = None
    max_cu: float | None = None
    scale_to_zero_seconds: int | None = None
    db_active_connections: int | None = None
    db_cache_hit_ratio: float | None = None
    db_total_transactions: int | None = None


class TopologyInfo(BaseModel):
    branch_id: str
    endpoint_id: str | None = None
    endpoint_type: str | None = None
    is_primary: bool = False
    state: str | None = None
    host: str | None = None
    read_only_host: str | None = None
    min_cu: float | None = None
    max_cu: float | None = None


class TopologyResponse(BaseModel):
    branch_id: str
    primary_count: int = 0
    read_replica_count: int = 0
    has_read_routing: bool = False
    endpoints: list[TopologyInfo] = []


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


@router.get("/topology/{branch_id}", response_model=TopologyResponse)
def get_topology(branch_id: str, user: UserContext = Depends(get_current_user)):
    """Inspect the compute topology for a branch: primary + read replicas.

    High availability and read replicas are configured from the Lakebase UI
    (no SDK enablement path), so this endpoint is read-only inspection: it lists
    every endpoint, classifies primary vs read-replica, and reports whether the
    primary exposes a separate read-only host for read routing.
    """
    w = _get_client()
    pid = get_project_id(user)
    endpoints = list(
        w.postgres.list_endpoints(parent=f"projects/{pid}/branches/{branch_id}")
    )

    rows: list[TopologyInfo] = []
    primary_count = 0
    replica_count = 0
    has_read_routing = False
    for ep in endpoints:
        detail = w.postgres.get_endpoint(name=ep.name)
        s = detail.status
        ep_type = str(getattr(s, "endpoint_type", "")) if s else ""
        is_primary = "READ_WRITE" in ep_type
        ro_host = getattr(s.hosts, "read_only_host", None) if s and s.hosts else None
        if is_primary:
            primary_count += 1
        elif "READ_ONLY" in ep_type:
            replica_count += 1
        if ro_host:
            has_read_routing = True
        rows.append(TopologyInfo(
            branch_id=branch_id,
            endpoint_id=getattr(s, "endpoint_id", None) if s else (detail.name.split("/")[-1] if detail.name else None),
            endpoint_type=ep_type or None,
            is_primary=is_primary,
            state=str(getattr(s, "current_state", "")) if s else None,
            host=getattr(s.hosts, "host", None) if s and s.hosts else None,
            read_only_host=ro_host,
            min_cu=getattr(s, "autoscaling_limit_min_cu", None) if s else None,
            max_cu=getattr(s, "autoscaling_limit_max_cu", None) if s else None,
        ))

    return TopologyResponse(
        branch_id=branch_id,
        primary_count=primary_count,
        read_replica_count=replica_count,
        has_read_routing=has_read_routing,
        endpoints=rows,
    )


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
