# app/schemas/auth_schemas.py

from pydantic import BaseModel
from typing import Optional
from datetime import date


class UserCreate(BaseModel):
    username: str
    email: str
    password: str  # plain text as per your dev requirement

    full_name: str
    phone: Optional[str] = None

    role_id: int
    region_id: Optional[int] = None
    branch_id: Optional[int] = None
    is_active: bool = True

    employee_code: Optional[str] = None
    date_joined: Optional[date] = None
    notes: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_role: Optional[str] = None
    user_id: int
    user_name: str


class UserUpdate(BaseModel):
    # All fields optional for partial update
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None  # still plain as per current requirement

    full_name: Optional[str] = None
    phone: Optional[str] = None

    role_id: Optional[int] = None
    region_id: Optional[int] = None
    branch_id: Optional[int] = None
    is_active: Optional[bool] = None

    employee_code: Optional[str] = None
    notes: Optional[str] = None
