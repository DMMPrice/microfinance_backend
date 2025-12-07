# app/schemas/employee_schemas.py

from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class EmployeeOut(BaseModel):
    employee_id: int
    user_id: int
    full_name: str
    phone: Optional[str]
    role_id: int
    region_id: Optional[int]
    branch_id: Optional[int]
    employee_code: Optional[str]
    date_joined: Optional[date]
    notes: Optional[str]
    is_active: bool
    created_on: datetime

    class Config:
        from_attributes = True
