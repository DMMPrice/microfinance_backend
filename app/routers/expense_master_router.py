# app/routes/expense_master_router.py

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.models.expense_categories_model import ExpenseCategory
from app.models.expense_subcategories_model import ExpenseSubCategory
from app.schemas.expense_schemas import (
    ExpenseCategoryCreate,
    ExpenseCategoryOut,
    ExpenseCategoryUpdate,
    ExpenseSubCategoryCreate,
    ExpenseSubCategoryOut,
    ExpenseSubCategoryUpdate, PaymentType,
)

router = APIRouter(prefix="/expenses/master", tags=["Expense Master"])


# ==========================================================
# CATEGORY CRUD
# ==========================================================

@router.post("/categories", response_model=ExpenseCategoryOut)
def create_category(payload: ExpenseCategoryCreate, db: Session = Depends(get_db)):
    exists = (
        db.query(ExpenseCategory)
        .filter(ExpenseCategory.category_name == payload.category_name)
        .first()
    )
    if exists:
        raise HTTPException(400, "Category name already exists")

    cat = ExpenseCategory(
        category_name=payload.category_name,
        is_active=payload.is_active,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.get("/categories", response_model=list[ExpenseCategoryOut])
def list_categories(
        is_active: Optional[bool] = Query(default=None, description="Filter by active status"),
        db: Session = Depends(get_db),
):
    q = db.query(ExpenseCategory)
    if is_active is not None:
        q = q.filter(ExpenseCategory.is_active == is_active)
    return q.order_by(ExpenseCategory.category_name.asc()).all()


@router.get("/categories/{category_id}", response_model=ExpenseCategoryOut)
def get_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.query(ExpenseCategory).filter(ExpenseCategory.category_id == category_id).first()
    if not cat:
        raise HTTPException(404, "Category not found")
    return cat


@router.put("/categories/{category_id}", response_model=ExpenseCategoryOut)
def update_category(category_id: int, payload: ExpenseCategoryUpdate, db: Session = Depends(get_db)):
    cat = db.query(ExpenseCategory).filter(ExpenseCategory.category_id == category_id).first()
    if not cat:
        raise HTTPException(404, "Category not found")

    if payload.category_name is not None:
        dup = (
            db.query(ExpenseCategory)
            .filter(
                ExpenseCategory.category_name == payload.category_name,
                ExpenseCategory.category_id != category_id,
            )
            .first()
        )
        if dup:
            raise HTTPException(400, "Category name already in use")
        cat.category_name = payload.category_name

    if payload.is_active is not None:
        cat.is_active = payload.is_active

    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.query(ExpenseCategory).filter(ExpenseCategory.category_id == category_id).first()
    if not cat:
        raise HTTPException(404, "Category not found")

    # Prevent delete if subcategories exist
    used = (
        db.query(ExpenseSubCategory)
        .filter(ExpenseSubCategory.category_id == category_id)
        .first()
    )
    if used:
        raise HTTPException(400, "Cannot delete category: subcategories exist")

    db.delete(cat)
    db.commit()
    return {"message": "Category deleted successfully"}


# ==========================================================
# SUBCATEGORY CRUD
# ==========================================================

@router.post("/subcategories", response_model=ExpenseSubCategoryOut)
def create_subcategory(payload: ExpenseSubCategoryCreate, db: Session = Depends(get_db)):
    # Ensure category exists
    cat = (
        db.query(ExpenseCategory)
        .filter(ExpenseCategory.category_id == payload.category_id)
        .first()
    )
    if not cat:
        raise HTTPException(400, "Invalid category_id")

    # Unique within same category
    exists = (
        db.query(ExpenseSubCategory)
        .filter(
            ExpenseSubCategory.category_id == payload.category_id,
            ExpenseSubCategory.subcategory_name == payload.subcategory_name,
        )
        .first()
    )
    if exists:
        raise HTTPException(400, "Subcategory already exists in this category")

    sub = ExpenseSubCategory(
        category_id=payload.category_id,
        subcategory_name=payload.subcategory_name,
        is_active=payload.is_active,
        payment_type=payload.payment_type,  # ✅ NEW
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.get("/subcategories", response_model=list[ExpenseSubCategoryOut])
def list_subcategories(
        category_id: Optional[int] = Query(default=None, description="Filter by category_id"),
        is_active: Optional[bool] = Query(default=None, description="Filter by active status"),
        payment_type: Optional[PaymentType] = Query(default=None, description="Filter by payment type (DEBIT/CREDIT)"),
        # ✅ NEW
        db: Session = Depends(get_db),
):
    q = db.query(ExpenseSubCategory)

    if category_id is not None:
        q = q.filter(ExpenseSubCategory.category_id == category_id)
    if is_active is not None:
        q = q.filter(ExpenseSubCategory.is_active == is_active)
    if payment_type is not None:
        q = q.filter(ExpenseSubCategory.payment_type == payment_type)  # ✅ NEW

    return q.order_by(ExpenseSubCategory.subcategory_name.asc()).all()


@router.get("/subcategories/{subcategory_id}", response_model=ExpenseSubCategoryOut)
def get_subcategory(subcategory_id: int, db: Session = Depends(get_db)):
    sub = (
        db.query(ExpenseSubCategory)
        .filter(ExpenseSubCategory.subcategory_id == subcategory_id)
        .first()
    )
    if not sub:
        raise HTTPException(404, "Subcategory not found")
    return sub


@router.put("/subcategories/{subcategory_id}", response_model=ExpenseSubCategoryOut)
def update_subcategory(subcategory_id: int, payload: ExpenseSubCategoryUpdate, db: Session = Depends(get_db)):
    sub = (
        db.query(ExpenseSubCategory)
        .filter(ExpenseSubCategory.subcategory_id == subcategory_id)
        .first()
    )
    if not sub:
        raise HTTPException(404, "Subcategory not found")

    new_category_id = payload.category_id if payload.category_id is not None else sub.category_id
    new_name = payload.subcategory_name if payload.subcategory_name is not None else sub.subcategory_name

    # If category_id is changing, ensure new category exists
    if payload.category_id is not None:
        cat = db.query(ExpenseCategory).filter(ExpenseCategory.category_id == payload.category_id).first()
        if not cat:
            raise HTTPException(400, "Invalid category_id")

    # Unique within category check
    dup = (
        db.query(ExpenseSubCategory)
        .filter(
            ExpenseSubCategory.category_id == new_category_id,
            ExpenseSubCategory.subcategory_name == new_name,
            ExpenseSubCategory.subcategory_id != subcategory_id,
        )
        .first()
    )
    if dup:
        raise HTTPException(400, "Subcategory name already in use in this category")

    if payload.category_id is not None:
        sub.category_id = payload.category_id

    if payload.subcategory_name is not None:
        sub.subcategory_name = payload.subcategory_name

    if payload.is_active is not None:
        sub.is_active = payload.is_active

    if payload.payment_type is not None:
        sub.payment_type = payload.payment_type  # ✅ NEW

    db.commit()
    db.refresh(sub)
    return sub


@router.delete("/subcategories/{subcategory_id}")
def delete_subcategory(subcategory_id: int, db: Session = Depends(get_db)):
    sub = (
        db.query(ExpenseSubCategory)
        .filter(ExpenseSubCategory.subcategory_id == subcategory_id)
        .first()
    )
    if not sub:
        raise HTTPException(404, "Subcategory not found")

    db.delete(sub)
    db.commit()
    return {"message": "Subcategory deleted successfully"}
