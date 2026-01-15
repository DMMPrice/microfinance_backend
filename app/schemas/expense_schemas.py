# app/schemas/expense_schemas.py

from pydantic import BaseModel
from typing import Optional
from enum import Enum


# ----------------------------
# Expense Category Schemas
# ----------------------------
class ExpenseCategoryBase(BaseModel):
    category_name: str
    is_active: bool = True

    class Config:
        extra = "forbid"


class ExpenseCategoryCreate(ExpenseCategoryBase):
    pass


class ExpenseCategoryUpdate(BaseModel):
    category_name: Optional[str] = None
    is_active: Optional[bool] = None

    class Config:
        extra = "forbid"


class ExpenseCategoryOut(ExpenseCategoryBase):
    category_id: int

    class Config:
        from_attributes = True
        use_enum_values = True
        extra = "forbid"


# ----------------------------
# Expense SubCategory Schemas
# ----------------------------
class PaymentType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class ExpenseSubCategoryBase(BaseModel):
    category_id: int
    subcategory_name: str
    is_active: bool = True
    payment_type: PaymentType = PaymentType.DEBIT  # ✅ NEW

    class Config:
        extra = "forbid"
        use_enum_values = True


class ExpenseSubCategoryCreate(ExpenseSubCategoryBase):
    pass


class ExpenseSubCategoryUpdate(BaseModel):
    category_id: Optional[int] = None
    subcategory_name: Optional[str] = None
    is_active: Optional[bool] = None
    payment_type: Optional[PaymentType] = None  # ✅ NEW

    class Config:
        extra = "forbid"
        use_enum_values = True


class ExpenseSubCategoryOut(ExpenseSubCategoryBase):
    subcategory_id: int

    class Config:
        from_attributes = True
        use_enum_values = True
        extra = "forbid"
