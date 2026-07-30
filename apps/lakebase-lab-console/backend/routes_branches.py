"""Branch management API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Branch, BranchSpec, Duration

from .db import get_project_id
from .security import is_valid_resource_id
from .user_context import UserContext, get_current_user

router = APIRouter(prefix="/api/branches", tags=["branches"])


def _get_client() -> WorkspaceClient:
    return WorkspaceClient()


class CreateBranchRequest(BaseModel):
    branch_id: str = Field(..., pattern=r"^lab-[a-z0-9-]{1,50}$")
    source_branch: str = "production"
    ttl_hours: int = Field(default=24, ge=1, le=720)


class BranchInfo(BaseModel):
    name: str
    branch_id: str
    is_default: bool = False
    is_protected: bool = False
    state: str | None = None
    logical_size_bytes: int | None = None
    expire_time: str | None = None
    source_branch: str | None = None


@router.get("", response_model=list[BranchInfo])
def list_branches(user: UserContext = Depends(get_current_user)):
    """List all branches in the project."""
    w = _get_client()
    project_id = get_project_id(user)
    branches = list(w.postgres.list_branches(parent=f"projects/{project_id}"))

    result = []
    for b in branches:
        bid = b.name.split("/")[-1] if b.name else ""
        result.append(BranchInfo(
            name=b.name,
            branch_id=bid,
            is_default=getattr(b.status, "default", False) or False,
            is_protected=getattr(b.status, "is_protected", False) or False,
            state=str(getattr(b.status, "current_state", "")) if b.status else None,
            logical_size_bytes=getattr(b.status, "logical_size_bytes", None),
            expire_time=str(getattr(b.status, "expire_time", "")) if b.status else None,
        ))
    return result


@router.get("/{branch_id}", response_model=BranchInfo)
def get_branch(branch_id: str, user: UserContext = Depends(get_current_user)):
    """Get details of a specific branch."""
    if not is_valid_resource_id(branch_id):
        raise HTTPException(400, "Invalid branch id")
    w = _get_client()
    project_id = get_project_id(user)
    b = w.postgres.get_branch(name=f"projects/{project_id}/branches/{branch_id}")
    bid = b.name.split("/")[-1]
    return BranchInfo(
        name=b.name,
        branch_id=bid,
        is_default=getattr(b.status, "default", False) or False,
        is_protected=getattr(b.status, "is_protected", False) or False,
        state=str(getattr(b.status, "current_state", "")) if b.status else None,
        logical_size_bytes=getattr(b.status, "logical_size_bytes", None),
        expire_time=str(getattr(b.status, "expire_time", "")) if b.status else None,
    )


@router.post("", response_model=BranchInfo)
def create_branch(req: CreateBranchRequest, user: UserContext = Depends(get_current_user)):
    """Create a new branch (prefixed with 'lab-')."""
    w = _get_client()
    project_id = get_project_id(user)
    source = f"projects/{project_id}/branches/{req.source_branch}"

    ttl_seconds = req.ttl_hours * 3600

    try:
        result = w.postgres.create_branch(
            parent=f"projects/{project_id}",
            branch=Branch(
                spec=BranchSpec(
                    source_branch=source,
                    ttl=Duration(seconds=ttl_seconds),
                )
            ),
            branch_id=req.branch_id,
        ).wait()
    except Exception as e:
        raise HTTPException(400, str(e))

    bid = result.name.split("/")[-1]
    return BranchInfo(
        name=result.name,
        branch_id=bid,
        state=str(getattr(result.status, "current_state", "")) if result.status else None,
        expire_time=str(getattr(result.status, "expire_time", "")) if result.status else None,
    )


@router.delete("/{branch_id}")
def delete_branch(branch_id: str, user: UserContext = Depends(get_current_user)):
    """Delete a branch. Only lab- prefixed branches can be deleted via the UI."""
    if not is_valid_resource_id(branch_id):
        raise HTTPException(400, "Invalid branch id")
    if not branch_id.startswith("lab-"):
        raise HTTPException(400, "Only lab- prefixed branches can be deleted from the console")

    w = _get_client()
    project_id = get_project_id(user)

    try:
        w.postgres.delete_branch(
            name=f"projects/{project_id}/branches/{branch_id}"
        ).wait()
    except Exception as e:
        raise HTTPException(400, str(e))

    return {"status": "deleted", "branch_id": branch_id}
