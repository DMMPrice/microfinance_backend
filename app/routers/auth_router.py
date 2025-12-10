# app/routes/auth_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import jwt

from app.utils.database import get_db
from app.models.user_model import User
from app.models.roles_model import Role
from app.models.employee_model import Employee
from app.models.loan_officer_model import LoanOfficer
from app.schemas import UserCreate, UserLogin, TokenResponse, UserUpdate
from app.core.config import JWT_SECRET, JWT_ALGO
from app.utils.auth import get_current_user  # your JWT dependency

router = APIRouter(prefix="/auth", tags=["Authentication"])


def create_access_token(data: dict, expires_minutes: int = 600):
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    data.update({"exp": expire})
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGO)


# ======================
#  REGISTER
# ======================
@router.post("/register")
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    # 1. Validate role
    role_obj = db.query(Role).filter(Role.id == payload.role_id).first()
    if not role_obj:
        raise HTTPException(400, "Invalid role_id provided.")

    # 2. Normalize region/branch
    region_id = payload.region_id if payload.region_id not in (0, None) else None
    branch_id = payload.branch_id if payload.branch_id not in (0, None) else None

    # Role hierarchy numeric mapping (based on seed order):
    # 1 = admin
    # 2 = regional_manager
    # 3 = branch_manager
    # 4 = loan_officer
    # 5 = super_admin

    if payload.role_id == 1:  # admin
        region_id = None
        branch_id = None

    elif payload.role_id == 2:  # regional_manager
        if region_id is None:
            raise HTTPException(400, "regional_manager must have region_id.")
        branch_id = None

    elif payload.role_id == 3:  # branch_manager
        if region_id is None or branch_id is None:
            raise HTTPException(
                400, "branch_manager must have both region_id and branch_id."
            )

    elif payload.role_id == 4:  # loan_officer
        if region_id is None or branch_id is None:
            raise HTTPException(
                400, "loan_officer must have both region_id and branch_id."
            )

    elif payload.role_id == 5:  # super_admin
        region_id = None
        branch_id = None

    else:
        raise HTTPException(400, "Unhandled role_id provided.")

    # 3. Create auth user
    auth_user = User(
        username=payload.username,
        email=payload.email,
        password=payload.password,  # plain for now (dev)
        is_active=payload.is_active,
    )
    db.add(auth_user)
    db.flush()  # get auth_user.user_id

    # 4. Create employee profile
    employee = Employee(
        user_id=auth_user.user_id,
        full_name=payload.full_name,
        phone=payload.phone,
        role_id=payload.role_id,
        region_id=region_id,
        branch_id=branch_id,
        employee_code=payload.employee_code,
        date_joined=payload.date_joined,
        notes=payload.notes,
        is_active=payload.is_active,
    )
    db.add(employee)
    db.flush()

    # 5. If loan officer, create loan_officers row
    if payload.role_id == 4:
        lo = LoanOfficer(employee_id=employee.employee_id)
        db.add(lo)

    db.commit()
    db.refresh(auth_user)

    return {
        "message": "User registered successfully",
        "user_id": auth_user.user_id,
        "employee_id": employee.employee_id,
    }


# ======================
#  LOGIN
# ======================
@router.post("/login", response_model=TokenResponse)
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    # 1. Find auth user
    user = db.query(User).filter(User.username == payload.username).first()
    if not user:
        raise HTTPException(401, "Invalid credentials")

    if payload.password != user.password:
        raise HTTPException(401, "Invalid credentials")

    # 2. Employee profile
    employee = user.employee
    if not employee:
        raise HTTPException(400, "Employee profile not found for this user.")

    role_name = employee.role.name if employee.role else None

    token_data = {
        "user_id": user.user_id,
        "employee_id": employee.employee_id,
        "role": role_name,
        "region_id": employee.region_id,
        "branch_id": employee.branch_id,
    }

    token = create_access_token(token_data)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_role=role_name,
        user_id=user.user_id,
        user_name=user.username,
    )


# ======================
#  ME
# ======================
@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


