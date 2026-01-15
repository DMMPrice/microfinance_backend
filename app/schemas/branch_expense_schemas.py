from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class BranchExpenseBase(BaseModel):
    branch_id: int
    category_id: int
    subcategory_id: Optional[int] = None  # ✅ added
    expense_date: date
    amount: Decimal
    payee: Optional[str] = None  # ✅ added
    description: Optional[str] = None
    payment_mode: Optional[str] = None
    reference_no: Optional[str] = None


class BranchExpenseCreate(BranchExpenseBase):
    pass


class BranchExpenseUpdate(BaseModel):
    branch_id: Optional[int] = None
    category_id: Optional[int] = None
    subcategory_id: Optional[int] = None  # ✅ added
    expense_date: Optional[date] = None
    amount: Optional[Decimal] = None  # ✅ keep Decimal (don’t use float)
    payee: Optional[str] = None  # ✅ added
    description: Optional[str] = None
    payment_mode: Optional[str] = None
    reference_no: Optional[str] = None


class BranchExpenseOut(BranchExpenseBase):
    expense_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
