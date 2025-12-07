# app/routes/branches_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.models.branches_model import Branch
from app.models.regions_model import Region
from app.schemas import BranchCreate, BranchOut, BranchUpdate

router = APIRouter(prefix="/branches", tags=["Branches"])


# CREATE
@router.post("/", response_model=BranchOut)
def create_branch(payload: BranchCreate, db: Session = Depends(get_db)):
    # Ensure region exists
    region = db.query(Region).filter(Region.region_id == payload.region_id).first()
    if not region:
        raise HTTPException(400, "Invalid region_id")

    # Ensure unique name
    exists = db.query(Branch).filter(Branch.branch_name == payload.branch_name).first()
    if exists:
        raise HTTPException(400, "Branch name already exists")

    branch = Branch(
        branch_name=payload.branch_name,
        region_id=payload.region_id,
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


# READ ALL
@router.get("/", response_model=list[BranchOut])
def list_branches(
        region_id: int | None = None,
        db: Session = Depends(get_db),
):
    q = db.query(Branch)
    if region_id is not None:
        q = q.filter(Branch.region_id == region_id)
    return q.all()


# READ ONE
@router.get("/{branch_id}", response_model=BranchOut)
def get_branch(branch_id: int, db: Session = Depends(get_db)):
    branch = db.query(Branch).filter(Branch.branch_id == branch_id).first()
    if not branch:
        raise HTTPException(404, "Branch not found")

    return branch


# UPDATE
@router.put("/{branch_id}", response_model=BranchOut)
def update_branch(
        branch_id: int,
        payload: BranchUpdate,
        db: Session = Depends(get_db),
):
    branch = db.query(Branch).filter(Branch.branch_id == branch_id).first()
    if not branch:
        raise HTTPException(404, "Branch not found")

    if payload.branch_name is not None:
        # unique name check
        dup = (
            db.query(Branch)
            .filter(
                Branch.branch_name == payload.branch_name,
                Branch.branch_id != branch_id,
            )
            .first()
        )
        if dup:
            raise HTTPException(400, "Branch name already in use")
        branch.branch_name = payload.branch_name

    if payload.region_id is not None:
        region = db.query(Region).filter(Region.region_id == payload.region_id).first()
        if not region:
            raise HTTPException(400, "Invalid region_id")
        branch.region_id = payload.region_id

    db.commit()
    db.refresh(branch)
    return branch


# DELETE
@router.delete("/{branch_id}")
def delete_branch(branch_id: int, db: Session = Depends(get_db)):
    branch = db.query(Branch).filter(Branch.branch_id == branch_id).first()
    if not branch:
        raise HTTPException(404, "Branch not found")

    # Optional: prevent delete if employees / groups exist, later
    db.delete(branch)
    db.commit()
    return {"message": "Branch deleted successfully"}
