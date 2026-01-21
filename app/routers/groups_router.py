# app/routers/groups_router.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.models.group_model import Group
from app.models.loan_officer_model import LoanOfficer
from app.utils.schemas import GroupCreate, GroupOut
from app.schemas.group_schemas import GroupSummaryOut
from app.models.member_model import Member

router = APIRouter(prefix="/groups", tags=["Groups"])


# --------------------------------------
# CREATE GROUP (NO RBAC / NO JWT)
# --------------------------------------
@router.post("/", response_model=GroupOut)
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
):
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
# LIST GROUPS (NO RBAC / NO JWT)
# --------------------------------------
@router.get("/", response_model=list[GroupOut])
def list_groups(
    region_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    lo_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),   # 👈 NEW
    db: Session = Depends(get_db),
):
    q = db.query(Group)

    # ---------------------------
    # OPTIONAL FILTERS
    # ---------------------------
    if region_id is not None:
        q = q.filter(Group.region_id == region_id)

    if branch_id is not None:
        q = q.filter(Group.branch_id == branch_id)

    if lo_id is not None:
        q = q.filter(Group.lo_id == lo_id)

    # ---------------------------
    # NEW: filter by user_id (employee_id)
    # ---------------------------
    if user_id is not None:
        lo = (
            db.query(LoanOfficer)
            .filter(LoanOfficer.employee_id == user_id)
            .first()
        )

        if not lo:
            return []  # no loan officer → no groups

        q = q.filter(Group.lo_id == lo.lo_id)

    return q.all()



# --------------------------------------
# GROUP DETAILS (NO RBAC / NO JWT)
# --------------------------------------
@router.get("/{group_id}", response_model=GroupOut)
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
):
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


# --------------------------------------
# DELETE GROUP (NO RBAC / NO JWT)
# --------------------------------------
@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
):
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    db.delete(group)
    db.commit()
    return


# ===================================================
# ASSIGN / REASSIGN LOAN OFFICER TO MULTIPLE GROUPS
# (NO RBAC / NO JWT)
# ===================================================
class AssignLoanOfficerPayload(BaseModel):
    lo_id: int
    group_ids: List[int]


@router.post("/assign-lo", response_model=list[GroupOut])
def assign_loan_officer_to_groups(
    payload: AssignLoanOfficerPayload,
    db: Session = Depends(get_db),
):
    # 1) Check LO exists
    lo = db.query(LoanOfficer).filter(LoanOfficer.lo_id == payload.lo_id).first()
    if not lo:
        raise HTTPException(status_code=404, detail="Loan Officer not found")

    # 2) Fetch all groups
    groups = db.query(Group).filter(Group.group_id.in_(payload.group_ids)).all()
    if not groups:
        raise HTTPException(
            status_code=404,
            detail="No matching groups found for the provided group_ids",
        )

    # 3) Perform assignment
    for g in groups:
        g.lo_id = lo.lo_id

    db.commit()

    for g in groups:
        db.refresh(g)

    return groups


# --------------------------------------
# GROUP SUMMARY (NO RBAC / NO JWT)
# --------------------------------------
@router.get("/{group_id}/summary", response_model=GroupSummaryOut)
def get_group_summary(
    group_id: int,
    db: Session = Depends(get_db),
):
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

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
