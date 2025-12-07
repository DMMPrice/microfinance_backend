from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.models.group_model import Group
from app.models.member_model import Member
from app.schemas.member_schemas import MemberCreate, MemberOut, MemberUpdate
from app.utils.auth import get_current_user

router = APIRouter(prefix="/members", tags=["Members"])


# --------------------------------------
# CREATE MEMBER
# --------------------------------------
@router.post("/", response_model=MemberOut)
def create_member(
    payload: MemberCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if payload.group_id is None:
        raise HTTPException(400, "group_id is required")

    group = db.query(Group).filter(Group.group_id == payload.group_id).first()
    if not group:
        raise HTTPException(404, "Group not found")

    # Access control identical to groups
    if user["role"] == "regional_manager" and group.region_id != user["region_id"]:
        raise HTTPException(403, "Access denied")

    if user["role"] == "branch_manager" and group.branch_id != user["branch_id"]:
        raise HTTPException(403, "Access denied")

    if user["role"] == "loan_officer" and group.lo_id != user["user_id"]:
        raise HTTPException(403, "Access denied")

    new_member = Member(
        full_name=payload.full_name,
        father_or_husband_name=payload.father_or_husband_name,
        mother_name=payload.mother_name,
        photo_b64=payload.photo_b64,
        dob=payload.dob,
        phone=payload.phone,
        aadhar_no=payload.aadhar_no,
        pan_no=payload.pan_no,
        voter_id=payload.voter_id,
        present_address=payload.present_address,
        permanent_address=payload.permanent_address,
        pincode=payload.pincode,
        other_details=payload.other_details,
        is_active=payload.is_active,
        group_id=payload.group_id,
        lo_id=group.lo_id,
        branch_id=group.branch_id,
        region_id=group.region_id,
    )

    db.add(new_member)
    db.commit()
    db.refresh(new_member)

    return new_member


# --------------------------------------
# LIST MEMBERS
# --------------------------------------
@router.get("/", response_model=list[MemberOut])
def list_members(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    q = db.query(Member).filter(Member.is_active == True)

    if user["role"] == "regional_manager":
        q = q.filter(Member.region_id == user["region_id"])

    if user["role"] == "branch_manager":
        q = q.filter(Member.branch_id == user["branch_id"])

    if user["role"] == "loan_officer":
        q = q.filter(Member.lo_id == user["user_id"])

    return q.all()


# --------------------------------------
# MEMBER DETAILS
# --------------------------------------
@router.get("/{member_id}", response_model=MemberOut)
def get_member(
    member_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    member = db.query(Member).filter(Member.member_id == member_id).first()

    if not member:
        raise HTTPException(404, "Member not found")

    # Role-based access
    if user["role"] == "regional_manager" and member.region_id != user["region_id"]:
        raise HTTPException(403, "Access denied")

    if user["role"] == "branch_manager" and member.branch_id != user["branch_id"]:
        raise HTTPException(403, "Access denied")

    if user["role"] == "loan_officer" and member.lo_id != user["user_id"]:
        raise HTTPException(403, "Access denied")

    return member


# --------------------------------------
# UPDATE MEMBER (PARTIAL)
# --------------------------------------
@router.put("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: int,
    payload: MemberUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    member = db.query(Member).filter(Member.member_id == member_id).first()

    if not member:
        raise HTTPException(404, "Member not found")

    # Check access based on existing member mapping
    if user["role"] == "regional_manager" and member.region_id != user["region_id"]:
        raise HTTPException(403, "Access denied")

    if user["role"] == "branch_manager" and member.branch_id != user["branch_id"]:
        raise HTTPException(403, "Access denied")

    if user["role"] == "loan_officer" and member.lo_id != user["user_id"]:
        raise HTTPException(403, "Access denied")

    data = payload.model_dump(exclude_unset=True)

    # If group_id is being changed, update LO / branch / region from that group
    if "group_id" in data and data["group_id"] is not None:
        new_group = db.query(Group).filter(Group.group_id == data["group_id"]).first()
        if not new_group:
            raise HTTPException(404, "New group not found")

        # Access control for new group as well
        if (
            user["role"] == "regional_manager"
            and new_group.region_id != user["region_id"]
        ):
            raise HTTPException(403, "Access denied for new group")

        if (
            user["role"] == "branch_manager"
            and new_group.branch_id != user["branch_id"]
        ):
            raise HTTPException(403, "Access denied for new group")

        if user["role"] == "loan_officer" and new_group.lo_id != user["user_id"]:
            raise HTTPException(403, "Access denied for new group")

        member.group_id = new_group.group_id
        member.lo_id = new_group.lo_id
        member.branch_id = new_group.branch_id
        member.region_id = new_group.region_id

        # avoid reusing group-related fields from payload
        data.pop("group_id", None)

    # Update simple scalar fields
    # (we don't allow direct override of lo_id/branch_id/region_id from payload)
    for field, value in data.items():
        if field in {"lo_id", "branch_id", "region_id"}:
            continue
        setattr(member, field, value)

    db.commit()
    db.refresh(member)

    return member


# --------------------------------------
# DELETE / DEACTIVATE MEMBER
# --------------------------------------
@router.delete("/{member_id}")
def delete_member(
    member_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    member = db.query(Member).filter(Member.member_id == member_id).first()

    if not member:
        raise HTTPException(404, "Member not found")

    # Same access control
    if user["role"] == "regional_manager" and member.region_id != user["region_id"]:
        raise HTTPException(403, "Access denied")

    if user["role"] == "branch_manager" and member.branch_id != user["branch_id"]:
        raise HTTPException(403, "Access denied")

    if user["role"] == "loan_officer" and member.lo_id != user["user_id"]:
        raise HTTPException(403, "Access denied")

    # Soft delete
    member.is_active = False
    db.commit()

    return {"detail": "Member deactivated successfully"}
