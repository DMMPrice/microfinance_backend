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
from app.utils.auth import get_current_user
from app.schemas import (
    LoanOfficerCreate,
    LoanOfficerOut,
    LoanOfficerGroupSummaryOut,
)
from app.schemas.loan_officer_schemas import LoanOfficerWithEmployeeOut

router = APIRouter(prefix="/loan-officers", tags=["Loan Officers"])


# ===========================
# Helper: access checks
# ===========================


def _ensure_can_access_lo(user: dict, lo: LoanOfficer):
    """
    Enforce access rules for a specific Loan Officer record.
    - admin / super_admin: full access
    - regional_manager: only LOs in their region
    - branch_manager: only LOs in their branch
    - loan_officer: only their own record
    """
    role = (user.get("role") or "").lower()
    employee = lo.employee  # via relationship

    if employee is None:
        # Data inconsistency; be safe and block
        raise HTTPException(
            status_code=400, detail="Loan Officer not linked to employee"
        )

    if role == "regional_manager":
        if employee.region_id != user.get("region_id"):
            raise HTTPException(status_code=403, detail="Access denied for this region")

    elif role == "branch_manager":
        if employee.branch_id != user.get("branch_id"):
            raise HTTPException(status_code=403, detail="Access denied for this branch")

    elif role == "loan_officer":
        # token has employee_id (see /login in auth_router)
        if employee.employee_id != user.get("employee_id"):
            raise HTTPException(
                status_code=403,
                detail="Loan Officers can access only their own record",
            )

    # admin / super_admin → allowed


def _ensure_can_create_in_scope(user: dict, employee: Employee):
    """
    Enforce creation scope based on current user's role.
    """
    role = (user.get("role") or "").lower()

    if role == "loan_officer":
        raise HTTPException(
            status_code=403,
            detail="Loan Officers cannot create Loan Officer records",
        )

    if role == "regional_manager":
        if employee.region_id != user.get("region_id"):
            raise HTTPException(
                status_code=403,
                detail="Regional Manager can create LOs only in their region",
            )

    if role == "branch_manager":
        if employee.branch_id != user.get("branch_id"):
            raise HTTPException(
                status_code=403,
                detail="Branch Manager can create LOs only in their branch",
            )

    # admin / super_admin → allowed


# ===========================
# CREATE LOAN OFFICER
# ===========================


@router.post("/", response_model=LoanOfficerOut)
def create_loan_officer(
    payload: LoanOfficerCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Register an existing employee as a Loan Officer.

    Checks:
    - Employee must exist.
    - Employee's role must be 'loan_officer' (role_id == 4 or name == 'loan_officer').
    - Role-based scope (admin, regional_manager, branch_manager).
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
        # you can relax this if needed
        raise HTTPException(
            status_code=400,
            detail="Employee's role must be 'loan_officer' to register as Loan Officer.",
        )

    # 3️⃣ Scope check based on current user
    _ensure_can_create_in_scope(user, emp)

    # 4️⃣ Ensure not already a Loan Officer
    existing_lo = (
        db.query(LoanOfficer).filter(LoanOfficer.employee_id == emp.employee_id).first()
    )
    if existing_lo:
        raise HTTPException(
            status_code=400,
            detail="This employee is already registered as a Loan Officer.",
        )

    # 5️⃣ Create LoanOfficer row
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
    user: dict = Depends(get_current_user),
):
    """
    List Loan Officers within the scope of the current user,
    including nested Employee + User details.

    - admin / super_admin → all
    - regional_manager    → LOs in their region
    - branch_manager      → LOs in their branch
    - loan_officer        → only their own record
    """

    role = (user.get("role") or "").lower()

    q = (
        db.query(LoanOfficer)
        .join(Employee, LoanOfficer.employee_id == Employee.employee_id)
        .options(
            joinedload(LoanOfficer.employee).joinedload(Employee.user)
        )
    )

    if role == "regional_manager":
        q = q.filter(Employee.region_id == user.get("region_id"))

    elif role == "branch_manager":
        q = q.filter(Employee.branch_id == user.get("branch_id"))

    elif role == "loan_officer":
        q = q.filter(Employee.employee_id == user.get("employee_id"))

    # admin / super_admin → no filter

    return q.all()


