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


def _branch_error(e: Exception) -> HTTPException:
    """Map SDK failures to an actionable message.

    The raw 'Can Manage' error is a wall of SDK config detail that buries the one
    thing a participant can act on: their project ACL is missing the app's SP.
    """
    msg = str(e)
    if "Can Manage" in msg or "not authorized" in msg:
        return HTTPException(
            403,
            "The Lab Console's service principal doesn't have 'Can Manage' on your "
            "Lakebase project, which is required to manage branches. Re-run Step 6a "
            "of the 00_Setup_Lakebase_Project notebook to grant it.",
        )
    return HTTPException(400, msg)


class CreateBranchRequest(BaseModel):
    branch_id: str = Field(..., pattern=r"^lab-[a-z0-9-]{1,50}$")
    source_branch: str = "production"
    # None => persistent branch (no auto-delete), matching the lab's snapshot
    # pattern. A value creates a temporary branch that auto-deletes after N hours.
    ttl_hours: int | None = Field(default=None, ge=1, le=720)


def _branch_field(b, attr: str) -> str | None:
    """Read a status field off an SDK Branch, returning None (not the string
    'None') when it is unset, so the frontend can classify cleanly."""
    if not b.status:
        return None
    val = getattr(b.status, attr, None)
    return str(val) if val else None


def _source_branch(b) -> str | None:
    """Extract the short source branch name from a Branch's spec, if present."""
    spec = getattr(b, "spec", None)
    src = getattr(spec, "source_branch", None) if spec else None
    return src.split("/")[-1] if src else None


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
            state=_branch_field(b, "current_state"),
            logical_size_bytes=getattr(b.status, "logical_size_bytes", None),
            expire_time=_branch_field(b, "expire_time"),
            source_branch=_source_branch(b),
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
        state=_branch_field(b, "current_state"),
        logical_size_bytes=getattr(b.status, "logical_size_bytes", None),
        expire_time=_branch_field(b, "expire_time"),
        source_branch=_source_branch(b),
    )


@router.post("", response_model=BranchInfo)
def create_branch(req: CreateBranchRequest, user: UserContext = Depends(get_current_user)):
    """Create a new branch (prefixed with 'lab-')."""
    w = _get_client()
    project_id = get_project_id(user)
    source = f"projects/{project_id}/branches/{req.source_branch}"

    # Only set a TTL when the caller asked for a temporary branch. A snapshot
    # (ttl_hours=None) is created persistent, matching the lab's no_expiry pattern.
    spec = BranchSpec(source_branch=source)
    if req.ttl_hours is not None:
        spec.ttl = Duration(seconds=req.ttl_hours * 3600)

    try:
        result = w.postgres.create_branch(
            parent=f"projects/{project_id}",
            branch=Branch(spec=spec),
            branch_id=req.branch_id,
        ).wait()
    except Exception as e:
        raise _branch_error(e)

    bid = result.name.split("/")[-1]
    return BranchInfo(
        name=result.name,
        branch_id=bid,
        state=_branch_field(result, "current_state"),
        expire_time=_branch_field(result, "expire_time"),
        source_branch=_source_branch(result),
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
        raise _branch_error(e)

    return {"status": "deleted", "branch_id": branch_id}
