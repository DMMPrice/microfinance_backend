# app/schemas/loan_officer_schemas.py

from pydantic import BaseModel
from typing import List
from app.schemas.group_schemas import GroupOut  # or `from app.schemas import GroupOut`


class LoanOfficerBase(BaseModel):
    employee_id: int


class LoanOfficerCreate(LoanOfficerBase):
    """Data needed to register an existing employee as a Loan Officer."""

    pass


class LoanOfficerOut(LoanOfficerBase):
    lo_id: int

    class Config:
        from_attributes = True


class LoanOfficerGroupSummaryOut(BaseModel):
    lo_id: int
    employee_id: int
    full_name: str | None = None
    region_id: int | None = None
    branch_id: int | None = None
    group_count: int
    groups: List[GroupOut]

    class Config:
        from_attributes = True
