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
from app.models.member_model import Member
from app.models.group_model import Group

from app.schemas.loan_schema import (
    LoanCreate,
    LoanOut,
    InstallmentOut,
    PaymentCreate,
    PaymentResult,
    LedgerRowOut,
    LoanSummaryOut,
    LoanListOut,
    CollectionRowOut,
    AdvanceApplyResult,
    LoanStatsOut,
)

router = APIRouter(prefix="/loans", tags=["Loans"])


# -------------------------------------------------
# Helpers
# -------------------------------------------------
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


# =================================================
# 🔹 STATIC ROUTES (ALWAYS FIRST)
# =================================================

@router.get("/stats", response_model=LoanStatsOut)
def loan_stats(db: Session = Depends(get_db)):
    rows = db.execute(
        text("select status, count(*) as c from loans group by status")
    ).mappings().all()

    out = LoanStatsOut()
    for r in rows:
        s = (r["status"] or "").upper()
        if hasattr(out, s):
            setattr(out, s, r["c"])
        else:
            out.OTHER += r["c"]
    return out


@router.get("/installments/due")
def installments_due(as_on: date, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
             select i.installment_id,
                    i.loan_id,
                    i.installment_no,
                    i.due_date,
                    (i.total_due - i.total_paid) as due_left,
                    l.member_id,
                    m.full_name                  as member_name,
                    l.group_id,
                    g.group_name,
                    l.lo_id
             from loan_installments i
                      join loans l on l.loan_id = i.loan_id
                      join members m on m.member_id = l.member_id
                      join groups g on g.group_id = l.group_id
             where i.status <> 'PAID'
               and i.due_date <= :as_on
               and l.status in ('DISBURSED', 'ACTIVE')
             order by i.due_date asc
             """),
        {"as_on": as_on},
    ).mappings().all()

    return [
        {
            "installment_id": r["installment_id"],
            "loan_id": r["loan_id"],
            "installment_no": r["installment_no"],
            "due_date": r["due_date"],
            "due_left": float(r["due_left"]),
            "member_id": r["member_id"],
            "member_name": r["member_name"],
            "group_id": r["group_id"],
            "group_name": r["group_name"],
            "lo_id": r["lo_id"],
        }
        for r in rows
    ]


@router.get("/by-member/{member_id}", response_model=list[LoanListOut])
def loans_by_member(member_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Loan)
        .filter(Loan.member_id == member_id)
        .order_by(Loan.loan_id.desc())
        .all()
    )


@router.get("/by-group/{group_id}", response_model=list[LoanListOut])
def loans_by_group(group_id: int, status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Loan).filter(Loan.group_id == group_id)
    if status:
        q = q.filter(Loan.status == status)
    return q.order_by(Loan.loan_id.desc()).all()


@router.get("/collections/by-lo/{lo_id}", response_model=list[CollectionRowOut])
def collections_by_lo(lo_id: int, as_on: date, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
             select l.loan_id,
                    m.member_id,
                    m.full_name                  as member_name,
                    g.group_id,
                    g.group_name,
                    i.due_date,
                    i.installment_no,
                    (i.total_due - i.total_paid) as due_left,
                    l.advance_balance,
                    i.status
             from loans l
                      join members m on m.member_id = l.member_id
                      join groups g on g.group_id = l.group_id
                      join loan_installments i on i.loan_id = l.loan_id
             where l.lo_id = :loid
               and l.status in ('DISBURSED', 'ACTIVE')
               and i.status <> 'PAID'
               and i.due_date <= :as_on
             order by g.group_id, i.due_date, m.full_name
             """),
        {"loid": lo_id, "as_on": as_on},
    ).mappings().all()

    return [
        CollectionRowOut(
            loan_id=r["loan_id"],
            member_id=r["member_id"],
            member_name=r["member_name"],
            group_id=r["group_id"],
            group_name=r["group_name"],
            due_date=r["due_date"],
            installment_no=r["installment_no"],
            due_left=float(r["due_left"]),
            advance_balance=float(r["advance_balance"]),
            status=r["status"],
        )
        for r in rows
    ]


