# app/schemas/group_schemas.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.schemas.member_schemas import MemberOut


class GroupBase(BaseModel):
    group_name: str
    lo_id: int
    region_id: Optional[int] = None
    branch_id: Optional[int] = None
    meeting_day: Optional[str] = None


class GroupCreate(GroupBase):
    pass


class GroupOut(GroupBase):
    group_id: int
    created_on: datetime  # ✅ now backed by the model column

    class Config:
        from_attributes = True  # for Pydantic ORM mode

class GroupSummaryOut(BaseModel):
    group: GroupOut
    members: List[MemberOut]
    total_members: int
    active_members: int
    inactive_members: int

    class Config:
        from_attributes = True