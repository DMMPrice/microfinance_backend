# app/schemas/branch_schemas.py

from pydantic import BaseModel
from typing import Optional


class BranchBase(BaseModel):
    branch_name: str
    region_id: int


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseModel):
    branch_name: Optional[str] = None
    region_id: Optional[int] = None


class BranchOut(BranchBase):
    branch_id: int

    class Config:
        from_attributes = True
