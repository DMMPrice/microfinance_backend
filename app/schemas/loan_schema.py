from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from typing import Optional, List, Literal


class LoanCreate(BaseModel):
    member_id: int
    product_id: Optional[int] = None

    loan_account_no: Optional[str] = None

    disburse_date: date
    first_installment_date: date

    principal_amount: float = Field(gt=0)
    flat_interest_total: float = Field(ge=0)
    duration_weeks: int = Field(gt=0)


class LoanOut(BaseModel):
    loan_id: int
    loan_account_no: Optional[str]
    member_id: int
    group_id: int
    lo_id: int

    principal_amount: float
    interest_amount_total: float
    total_disbursed_amount: float
    installment_amount: float
    duration_weeks: int

    status: str
    advance_balance: float

    class Config:
        from_attributes = True


class InstallmentOut(BaseModel):
    installment_id: int
    installment_no: int
    due_date: date

    principal_due: float
    interest_due: float
    total_due: float

    principal_paid: float
    interest_paid: float
    total_paid: float

    status: str
    paid_date: Optional[date] = None

    class Config:
        from_attributes = True


class PaymentCreate(BaseModel):
    payment_date: Optional[datetime] = None
    amount_received: float = Field(gt=0)
    payment_mode: Literal["CASH", "UPI", "BANK", "CARD", "OTHER"] = "CASH"
    receipt_no: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("receipt_no", "remarks", mode="before")
    def empty_to_none(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None


class PaymentResult(BaseModel):
    payment_id: int
    applied_to_installments: int
    advance_added: float
    new_advance_balance: float


class LedgerRowOut(BaseModel):
    ledger_id: int
    txn_date: datetime
    txn_type: str
    debit: float
    credit: float
    principal_component: float
    interest_component: float
    balance_outstanding: float
    narration: Optional[str] = None

    class Config:
        from_attributes = True


class LoanSummaryOut(BaseModel):
    loan_id: int
    loan_account_no: Optional[str] = None

    member_id: int
    member_name: str
    group_id: int
    group_name: str
    lo_id: int

    principal_amount: float
    interest_amount_total: float
    total_disbursed_amount: float

    total_paid: float
    outstanding: float
    advance_balance: float
    status: str

    next_due_date: Optional[date] = None
    next_due_amount: Optional[float] = None


class LoanListOut(BaseModel):
    loan_id: int
    loan_account_no: Optional[str] = None
    member_id: int
    group_id: int
    lo_id: int
    principal_amount: float
    total_disbursed_amount: float
    installment_amount: float
    duration_weeks: int
    status: str
    disburse_date: date
    first_installment_date: date

    class Config:
        from_attributes = True


class CollectionRowOut(BaseModel):
    loan_id: int
    member_id: int
    member_name: str
    group_id: int
    group_name: str
    due_date: date
    installment_no: int
    due_left: float
    advance_balance: float
    status: str


class AdvanceApplyResult(BaseModel):
    applied_installments: int
    used_advance: float
    remaining_advance: float


class LoanStatsOut(BaseModel):
    DISBURSED: int = 0
    ACTIVE: int = 0
    CLOSED: int = 0
    OTHER: int = 0


class LoanMasterRowOut(BaseModel):
    loan_id: int
    loan_account_no: str

    member_id: int
    member_name: str

    group_id: int
    group_name: str

    lo_id: int | None = None
    branch_id: int | None = None
    region_id: int | None = None

    product_id: int | None = None
    disburse_date: date | None = None
    first_installment_date: date | None = None

    duration_weeks: int
    installment_type: str
    installment_amount: float

    principal_amount: float
    interest_amount_total: float
    total_disbursed_amount: float

    total_paid: float
    outstanding: float
    advance_balance: float

    status: str
