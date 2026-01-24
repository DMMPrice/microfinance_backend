from pydantic import BaseModel, Field, field_validator, constr
from datetime import date, datetime
from typing import Optional, Literal, Dict
from decimal import Decimal

# -------------------------------------------------
# Helpers
# -------------------------------------------------
MoneyDecimal = Decimal


# -------------------------------------------------
# Loan Create / Update
# -------------------------------------------------
class LoanCreate(BaseModel):
    member_id: int
    product_id: Optional[int] = None

    loan_account_no: Optional[constr(strip_whitespace=True, min_length=3, max_length=50)] = None

    disburse_date: date
    first_installment_date: date

    principal_amount: Decimal = Field(gt=0)
    duration_weeks: int = Field(gt=0)

    # ✅ OPTIONAL (frontend may send), but backend can compute from settings if 0/None
    insurance_fee: Decimal = Field(default=0, ge=0)
    processing_fee: Decimal = Field(default=0, ge=0)
    book_price: Decimal = Field(default=0, ge=0)

    @field_validator("loan_account_no", mode="before")
    def empty_loan_acc_to_none(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None


class LoanUpdate(BaseModel):
    loan_account_no: Optional[constr(strip_whitespace=True, min_length=3, max_length=50)] = None

    product_id: Optional[int] = None
    disburse_date: Optional[date] = None
    first_installment_date: Optional[date] = None
    duration_weeks: Optional[int] = None
    principal_amount: Optional[Decimal] = None

    # ✅ fees editable only if no payment exists (optional)
    insurance_fee: Optional[Decimal] = None
    processing_fee: Optional[Decimal] = None
    book_price: Optional[Decimal] = None

    # DISBURSED / ACTIVE / PAUSED / CLOSED / CANCELLED / INACTIVE
    status: Optional[str] = None


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

    status: str  # PENDING / OVERDUE / PAID
    paid_date: Optional[date] = None

    class Config:
        from_attributes = True


# -------------------------------------------------
# Payment
# -------------------------------------------------
class PaymentCreate(BaseModel):
    payment_date: Optional[datetime] = None
    amount_received: Decimal = Field(gt=0)
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


class CollectionPaymentCreate(BaseModel):
    loan_id: int
    payment_date: Optional[datetime] = None
    amount_received: Decimal = Field(gt=0)
    payment_mode: Literal["CASH", "UPI", "BANK", "CARD", "OTHER"] = "CASH"
    receipt_no: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("receipt_no", "remarks", mode="before")
    def empty_to_none(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None


# -------------------------------------------------
# Charge Collection (Manual)
# -------------------------------------------------
class ChargeCollectCreate(BaseModel):
    """
    ✅ Manual fee collection window:
    - Collect any one charge (insurance/processing/book) or a generic CHARGE amount.
    - Keeps records in LoanCharge + LoanLedger.
    """
    charge_type: Literal["INSURANCE_FEE", "PROCESSING_FEE", "BOOK_PRICE", "OTHER"] = "OTHER"

    payment_date: Optional[datetime] = None
    amount_received: Decimal = Field(gt=0)
    payment_mode: Literal["CASH", "UPI", "BANK", "CARD", "OTHER"] = "CASH"
    receipt_no: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("receipt_no", "remarks", mode="before")
    def empty_to_none(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None


class ChargeCollectResult(BaseModel):
    collected: float

    # ✅ can be single number or a breakdown (keep both optional)
    pending_charges: float = 0.0
    pending_breakdown: Optional[Dict[str, float]] = None


class ChargeOut(BaseModel):
    charge_id: int
    loan_id: int
    charge_type: str

    amount: float
    is_waived: bool
    waived_amount: float

    collected_amount: float
    is_collected: bool
    collected_on: Optional[datetime] = None
    payment_mode: Optional[str] = None
    receipt_no: Optional[str] = None

    remarks: Optional[str] = None
    charge_date: Optional[datetime] = None

    class Config:
        from_attributes = True


# -------------------------------------------------
# Ledger / Summary / Master
# -------------------------------------------------
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

    # ✅ Charges snapshot
    charges_total: float = 0.0
    charges_waived: float = 0.0
    charges_collected: float = 0.0
    charges_pending: float = 0.0


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
    loan_account_no: Optional[str] = None
    installment_amount: float

    member_id: int
    member_name: str
    group_id: int
    group_name: str

    due_date: date
    installment_no: int
    due_left: float
    total_due: float

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