# ======================
#  UPDATE USER + ROLE
# ======================
@router.put("/users/{user_id}")
def update_user(
        user_id: int,
        payload: UserUpdate,
        db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    employee = user.employee
    if not employee:
        raise HTTPException(400, "Employee profile not found for this user.")

    # Keep track of old role to manage loan_officer mapping
    old_role_id = employee.role_id

    # --------------------------
    # Update user (login info)
    # --------------------------
    if payload.username is not None:
        # optional: check duplicates
        exists = (
            db.query(User)
            .filter(User.username == payload.username, User.user_id != user_id)
            .first()
        )
        if exists:
            raise HTTPException(400, "Username already taken")
        user.username = payload.username

    if payload.email is not None:
        exists = (
            db.query(User)
            .filter(User.email == payload.email, User.user_id != user_id)
            .first()
        )
        if exists:
            raise HTTPException(400, "Email already used")
        user.email = payload.email

    if payload.password is not None:
        user.password = payload.password  # still plain text as per dev requirement

    if payload.is_active is not None:
        user.is_active = payload.is_active

    # --------------------------
    # Update employee profile
    # --------------------------
    if payload.full_name is not None:
        employee.full_name = payload.full_name

    if payload.phone is not None:
        employee.phone = payload.phone

    # Role / region / branch logic
    new_role_id = payload.role_id if payload.role_id is not None else employee.role_id

    # Validate role if changed or provided
    role_obj = db.query(Role).filter(Role.id == new_role_id).first()
    if not role_obj:
        raise HTTPException(400, "Invalid role_id provided.")

    # Normalize region/branch from payload or keep old
    region_id = (
        payload.region_id if payload.region_id is not None else employee.region_id
    )
    branch_id = (
        payload.branch_id if payload.branch_id is not None else employee.branch_id
    )

    # Convert 0 → None
    region_id = None if region_id in (0, None) else region_id
    branch_id = None if branch_id in (0, None) else branch_id

    # Apply hierarchy rules (same as in register)
    if new_role_id == 1:  # admin
        region_id = None
        branch_id = None

    elif new_role_id == 2:  # regional_manager
        if region_id is None:
            raise HTTPException(400, "regional_manager must have region_id.")
        branch_id = None

    elif new_role_id == 3:  # branch_manager
        if region_id is None or branch_id is None:
            raise HTTPException(
                400, "branch_manager must have both region_id and branch_id."
            )

    elif new_role_id == 4:  # loan_officer
        if region_id is None or branch_id is None:
            raise HTTPException(
                400, "loan_officer must have both region_id and branch_id."
            )

    elif new_role_id == 5:  # super_admin
        region_id = None
        branch_id = None

    else:
        raise HTTPException(400, "Unhandled role_id provided.")

    # Save role + hierarchy to employee
    employee.role_id = new_role_id
    employee.region_id = region_id
    employee.branch_id = branch_id

    if payload.employee_code is not None:
        employee.employee_code = payload.employee_code

    if payload.date_joined is not None:
        employee.date_joined = payload.date_joined

    if payload.notes is not None:
        employee.notes = payload.notes

    if payload.is_active is not None:
        employee.is_active = payload.is_active

    # --------------------------
    # Manage loan_officer table
    # --------------------------
    # Old LO → New non-LO: remove entry
    if old_role_id == 4 and new_role_id != 4:
        lo_obj = (
            db.query(LoanOfficer)
            .filter(LoanOfficer.employee_id == employee.employee_id)
            .first()
        )
        if lo_obj:
            db.delete(lo_obj)

    # Old non-LO → New LO: create entry
    if old_role_id != 4 and new_role_id == 4:
        lo_exists = (
            db.query(LoanOfficer)
            .filter(LoanOfficer.employee_id == employee.employee_id)
            .first()
        )
        if not lo_exists:
            db.add(LoanOfficer(employee_id=employee.employee_id))

    db.commit()
    return {"message": "User updated successfully"}


# ======================
#  DELETE USER
# ======================
@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    # Because Employee.user_id has ON DELETE CASCADE
    # and LoanOfficer.employee_id has ON DELETE CASCADE,
    # deleting user will cascade to employee and loan_officer.
    db.delete(user)
    db.commit()

    return {"message": "User deleted successfully"}
