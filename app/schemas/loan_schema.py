from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List


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
    payment_mode: str = "CASH"
    receipt_no: Optional[str] = None
    remarks: Optional[str] = None


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
l̥