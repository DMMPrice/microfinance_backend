# app/schemas/loan_officer_schemas.py

from pydantic import BaseModel
from typing import List, Optional
from app.schemas.group_schemas import GroupOut  # or `from app.schemas import GroupOut`


# ---------- NESTED MINI SCHEMAS ----------

class UserMiniOut(BaseModel):
    user_id: int
    username: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None

    class Config:
        from_attributes = True


class EmployeeMiniOut(BaseModel):
    employee_id: int
    full_name: str
    phone: Optional[str] = None
    role_id: int
    region_id: Optional[int] = None
    branch_id: Optional[int] = None

    # 🔗 include linked user details
    user: Optional[UserMiniOut] = None

    class Config:
        from_attributes = True


# ---------- EXISTING BASES ----------

class LoanOfficerBase(BaseModel):
    employee_id: int


class LoanOfficerCreate(LoanOfficerBase):
    """Data needed to register an existing employee as a Loan Officer."""
    pass


# 🔹 USED FOR SIMPLE LISTS / DETAILS WITH EMPLOYEE+USER
class LoanOfficerWithEmployeeOut(BaseModel):
    lo_id: int
    employee_id: int
    employee: EmployeeMiniOut

    class Config:
        from_attributes = True


# (keep this if you still need a very simple version somewhere)
class LoanOfficerOut(LoanOfficerBase):
    lo_id: int

    class Config:
        from_attributes = True


class LoanOfficerGroupSummaryOut(BaseModel):
    lo_id: int
    employee_id: int
    full_name: Optional[str] = None
    region_id: Optional[int] = None
    branch_id: Optional[int] = None
    group_count: int
    groups: List[GroupOut]

    # 🔹 add user info here also (optional)
    user: Optional[UserMiniOut] = None

    class Config:
        from_attributes = True