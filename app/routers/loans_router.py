from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import timedelta, date
from decimal import Decimal

from app.utils.database import get_db
from app.models.loan_model import Loan
from app.models.loan_installment_model import LoanInstallment
from app.models.loan_payment_model import LoanPayment
from app.models.loan_payment_allocation_model import LoanPaymentAllocation
from app.models.loan_ledger_model import LoanLedger
from app.models.system_settings_model import SystemSetting

from app.schemas.loan_schema import (
    LoanCreate, LoanOut, InstallmentOut,
    PaymentCreate, PaymentResult, LedgerRowOut
)

router = APIRouter(prefix="/loans", tags=["Loans"])


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"))


def get_setting(db: Session, key: str, default: str) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return row.value if row else default


def last_balance(db: Session, loan_id: int) -> Decimal:
    last = (
        db.query(LoanLedger)
        .filter(LoanLedger.loan_id == loan_id)
        .order_by(LoanLedger.ledger_id.desc())
        .first()
    )
    return last.balance_outstanding if last else Decimal("0.00")


@router.post("", response_model=LoanOut)
def create_loan(payload: LoanCreate, db: Session = Depends(get_db)):
    # Fetch member snapshot from DB (your members table exists)
    member = db.execute(
        text("""
            select member_id, group_id, lo_id, branch_id, region_id
            from members
            where member_id=:mid and is_active=true
        """),
        {"mid": payload.member_id},
    ).mappings().first()

    if not member:
        raise HTTPException(404, "Member not found / inactive")

    group = db.execute(
        text("""
            select group_id, lo_id, branch_id, region_id
            from groups
            where group_id=:gid
        """),
        {"gid": member["group_id"]},
    ).mappings().first()

    if not group:
        raise HTTPException(400, "Member group not found")

    min_weeks = int(get_setting(db, "MIN_WEEKS_BEFORE_CLOSURE", "4"))

    principal = money(payload.principal_amount)
    interest_total = money(payload.flat_interest_total)
    total = principal + interest_total

    installment_amount = (total / money(payload.duration_weeks)).quantize(Decimal("0.01"))

    loan = Loan(
        loan_account_no=payload.loan_account_no,
        member_id=payload.member_id,
        group_id=group["group_id"],
        lo_id=group["lo_id"],
        branch_id=group["branch_id"],
        region_id=group["region_id"],
        product_id=payload.product_id,
        disburse_date=payload.disburse_date,
        first_installment_date=payload.first_installment_date,
        duration_weeks=payload.duration_weeks,
        installment_type="WEEKLY",
        principal_amount=principal,
        interest_amount_total=interest_total,
        total_disbursed_amount=total,
        installment_amount=installment_amount,
        min_weeks_before_closure=min_weeks,
        allow_early_closure=False,
        advance_balance=money(0),
        status="DISBURSED",
    )

    db.add(loan)
    try:
        db.flush()  # gets loan_id + triggers partial unique index
    except Exception as e:
        db.rollback()
        raise HTTPException(400, f"Cannot create loan (maybe active loan exists): {str(e)}")

    # schedule
    principal_week = (principal / money(payload.duration_weeks)).quantize(Decimal("0.01"))
    interest_week = (interest_total / money(payload.duration_weeks)).quantize(Decimal("0.01"))

    due = payload.first_installment_date
    for i in range(1, payload.duration_weeks + 1):
        inst_total = (principal_week + interest_week).quantize(Decimal("0.01"))
        db.add(LoanInstallment(
            loan_id=loan.loan_id,
            installment_no=i,
            due_date=due,
            principal_due=principal_week,
            interest_due=interest_week,
            total_due=inst_total,
            status="PENDING"
        ))
        due = due + timedelta(days=7)

    # ledger: post receivable
    db.add(LoanLedger(
        loan_id=loan.loan_id,
        txn_type="DISBURSEMENT",
        debit=total,
        credit=money(0),
        principal_component=principal,
        interest_component=interest_total,
        balance_outstanding=total,
        narration="Loan disbursed (flat receivable posted)"
    ))

    db.commit()
    db.refresh(loan)
    return loan


@router.get("/{loan_id}/schedule", response_model=list[InstallmentOut])
def get_schedule(loan_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(LoanInstallment)
        .filter(LoanInstallment.loan_id == loan_id)
        .order_by(LoanInstallment.installment_no.asc())
        .all()
    )
    return rows


