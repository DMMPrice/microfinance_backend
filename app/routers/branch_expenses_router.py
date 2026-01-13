# app/routers/branch_expenses_router.py

from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.models.branches_model import Branch
from app.models.branches_model import BranchExpense
from app.models.expense_categories_model import ExpenseCategory  # ✅ create/import this model
from app.schemas.branch_expense_schemas import (
    BranchExpenseCreate,
    BranchExpenseOut,
    BranchExpenseUpdate,
)

router = APIRouter(prefix="/branch-expenses", tags=["Branch Expenses"])


@router.post("/", response_model=BranchExpenseOut)
def create_branch_expense(payload: BranchExpenseCreate, db: Session = Depends(get_db)):
    # ✅ validate branch
    branch = db.query(Branch).filter(Branch.branch_id == payload.branch_id).first()
    if not branch:
        raise HTTPException(400, "Invalid branch_id")

    # ✅ validate category
    cat = db.query(ExpenseCategory).filter(ExpenseCategory.category_id == payload.category_id).first()
    if not cat:
        raise HTTPException(400, "Invalid category_id")

    exp = BranchExpense(**payload.model_dump())
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


@router.get("/", response_model=list[BranchExpenseOut])
def list_branch_expenses(
        branch_id: Optional[int] = Query(default=None),
        category_id: Optional[int] = Query(default=None),
        from_date: Optional[date] = Query(default=None),
        to_date: Optional[date] = Query(default=None),
        db: Session = Depends(get_db),
):
    q = db.query(BranchExpense)

    if branch_id is not None:
        q = q.filter(BranchExpense.branch_id == branch_id)

    if category_id is not None:
        q = q.filter(BranchExpense.category_id == category_id)

    if from_date is not None:
        q = q.filter(BranchExpense.expense_date >= from_date)

    if to_date is not None:
        q = q.filter(BranchExpense.expense_date <= to_date)

    return q.order_by(BranchExpense.expense_date.desc(), BranchExpense.expense_id.desc()).all()


@router.get("/{expense_id}", response_model=BranchExpenseOut)
def get_branch_expense(expense_id: int, db: Session = Depends(get_db)):
    exp = db.query(BranchExpense).filter(BranchExpense.expense_id == expense_id).first()
    if not exp:
        raise HTTPException(404, "Expense not found")
    return exp


@router.put("/{expense_id}", response_model=BranchExpenseOut)
def update_branch_expense(expense_id: int, payload: BranchExpenseUpdate, db: Session = Depends(get_db)):
    exp = db.query(BranchExpense).filter(BranchExpense.expense_id == expense_id).first()
    if not exp:
        raise HTTPException(404, "Expense not found")

    data = payload.model_dump(exclude_unset=True)

    if "branch_id" in data:
        branch = db.query(Branch).filter(Branch.branch_id == data["branch_id"]).first()
        if not branch:
            raise HTTPException(400, "Invalid branch_id")

    if "category_id" in data:
        cat = db.query(ExpenseCategory).filter(ExpenseCategory.category_id == data["category_id"]).first()
        if not cat:
            raise HTTPException(400, "Invalid category_id")

    for k, v in data.items():
        setattr(exp, k, v)

    db.commit()
    db.refresh(exp)
    return exp


@router.delete("/{expense_id}")
def delete_branch_expense(expense_id: int, db: Session = Depends(get_db)):
    exp = db.query(BranchExpense).filter(BranchExpense.expense_id == expense_id).first()
    if not exp:
        raise HTTPException(404, "Expense not found")

    db.delete(exp)
    db.commit()
    return {"message": "Expense deleted successfully"}
