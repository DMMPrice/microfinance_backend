# app/routes/loan_officers_router.py

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.utils.database import get_db
from app.models.loan_officer_model import LoanOfficer
from app.models.employee_model import Employee
from app.models.roles_model import Role
from app.models.group_model import Group

from app.schemas import (
    LoanOfficerCreate,
    LoanOfficerOut,
    LoanOfficerGroupSummaryOut,
)
from app.schemas.loan_officer_schemas import LoanOfficerWithEmployeeOut

router = APIRouter(prefix="/loan-officers", tags=["Loan Officers"])


# ===========================
# CREATE LOAN OFFICER
# ===========================

@router.post("/", response_model=LoanOfficerOut)
def create_loan_officer(
        payload: LoanOfficerCreate,
        db: Session = Depends(get_db),
):
    """
    Register an existing employee as a Loan Officer.

    Checks:
    - Employee must exist.
    - Employee's role must be 'loan_officer' (role_id == 4 or name == 'loan_officer').
    - One LoanOfficer per employee.
    """

    # 1️⃣ Ensure employee exists
    emp = db.query(Employee).filter(Employee.employee_id == payload.employee_id).first()
    if not emp:
        raise HTTPException(
            status_code=404,
            detail="Employee not found for given employee_id",
        )

    # 2️⃣ Ensure role is actually loan_officer
    role_obj = db.query(Role).filter(Role.id == emp.role_id).first()
    if not role_obj:
        raise HTTPException(status_code=400, detail="Role not found for employee.")

    role_name = (role_obj.name or "").lower()
    if role_name != "loan_officer" and emp.role_id != 4:
        raise HTTPException(
            status_code=400,
            detail="Employee's role must be 'loan_officer' to register as Loan Officer.",
        )

    # 3️⃣ Ensure not already a Loan Officer
    existing_lo = (
        db.query(LoanOfficer).filter(LoanOfficer.employee_id == emp.employee_id).first()
    )
    if existing_lo:
        raise HTTPException(
            status_code=400,
            detail="This employee is already registered as a Loan Officer.",
        )

    # 4️⃣ Create LoanOfficer row
    lo = LoanOfficer(employee_id=emp.employee_id)
    db.add(lo)
    db.commit()
    db.refresh(lo)

    return lo


# ===========================
# LIST LOAN OFFICERS
# ===========================

@router.get("/", response_model=List[LoanOfficerWithEmployeeOut])
def list_loan_officers(
        db: Session = Depends(get_db),
):
    """
    List all Loan Officers, including nested Employee + User details.
    (No token/RBAC-based filtering here.)
    """

    q = (
        db.query(LoanOfficer)
        .join(Employee, LoanOfficer.employee_id == Employee.employee_id)
        .options(joinedload(LoanOfficer.employee).joinedload(Employee.user))
    )

    return q.all()


# ===========================
# GET LOAN OFFICER DETAILS
# ===========================

@router.get("/{lo_id}", response_model=LoanOfficerWithEmployeeOut)
def get_loan_officer(
        lo_id: int,
        db: Session = Depends(get_db),
):
    """
    Get a single Loan Officer, including Employee + User details.
    (No token/RBAC checks here.)
    """

    lo = (
        db.query(LoanOfficer)
        .join(Employee, LoanOfficer.employee_id == Employee.employee_id)
        .options(joinedload(LoanOfficer.employee).joinedload(Employee.user))
        .filter(LoanOfficer.lo_id == lo_id)
        .first()
    )

    if not lo:
        raise HTTPException(status_code=404, detail="Loan Officer not found")

    return lo


# ===========================
# DELETE LOAN OFFICER
# ===========================

@router.delete("/{lo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_loan_officer(
        lo_id: int,
        db: Session = Depends(get_db),
):
    """
    Delete a Loan Officer record.
    (No token/RBAC checks here — enforce authorization elsewhere if needed.)
    """

    lo = db.query(LoanOfficer).filter(LoanOfficer.lo_id == lo_id).first()
    if not lo:
        raise HTTPException(status_code=404, detail="Loan Officer not found")

    db.delete(lo)
    db.commit()
    return


# ===========================
# GROUP COUNT FOR A LOAN OFFICER
# ===========================

@router.get("/{lo_id}/groups/count")
def get_loan_officer_group_count(
        lo_id: int,
        db: Session = Depends(get_db),
):
    """
    Return how many groups are assigned to a given Loan Officer.
    (No token/RBAC checks here.)
    """

    lo_exists = db.query(LoanOfficer.lo_id).filter(LoanOfficer.lo_id == lo_id).first()
    if not lo_exists:
        raise HTTPException(status_code=404, detail="Loan Officer not found")

    group_count = (
        db.query(func.count(Group.group_id))
        .filter(Group.lo_id == lo_id)
        .scalar()
    )

    return {"lo_id": lo_id, "group_count": group_count}


# ===========================
# LOAN OFFICER + GROUP SUMMARY
# ===========================

@router.get("/groups/summary", response_model=List[LoanOfficerGroupSummaryOut])
def loan_officer_group_summary(
        lo_id: Optional[int] = Query(None),
        db: Session = Depends(get_db),
):
    """
    Summary of Loan Officers + their groups.
    If lo_id is provided, return only that Loan Officer’s summary.
    (No token/RBAC filtering here.)
    """

    q = (
        db.query(LoanOfficer)
        .join(Employee, LoanOfficer.employee_id == Employee.employee_id)
        .options(joinedload(LoanOfficer.employee).joinedload(Employee.user))
    )

    if lo_id is not None:
        q = q.filter(LoanOfficer.lo_id == lo_id)

    loan_officers = q.all()

    if lo_id is not None and len(loan_officers) == 0:
        raise HTTPException(status_code=404, detail="Loan Officer not found")

    summaries: List[LoanOfficerGroupSummaryOut] = []

    for lo in loan_officers:
        emp = lo.employee
        if not emp:
            continue

        groups = db.query(Group).filter(Group.lo_id == lo.lo_id).all()

        summaries.append(
            LoanOfficerGroupSummaryOut(
                lo_id=lo.lo_id,
                employee_id=emp.employee_id,
                full_name=emp.full_name,
                region_id=emp.region_id,
                branch_id=emp.branch_id,
                group_count=len(groups),
                groups=groups,
            )
        )

    return summaries