# =================================================
# 🔹 LOAN CREATION
# =================================================

@router.post("", response_model=LoanOut)
def create_loan(payload: LoanCreate, db: Session = Depends(get_db)):
    member = db.execute(
        text("""
             select member_id, group_id, lo_id, branch_id, region_id
             from members
             where member_id = :mid
               and is_active = true
             """),
        {"mid": payload.member_id},
    ).mappings().first()

    if not member:
        raise HTTPException(404, "Member not found / inactive")

    min_weeks = int(get_setting(db, "MIN_WEEKS_BEFORE_CLOSURE", "4"))

    principal = money(payload.principal_amount)
    interest_total = money(payload.flat_interest_total)
    total = principal + interest_total

    installment_amount = (total / payload.duration_weeks).quantize(Decimal("0.01"))

    loan = Loan(
        loan_account_no=payload.loan_account_no,
        member_id=payload.member_id,
        group_id=member["group_id"],
        lo_id=member["lo_id"],
        branch_id=member["branch_id"],
        region_id=member["region_id"],
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
    db.flush()

    principal_week = (principal / payload.duration_weeks).quantize(Decimal("0.01"))
    interest_week = (interest_total / payload.duration_weeks).quantize(Decimal("0.01"))

    due = payload.first_installment_date
    for i in range(1, payload.duration_weeks + 1):
        db.add(LoanInstallment(
            loan_id=loan.loan_id,
            installment_no=i,
            due_date=due,
            principal_due=principal_week,
            interest_due=interest_week,
            total_due=(principal_week + interest_week),
            status="PENDING"
        ))
        due += timedelta(days=7)

    db.add(LoanLedger(
        loan_id=loan.loan_id,
        txn_type="DISBURSEMENT",
        debit=total,
        credit=money(0),
        principal_component=principal,
        interest_component=interest_total,
        balance_outstanding=total,
        narration="Loan disbursed"
    ))

    db.commit()
    db.refresh(loan)
    return loan


# =================================================
# 🔹 DYNAMIC ROUTES (LAST)
# =================================================

@router.get("/{loan_id}/summary", response_model=LoanSummaryOut)
def loan_summary(loan_id: int, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(404, "Loan not found")

    member = db.query(Member).filter(Member.member_id == loan.member_id).first()
    group = db.query(Group).filter(Group.group_id == loan.group_id).first()

    total_paid = db.execute(
        text("""
             select coalesce(sum(credit), 0) as paid
             from loan_ledger
             where loan_id = :lid
               and txn_type = 'PAYMENT'
             """),
        {"lid": loan_id},
    ).mappings().first()["paid"]

    next_inst = (
        db.query(LoanInstallment)
        .filter(LoanInstallment.loan_id == loan_id, LoanInstallment.status != "PAID")
        .order_by(LoanInstallment.installment_no.asc())
        .first()
    )

    return LoanSummaryOut(
        loan_id=loan.loan_id,
        loan_account_no=loan.loan_account_no,
        member_id=loan.member_id,
        member_name=member.full_name if member else "Unknown",
        group_id=loan.group_id,
        group_name=group.group_name if group else "Unknown",
        lo_id=loan.lo_id,
        principal_amount=float(loan.principal_amount),
        interest_amount_total=float(loan.interest_amount_total),
        total_disbursed_amount=float(loan.total_disbursed_amount),
        total_paid=float(total_paid),
        outstanding=float(last_balance(db, loan_id)),
        advance_balance=float(loan.advance_balance),
        status=loan.status,
        next_due_date=next_inst.due_date if next_inst else None,
        next_due_amount=float(next_inst.total_due - next_inst.total_paid) if next_inst else None,
    )
