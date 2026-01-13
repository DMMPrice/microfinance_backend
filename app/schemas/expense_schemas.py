# app/schemas/expense_schemas.py

from pydantic import BaseModel
from typing import Optional


# ----------------------------
# Expense Category Schemas
# ----------------------------
class ExpenseCategoryBase(BaseModel):
    category_name: str
    is_active: bool = True


class ExpenseCategoryCreate(ExpenseCategoryBase):
    pass


class ExpenseCategoryUpdate(BaseModel):
    category_name: Optional[str] = None
    is_active: Optional[bool] = None


class ExpenseCategoryOut(ExpenseCategoryBase):
    category_id: int

    class Config:
        from_attributes = True


# ----------------------------
# Expense SubCategory Schemas
# ----------------------------
class ExpenseSubCategoryBase(BaseModel):
    category_id: int
    subcategory_name: str
    is_active: bool = True


class ExpenseSubCategoryCreate(ExpenseSubCategoryBase):
    pass


class ExpenseSubCategoryUpdate(BaseModel):
    category_id: Optional[int] = None
    subcategory_name: Optional[str] = None
    is_active: Optional[bool] = None


class ExpenseSubCategoryOut(ExpenseSubCategoryBase):
    subcategory_id: int

    class Config:
        from_attributes = True