@router.post("/{loan_id}/payments", response_model=PaymentResult)
def pay_loan(loan_id: int, payload: PaymentCreate, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(404, "Loan not found")
    if loan.status not in ("DISBURSED", "ACTIVE"):
        raise HTTPException(400, f"Cannot pay loan in status {loan.status}")

    amount = money(payload.amount_received)

    pay = LoanPayment(
        loan_id=loan.loan_id,
        member_id=loan.member_id,
        group_id=loan.group_id,
        lo_id=loan.lo_id,
        payment_date=payload.payment_date,
        amount_received=amount,
        payment_mode=payload.payment_mode,
        receipt_no=payload.receipt_no,
        remarks=payload.remarks,
    )
    db.add(pay)
    db.flush()

    remaining = amount
    applied_count = 0
    principal_applied = Decimal("0.00")
    interest_applied = Decimal("0.00")

    installments = (
        db.query(LoanInstallment)
        .filter(LoanInstallment.loan_id == loan.loan_id, LoanInstallment.status != "PAID")
        .order_by(LoanInstallment.installment_no.asc())
        .all()
    )

    for inst in installments:
        if remaining <= 0:
            break

        due_left = (inst.total_due - inst.total_paid).quantize(Decimal("0.01"))
        if due_left <= 0:
            inst.status = "PAID"
            continue

        take = remaining if remaining < due_left else due_left
        remaining -= take

        # interest-first allocation
        i_left = (inst.interest_due - inst.interest_paid).quantize(Decimal("0.01"))
        i_take = min(take, i_left)
        p_take = (take - i_take).quantize(Decimal("0.01"))

        inst.interest_paid = (inst.interest_paid + i_take).quantize(Decimal("0.01"))
        inst.principal_paid = (inst.principal_paid + p_take).quantize(Decimal("0.01"))
        inst.total_paid = (inst.total_paid + take).quantize(Decimal("0.01"))

        interest_applied += i_take
        principal_applied += p_take

        if inst.total_paid >= inst.total_due:
            inst.status = "PAID"
            inst.paid_date = date.today()
        else:
            inst.status = "PART_PAID"

        db.add(LoanPaymentAllocation(
            payment_id=pay.payment_id,
            installment_id=inst.installment_id,
            principal_alloc=p_take,
            interest_alloc=i_take,
        ))
        applied_count += 1

    advance_added = remaining if remaining > 0 else Decimal("0.00")
    loan.advance_balance = (loan.advance_balance + advance_added).quantize(Decimal("0.01"))

    if loan.status == "DISBURSED":
        loan.status = "ACTIVE"

    prev = last_balance(db, loan.loan_id)
    new_balance = (prev - amount).quantize(Decimal("0.01"))
    if new_balance < 0:
        new_balance = Decimal("0.00")

    db.add(LoanLedger(
        loan_id=loan.loan_id,
        txn_type="PAYMENT",
        ref_table="loan_payments",
        ref_id=pay.payment_id,
        debit=money(0),
        credit=amount,
        principal_component=principal_applied,
        interest_component=interest_applied,
        balance_outstanding=new_balance,
        narration=f"Cash collected. Advance added: {advance_added}"
    ))

    db.commit()

    return PaymentResult(
        payment_id=pay.payment_id,
        applied_to_installments=applied_count,
        advance_added=float(advance_added),
        new_advance_balance=float(loan.advance_balance),
    )


@router.get("/{loan_id}/statement", response_model=list[LedgerRowOut])
def statement(loan_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(LoanLedger)
        .filter(LoanLedger.loan_id == loan_id)
        .order_by(LoanLedger.ledger_id.asc())
        .all()
    )
    return rows


@router.post("/{loan_id}/close")
def close_loan(loan_id: int, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(404, "Loan not found")

    weeks_since = (date.today() - loan.disburse_date).days // 7
    if (not loan.allow_early_closure) and (weeks_since < loan.min_weeks_before_closure):
        raise HTTPException(
            400,
            f"Cannot close before {loan.min_weeks_before_closure} weeks. Current: {weeks_since} weeks."
        )

    bal = last_balance(db, loan.loan_id)
    if bal > Decimal("0.00"):
        raise HTTPException(400, f"Cannot close. Outstanding is {bal}")

    loan.status = "CLOSED"
    loan.closing_date = date.today()

    db.add(LoanLedger(
        loan_id=loan.loan_id,
        txn_type="CLOSURE",
        debit=money(0),
        credit=money(0),
        principal_component=money(0),
        interest_component=money(0),
        balance_outstanding=Decimal("0.00"),
        narration="Loan closed"
    ))
    db.commit()
    return {"message": "loan closed", "loan_id": loan.loan_id}
