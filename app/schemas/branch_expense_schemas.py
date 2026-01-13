# app/schemas/branch_expense_schemas.py

from pydantic import BaseModel
from typing import Optional
from datetime import date


class BranchExpenseBase(BaseModel):
    branch_id: int
    category_id: int
    expense_date: date
    description: Optional[str] = None
    amount: float
    payment_mode: Optional[str] = None
    reference_no: Optional[str] = None


class BranchExpenseCreate(BranchExpenseBase):
    pass


class BranchExpenseUpdate(BaseModel):
    branch_id: Optional[int] = None
    category_id: Optional[int] = None
    expense_date: Optional[date] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    payment_mode: Optional[str] = None
    reference_no: Optional[str] = None


class BranchExpenseOut(BranchExpenseBase):
    expense_id: int

    class Config:
        from_attributes = True
