# app/utils/schemas.py

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


# =====================================
# AUTH + EMPLOYEE SCHEMAS
# =====================================

class UserCreate(BaseModel):
    # Auth
    username: str
    email: str
    password: str  # plain text as per your current requirement

    # Employee profile
    full_name: str
    phone: Optional[str] = None

    role_id: int
    region_id: Optional[int] = None
    branch_id: Optional[int] = None
    is_active: bool = True

    employee_code: Optional[str] = None
    date_joined: Optional[date] = None
    notes: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_role: Optional[str] = None
    user_id: int
    user_name: str


# =====================================
# GROUP SCHEMAS
#   (matches SQL: groups table)
# =====================================

class GroupBase(BaseModel):
    group_name: str
    lo_id: int
    region_id: Optional[int] = None
    branch_id: Optional[int] = None
    meeting_day: Optional[str] = None  # e.g., "Monday", "Tuesday"


class GroupCreate(GroupBase):
    """
    Used for POST /groups
    """
    pass


class GroupOut(GroupBase):
    """
    Used for response models in groups_router
    """
    group_id: int
    created_on: datetime

    class Config:
        from_attributes = True  # for ORM mode (SQLAlchemy objects)


# =====================================
# MEMBER SCHEMAS
#   (matches SQL: members table)
# =====================================

class MemberBase(BaseModel):
    full_name: str
    phone: Optional[str] = None
    address: Optional[str] = None

    group_id: Optional[int] = None
    lo_id: Optional[int] = None
    branch_id: Optional[int] = None
    region_id: Optional[int] = None

    is_active: bool = True


class MemberCreate(MemberBase):
    """
    Used for POST /members
    """
    pass


class MemberOut(MemberBase):
    """
    Used for response models in members_router
    """
    member_id: int
    created_on: datetime

    class Config:
        from_attributes = True  # for ORM mode
