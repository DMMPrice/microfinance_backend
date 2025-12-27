# app/routers/groups_router.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.models.group_model import Group
from app.models.loan_officer_model import LoanOfficer
from app.utils.schemas import GroupCreate, GroupOut
from app.utils.auth import get_current_user
from app.schemas.group_schemas import GroupSummaryOut
from app.models.member_model import Member

router = APIRouter(prefix="/groups", tags=["Groups"])


# ===========================
# Helper: RBAC check for group
# ===========================
def _ensure_can_access_group(user: dict, group: Group):
    role = user["role"]

    if role == "regional_manager" and group.region_id != user["region_id"]:
        raise HTTPException(status_code=403, detail="Access denied for this region")

    if role == "branch_manager" and group.branch_id != user["branch_id"]:
        raise HTTPException(status_code=403, detail="Access denied for this branch")

    if role == "loan_officer" and group.lo_id != user["user_id"]:
        raise HTTPException(
            status_code=403, detail="Loan Officer can access only their groups"
        )

    # admin or any other higher role → allowed


# --------------------------------------
# CREATE GROUP
# --------------------------------------
@router.post("/", response_model=GroupOut)
def create_group(
        payload: GroupCreate,
        db: Session = Depends(get_db),
        user: dict = Depends(get_current_user),
):
    # Admin → allowed
    # RM → region match only
    # BM → branch match only
    # LO → can create only under themselves

    role = user["role"]

    if role == "loan_officer":
        if payload.lo_id != user["user_id"]:
            raise HTTPException(
                status_code=403,
                detail="Loan Officer can create groups only for themselves",
            )

    if role == "branch_manager":
        if payload.branch_id != user["branch_id"]:
            raise HTTPException(
                status_code=403, detail="Branch Manager limited to their branch"
            )

    if role == "regional_manager":
        if payload.region_id != user["region_id"]:
            raise HTTPException(
                status_code=403, detail="Regional Manager limited to their region"
            )

    # Admin bypasses everything

    new_group = Group(
        group_name=payload.group_name,
        lo_id=payload.lo_id,
        region_id=payload.region_id,
        branch_id=payload.branch_id,
        meeting_day=payload.meeting_day,
    )

    db.add(new_group)
    db.commit()
    db.refresh(new_group)

    return new_group


# --------------------------------------
# LIST GROUPS
# --------------------------------------
@router.get("/", response_model=list[GroupOut])
def list_groups(
        region_id: Optional[int] = Query(None),
        branch_id: Optional[int] = Query(None),
        lo_id: Optional[int] = Query(None),
        db: Session = Depends(get_db),
        user: dict = Depends(get_current_user),
):
    q = db.query(Group)
    role = user["role"]

    # ---------------------------
    # ROLE-BASED HARD FILTERS
    # ---------------------------

    if role == "regional_manager":
        q = q.filter(Group.region_id == user["region_id"])

    elif role == "branch_manager":
        q = q.filter(Group.branch_id == user["branch_id"])

    elif role == "loan_officer":
        q = q.filter(Group.lo_id == user["user_id"])

    # ---------------------------
    # OPTIONAL QUERY FILTERS
    # (Admin / higher roles only)
    # ---------------------------

    if region_id is not None:
        q = q.filter(Group.region_id == region_id)

    if branch_id is not None:
        q = q.filter(Group.branch_id == branch_id)

    if lo_id is not None:
        q = q.filter(Group.lo_id == lo_id)

    return q.all()


# --------------------------------------
# GROUP DETAILS
# --------------------------------------
@router.get("/{group_id}", response_model=GroupOut)
def get_group(
        group_id: int,
        db: Session = Depends(get_db),
        user: dict = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == group_id).first()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    _ensure_can_access_group(user, group)

    return group


# --------------------------------------
# DELETE GROUP
# --------------------------------------
@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
        group_id: int,
        db: Session = Depends(get_db),
        user: dict = Depends(get_current_user),
):
    """
    Delete a group with the same access rules used for reading:
    - Admin: can delete any group
    - Regional Manager: only groups in their region
    - Branch Manager: only groups in their branch
    - Loan Officer: only their own groups
    """
    group = db.query(Group).filter(Group.group_id == group_id).first()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    _ensure_can_access_group(user, group)

    db.delete(group)
    db.commit()
    # 204 → no response body
    return


# ===================================================
# ASSIGN / REASSIGN LOAN OFFICER TO MULTIPLE GROUPS
# ===================================================


class AssignLoanOfficerPayload(BaseModel):
    lo_id: int
    group_ids: List[int]


@router.post("/assign-lo", response_model=list[GroupOut])
def assign_loan_officer_to_groups(
        payload: AssignLoanOfficerPayload,
        db: Session = Depends(get_db),
        user: dict = Depends(get_current_user),
):
    """
    Assign a Loan Officer to one or multiple groups.

    - Admin: can assign any LO to any groups
    - Regional Manager: LO and groups must be in their region
    - Branch Manager: LO and groups must be in their branch
    - Loan Officer: not allowed to reassign (only Admin/RM/BM)
    """

    role = user["role"]

    if role == "loan_officer":
        raise HTTPException(
            status_code=403,
            detail="Loan Officers cannot reassign groups. Contact Branch/Regional/Admin.",
        )

    # 1️⃣ Check LO exists
    lo = db.query(LoanOfficer).filter(LoanOfficer.lo_id == payload.lo_id).first()
    if not lo:
        raise HTTPException(status_code=404, detail="Loan Officer not found")

    # 2️⃣ Fetch all groups
    groups = db.query(Group).filter(Group.group_id.in_(payload.group_ids)).all()

    if not groups:
        raise HTTPException(
            status_code=404,
            detail="No matching groups found for the provided group_ids",
        )

    # 3️⃣ Enforce region/branch constraints for RM / BM
    if role == "regional_manager":
        # LO must be in same region
        if lo.region_id != user["region_id"]:
            raise HTTPException(
                status_code=403,
                detail="Loan Officer is not in your region",
            )

        for g in groups:
            if g.region_id != user["region_id"]:
                raise HTTPException(
                    status_code=403,
                    detail=f"Group {g.group_id} is not in your region",
                )

    if role == "branch_manager":
        # LO must be in same branch
        if lo.branch_id != user["branch_id"]:
            raise HTTPException(
                status_code=403,
                detail="Loan Officer is not in your branch",
            )

        for g in groups:
            if g.branch_id != user["branch_id"]:
                raise HTTPException(
                    status_code=403,
                    detail=f"Group {g.group_id} is not in your branch",
                )

    # Admin bypasses everything

    # 4️⃣ Perform assignment
    for g in groups:
        g.lo_id = lo.lo_id

    db.commit()

    # Refresh to return updated objects
    for g in groups:
        db.refresh(g)

    return groups


# --------------------------------------
# GROUP SUMMARY (GROUP + MEMBERS + COUNTS)
# --------------------------------------
@router.get("/{group_id}/summary", response_model=GroupSummaryOut)
def get_group_summary(
        group_id: int,
        db: Session = Depends(get_db),
        user: dict = Depends(get_current_user),
):
    # 1️⃣ Fetch group
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # 2️⃣ RBAC check (reuse existing helper)
    _ensure_can_access_group(user, group)

    # 3️⃣ Fetch members of this group
    members = db.query(Member).filter(Member.group_id == group_id).all()

    total_members = len(members)
    active_members = sum(1 for m in members if m.is_active)
    inactive_members = total_members - active_members

    return {
        "group": group,
        "members": members,
        "total_members": total_members,
        "active_members": active_members,
        "inactive_members": inactive_members,
    }