# ===========================
# GET LOAN OFFICER DETAILS
# ===========================


@router.get("/{lo_id}", response_model=LoanOfficerWithEmployeeOut)
def get_loan_officer(
    lo_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Get a single Loan Officer, including Employee + User details.
    """

    lo = (
        db.query(LoanOfficer)
        .join(Employee, LoanOfficer.employee_id == Employee.employee_id)
        .options(
            joinedload(LoanOfficer.employee).joinedload(Employee.user)
        )
        .filter(LoanOfficer.lo_id == lo_id)
        .first()
    )

    if not lo:
        raise HTTPException(status_code=404, detail="Loan Officer not found")

    _ensure_can_access_lo(user, lo)

    return lo


# ===========================
# DELETE LOAN OFFICER
# ===========================


@router.delete("/{lo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_loan_officer(
    lo_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Delete a Loan Officer record.

    - admin / super_admin → can delete any
    - regional_manager    → only LOs in their region
    - branch_manager      → only LOs in their branch
    - loan_officer        → cannot delete (even themselves)
    """

    lo = (
        db.query(LoanOfficer)
        .join(Employee, LoanOfficer.employee_id == Employee.employee_id)
        .filter(LoanOfficer.lo_id == lo_id)
        .first()
    )

    if not lo:
        raise HTTPException(status_code=404, detail="Loan Officer not found")

    role = (user.get("role") or "").lower()
    if role == "loan_officer":
        raise HTTPException(
            status_code=403,
            detail="Loan Officers cannot delete Loan Officer records",
        )

    _ensure_can_access_lo(user, lo)

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
    user: dict = Depends(get_current_user),
):
    """
    Return how many groups are assigned to a given Loan Officer.
    Respects the same RBAC rules used for /loan-officers/{lo_id}.
    """

    lo = (
        db.query(LoanOfficer)
        .join(LoanOfficer.employee)  # uses relationship
        .filter(LoanOfficer.lo_id == lo_id)
        .first()
    )
    if not lo:
        raise HTTPException(status_code=404, detail="Loan Officer not found")

    # reuse your existing access check
    _ensure_can_access_lo(user, lo)

    group_count = (
        db.query(func.count(Group.group_id)).filter(Group.lo_id == lo_id).scalar()
    )

    return {"lo_id": lo_id, "group_count": group_count}


# ===========================
# LOAN OFFICER + GROUP SUMMARY
# ===========================


@router.get("/groups/summary", response_model=List[LoanOfficerGroupSummaryOut])
def loan_officer_group_summary(
    lo_id: Optional[int] = Query(None),  # 👈 OPTIONAL PARAM
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Summary of Loan Officers + their groups.
    If lo_id is provided, return only that Loan Officer’s summary.

    RBAC:
    - admin/super_admin → all or specific LO
    - regional_manager  → only LOs in their region
    - branch_manager    → only LOs in their branch
    - loan_officer      → only their own (even if lo_id provided)
    """

    role = (user.get("role") or "").lower()

    # Base query with join to Employee table
    q = db.query(LoanOfficer).join(
        Employee, LoanOfficer.employee_id == Employee.employee_id
    )

    # ----------------------------
    #     OPTIONAL lo_id filter
    # ----------------------------
    if lo_id is not None:
        q = q.filter(LoanOfficer.lo_id == lo_id)

    # ----------------------------
    #     RBAC filtering
    # ----------------------------
    if role == "regional_manager":
        q = q.filter(Employee.region_id == user.get("region_id"))

    elif role == "branch_manager":
        q = q.filter(Employee.branch_id == user.get("branch_id"))

    elif role == "loan_officer":
        # Force LO to see only their own record
        q = q.filter(Employee.employee_id == user.get("employee_id"))

    # admin/super_admin → no extra filter

    loan_officers = (
        q.options(
            joinedload(LoanOfficer.employee).joinedload(Employee.user)
        )
        .all()
    )

    if lo_id is not None and len(loan_officers) == 0:
        raise HTTPException(404, "Loan Officer not found or access denied")

    summaries: List[LoanOfficerGroupSummaryOut] = []

    for lo in loan_officers:
        emp = lo.employee
        if not emp:
            continue

        # Get all groups assigned to this LO
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
