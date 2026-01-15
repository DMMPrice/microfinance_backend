# app/routers/branch_expenses_router.py

from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.models.branches_model import Branch, BranchExpense
from app.models.expense_categories_model import ExpenseCategory
from app.models.expense_subcategories_model import ExpenseSubCategory
from app.schemas.branch_expense_schemas import (
    BranchExpenseCreate,
    BranchExpenseOut,
    BranchExpenseUpdate,
)

router = APIRouter(prefix="/branch-expenses", tags=["Branch Expenses"])


def validate_branch(db: Session, branch_id: int):
    branch = db.query(Branch).filter(Branch.branch_id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=400, detail="Invalid branch_id")


def validate_category(db: Session, category_id: int):
    cat = db.query(ExpenseCategory).filter(ExpenseCategory.category_id == category_id).first()
    if not cat:
        raise HTTPException(status_code=400, detail="Invalid category_id")


def validate_subcategory(db: Session, subcategory_id: int, category_id: int):
    """
    Ensure subcategory exists AND belongs to the given category.
    """
    sub = (
        db.query(ExpenseSubCategory)
        .filter(
            ExpenseSubCategory.subcategory_id == subcategory_id,
            ExpenseSubCategory.category_id == category_id,
        )
        .first()
    )
    if not sub:
        raise HTTPException(status_code=400, detail="Invalid subcategory_id for this category")


@router.post("/", response_model=BranchExpenseOut)
def create_branch_expense(payload: BranchExpenseCreate, db: Session = Depends(get_db)):
    validate_branch(db, payload.branch_id)
    validate_category(db, payload.category_id)

    if payload.subcategory_id is not None:
        validate_subcategory(db, payload.subcategory_id, payload.category_id)

    exp = BranchExpense(**payload.model_dump())
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


@router.get("/", response_model=list[BranchExpenseOut])
def list_branch_expenses(
        branch_id: Optional[int] = Query(default=None),
        category_id: Optional[int] = Query(default=None),
        subcategory_id: Optional[int] = Query(default=None),
        from_date: Optional[date] = Query(default=None),
        to_date: Optional[date] = Query(default=None),
        db: Session = Depends(get_db),
):
    q = db.query(BranchExpense)

    if branch_id is not None:
        q = q.filter(BranchExpense.branch_id == branch_id)

    if category_id is not None:
        q = q.filter(BranchExpense.category_id == category_id)

    if subcategory_id is not None:
        q = q.filter(BranchExpense.subcategory_id == subcategory_id)

    if from_date is not None:
        q = q.filter(BranchExpense.expense_date >= from_date)

    if to_date is not None:
        q = q.filter(BranchExpense.expense_date <= to_date)

    return q.order_by(
        BranchExpense.expense_date.desc(),
        BranchExpense.expense_id.desc(),
    ).all()


@router.get("/{expense_id}", response_model=BranchExpenseOut)
def get_branch_expense(expense_id: int, db: Session = Depends(get_db)):
    exp = db.query(BranchExpense).filter(BranchExpense.expense_id == expense_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Expense not found")
    return exp


@router.put("/{expense_id}", response_model=BranchExpenseOut)
def update_branch_expense(expense_id: int, payload: BranchExpenseUpdate, db: Session = Depends(get_db)):
    exp = db.query(BranchExpense).filter(BranchExpense.expense_id == expense_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Expense not found")

    data = payload.model_dump(exclude_unset=True)

    if "branch_id" in data:
        validate_branch(db, data["branch_id"])

    if "category_id" in data:
        validate_category(db, data["category_id"])

    # ✅ if subcategory provided, validate it belongs to the right category
    if "subcategory_id" in data and data["subcategory_id"] is not None:
        effective_category_id = data.get("category_id", exp.category_id)
        validate_subcategory(db, data["subcategory_id"], effective_category_id)

    for k, v in data.items():
        setattr(exp, k, v)

    db.commit()
    db.refresh(exp)
    return exp


@router.delete("/{expense_id}")
def delete_branch_expense(expense_id: int, db: Session = Depends(get_db)):
    exp = db.query(BranchExpense).filter(BranchExpense.expense_id == expense_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Expense not found")

    db.delete(exp)
    db.commit()
    return {"message": "Expense deleted successfully"}
