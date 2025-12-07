# app/schemas/member_schemas.py
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class MemberBase(BaseModel):
    full_name: str
    father_or_husband_name: Optional[str] = None
    mother_name: Optional[str] = None

    photo_b64: Optional[str] = None

    dob: Optional[date] = None
    phone: Optional[str] = None
    aadhar_no: Optional[str] = None
    pan_no: Optional[str] = None
    voter_id: Optional[str] = None

    present_address: Optional[str] = None
    permanent_address: Optional[str] = None
    pincode: Optional[str] = None

    group_id: Optional[int] = None
    lo_id: Optional[int] = None
    branch_id: Optional[int] = None
    region_id: Optional[int] = None

    other_details: Optional[str] = None
    is_active: bool = True


class MemberCreate(MemberBase):
    """Used for creating a new member."""

    pass


class MemberUpdate(BaseModel):
    # (same as you already have)
    full_name: Optional[str] = None
    father_or_husband_name: Optional[str] = None
    mother_name: Optional[str] = None

    photo_b64: Optional[str] = None

    dob: Optional[date] = None
    phone: Optional[str] = None
    aadhar_no: Optional[str] = None
    pan_no: Optional[str] = None
    voter_id: Optional[str] = None

    present_address: Optional[str] = None
    permanent_address: Optional[str] = None
    pincode: Optional[str] = None

    group_id: Optional[int] = None
    other_details: Optional[str] = None
    is_active: Optional[bool] = None


class MemberOut(MemberBase):
    member_id: int
    created_on: Optional[datetime] = None  # ✅ allow None safely

    class Config:
        from_attributes = True
