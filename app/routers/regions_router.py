# app/routes/regions_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.models.regions_model import Region
from app.schemas import RegionCreate, RegionOut, RegionUpdate

router = APIRouter(prefix="/regions", tags=["Regions"])


# CREATE
@router.post("/", response_model=RegionOut)
def create_region(payload: RegionCreate, db: Session = Depends(get_db)):
    exists = db.query(Region).filter(Region.region_name == payload.region_name).first()
    if exists:
        raise HTTPException(400, "Region already exists")

    region = Region(region_name=payload.region_name)
    db.add(region)
    db.commit()
    db.refresh(region)
    return region


# READ ALL
@router.get("/", response_model=list[RegionOut])
def list_regions(db: Session = Depends(get_db)):
    return db.query(Region).all()


# READ ONE
@router.get("/{region_id}", response_model=RegionOut)
def get_region(region_id: int, db: Session = Depends(get_db)):
    region = db.query(Region).filter(Region.region_id == region_id).first()
    if not region:
        raise HTTPException(404, "Region not found")

    return region


# UPDATE
@router.put("/{region_id}", response_model=RegionOut)
def update_region(
        region_id: int, payload: RegionUpdate, db: Session = Depends(get_db)
):
    region = db.query(Region).filter(Region.region_id == region_id).first()
    if not region:
        raise HTTPException(404, "Region not found")

    if payload.region_name is not None:
        # prevent duplicate names
        dup = (
            db.query(Region)
            .filter(
                Region.region_name == payload.region_name,
                Region.region_id != region_id,
            )
            .first()
        )
        if dup:
            raise HTTPException(400, "Region name already in use")

        region.region_name = payload.region_name

    db.commit()
    db.refresh(region)
    return region


# DELETE
@router.delete("/{region_id}")
def delete_region(region_id: int, db: Session = Depends(get_db)):
    region = db.query(Region).filter(Region.region_id == region_id).first()
    if not region:
        raise HTTPException(404, "Region not found")

    # Optional protection: don't delete if branches exist
    if region.branches:
        raise HTTPException(400, "Cannot delete region with existing branches")

    db.delete(region)
    db.commit()
    return {"message": "Region deleted successfully"}
