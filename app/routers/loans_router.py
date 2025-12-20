from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import timedelta, date, datetime
from decimal import Decimal
from typing import Optional

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
    LoanMasterRowOut,
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


def alloc_to_installments(db: Session, loan_id: int, amount: Decimal):
    """
    Allocates 'amount' to pending installments in order.
    Returns: (allocations_list, remaining_amount, applied_installments_count, applied_total)

    allocations_list contains dicts:
      - installment_id
      - installment_no
      - applied_amount (Decimal)
    """
    amount = money(amount)
    allocations = []
    applied_installments = 0
    applied_total = money(0)

    installments = (
        db.query(LoanInstallment)
        .filter(LoanInstallment.loan_id == loan_id, LoanInstallment.status != "PAID")
        .order_by(LoanInstallment.installment_no.asc())
        .all()
    )

    for inst in installments:
        if amount <= 0:
            break

        due_left = money(inst.total_due - inst.total_paid)
        if due_left <= 0:
            inst.status = "PAID"
            continue

        apply_amt = due_left if amount >= due_left else amount

        # -------------------------------------------------
        # Split applied amount into principal/interest ratio
        # -------------------------------------------------
        principal_due = money(inst.principal_due)
        interest_due = money(inst.interest_due)
        total_due = money(inst.total_due)

        # Prevent division by zero
        if total_due > 0:
            pr_ratio = principal_due / total_due
            in_ratio = interest_due / total_due
        else:
            pr_ratio = Decimal("0")
            in_ratio = Decimal("0")

        pr_add = money(apply_amt * pr_ratio)
        in_add = money(apply_amt - pr_add)  # remaining to interest

        # Update installment paid
        inst.total_paid = money(inst.total_paid + apply_amt)

        # If your model has principal_paid / interest_paid fields
        if hasattr(inst, "principal_paid") and inst.principal_paid is not None:
            inst.principal_paid = money(inst.principal_paid + pr_add)
        elif hasattr(inst, "principal_paid"):
            inst.principal_paid = pr_add

        if hasattr(inst, "interest_paid") and inst.interest_paid is not None:
            inst.interest_paid = money(inst.interest_paid + in_add)
        elif hasattr(inst, "interest_paid"):
            inst.interest_paid = in_add

        # Status update
        new_due_left = money(inst.total_due - inst.total_paid)
        if new_due_left <= 0:
            inst.status = "PAID"
            if hasattr(inst, "paid_date"):
                inst.paid_date = date.today()
            applied_installments += 1
        else:
            inst.status = "PENDING"  # keep your existing statuses

        allocations.append(
            {
                "installment_id": inst.installment_id,
                "installment_no": inst.installment_no,
                "applied_amount": apply_amt,
            }
        )

        applied_total = money(applied_total + apply_amt)
        amount = money(amount - apply_amt)

    return allocations, amount, applied_installments, applied_total


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
        text(
            """
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
            """
        ),
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
def loans_by_group(
        group_id: int, status: Optional[str] = None, db: Session = Depends(get_db)
):
    q = db.query(Loan).filter(Loan.group_id == group_id)
    if status:
        q = q.filter(Loan.status == status)
    return q.order_by(Loan.loan_id.desc()).all()


@router.get("/collections/by-lo/{lo_id}", response_model=list[CollectionRowOut])
def collections_by_lo(lo_id: int, as_on: date, db: Session = Depends(get_db)):
    rows = db.execute(
        text(
            """
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
            """
        ),
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
# 🔹 MASTER LIST (KEEP THIS ABOVE /{loan_id}/... ROUTES)
# =================================================
@router.get("/master", response_model=list[LoanMasterRowOut])
def loan_master(
        status: Optional[str] = None,
        region_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        lo_id: Optional[int] = None,
        group_id: Optional[int] = None,
        member_id: Optional[int] = None,
        disburse_from: Optional[date] = None,
        disburse_to: Optional[date] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    status_norm = status.upper() if status else None

    sql = text(
        """
        SELECT l.loan_id,
               l.loan_account_no,
               l.member_id,
               m.full_name                                        AS member_name,
               l.group_id,
               g.group_name,
               l.lo_id,
               l.branch_id,
               l.region_id,
               l.product_id,
               l.disburse_date,
               l.first_installment_date,
               l.duration_weeks,
               l.installment_type,
               l.installment_amount,
               l.principal_amount,
               l.interest_amount_total,
               l.total_disbursed_amount,
               COALESCE(paid.total_paid, 0)                       AS total_paid,
               COALESCE(lb.outstanding, l.total_disbursed_amount) AS outstanding,
               l.advance_balance,
               l.status
        FROM loans l
                 JOIN members m ON m.member_id = l.member_id
                 JOIN groups g ON g.group_id = l.group_id

                 LEFT JOIN (SELECT loan_id, COALESCE(SUM(credit), 0) AS total_paid
                            FROM loan_ledger
                            WHERE txn_type = 'PAYMENT'
                            GROUP BY loan_id) paid ON paid.loan_id = l.loan_id

                 LEFT JOIN (SELECT x.loan_id, x.balance_outstanding AS outstanding
                            FROM loan_ledger x
                                     JOIN (SELECT loan_id, MAX(ledger_id) AS max_ledger_id
                                           FROM loan_ledger
                                           GROUP BY loan_id) y
                                          ON y.loan_id = x.loan_id AND y.max_ledger_id = x.ledger_id) lb
                           ON lb.loan_id = l.loan_id

        WHERE 1 = 1
          AND (:status IS NULL OR UPPER(l.status) = :status)
          AND (:region_id IS NULL OR l.region_id = :region_id)
          AND (:branch_id IS NULL OR l.branch_id = :branch_id)
          AND (:lo_id IS NULL OR l.lo_id = :lo_id)
          AND (:group_id IS NULL OR l.group_id = :group_id)
          AND (:member_id IS NULL OR l.member_id = :member_id)
          AND (:disburse_from IS NULL OR l.disburse_date >= :disburse_from)
          AND (:disburse_to IS NULL OR l.disburse_date <= :disburse_to)
          AND (
            :search IS NULL
                OR l.loan_account_no ILIKE :search_like
                OR m.full_name ILIKE :search_like
            )
        ORDER BY l.loan_id DESC LIMIT :limit
        OFFSET :offset
        """
    )

    params = {
        "status": status_norm,
        "region_id": region_id,
        "branch_id": branch_id,
        "lo_id": lo_id,
        "group_id": group_id,
        "member_id": member_id,
        "disburse_from": disburse_from,
        "disburse_to": disburse_to,
        "search": search,
        "search_like": f"%{search}%" if search else None,
        "limit": limit,
        "offset": offset,
    }

    rows = db.execute(sql, params).mappings().all()

    return [
        {
            "loan_id": r["loan_id"],
            "loan_account_no": r["loan_account_no"],
            "member_id": r["member_id"],
            "member_name": r["member_name"],
            "group_id": r["group_id"],
            "group_name": r["group_name"],
            "lo_id": r["lo_id"],
            "branch_id": r["branch_id"],
            "region_id": r["region_id"],
            "product_id": r["product_id"],
            "disburse_date": r["disburse_date"],
            "first_installment_date": r["first_installment_date"],
            "duration_weeks": r["duration_weeks"],
            "installment_type": r["installment_type"],
            "installment_amount": float(r["installment_amount"]),
            "principal_amount": float(r["principal_amount"]),
            "interest_amount_total": float(r["interest_amount_total"]),
            "total_disbursed_amount": float(r["total_disbursed_amount"]),
            "total_paid": float(r["total_paid"]),
            "outstanding": float(r["outstanding"]),
            "advance_balance": float(r["advance_balance"]),
            "status": r["status"],
        }
        for r in rows
    ]


# =================================================
# 🔹 LOAN CREATION
# =================================================
@router.post("", response_model=LoanOut)
def create_loan(payload: LoanCreate, db: Session = Depends(get_db)):
    member = db.execute(
        text(
            """
            select member_id, group_id, lo_id, branch_id, region_id
            from members
            where member_id = :mid
              and is_active = true
            """
        ),
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
        db.add(
            LoanInstallment(
                loan_id=loan.loan_id,
                installment_no=i,
                due_date=due,
                principal_due=principal_week,
                interest_due=interest_week,
                total_due=(principal_week + interest_week),
                status="PENDING",
            )
        )
        due += timedelta(days=7)

    db.add(
        LoanLedger(
            loan_id=loan.loan_id,
            txn_type="DISBURSEMENT",
            debit=total,
            credit=money(0),
            principal_component=principal,
            interest_component=interest_total,
            balance_outstanding=total,
            narration="Loan disbursed",
        )
    )

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
        text(
            """
            select coalesce(sum(credit), 0) as paid
            from loan_ledger
            where loan_id = :lid
              and txn_type = 'PAYMENT'
            """
        ),
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


@router.get("/{loan_id}/schedule", response_model=list[InstallmentOut])
def get_schedule(loan_id: int, db: Session = Depends(get_db)):
    return (
        db.query(LoanInstallment)
        .filter(LoanInstallment.loan_id == loan_id)
        .order_by(LoanInstallment.installment_no.asc())
        .all()
    )


@router.get("/{loan_id}/statement", response_model=list[LedgerRowOut])
def statement(loan_id: int, db: Session = Depends(get_db)):
    return (
        db.query(LoanLedger)
        .filter(LoanLedger.loan_id == loan_id)
        .order_by(LoanLedger.ledger_id.asc())
        .all()
    )


# =================================================
# ✅ PAYMENTS (schema-aligned)
# =================================================
@router.post("/{loan_id}/payments", response_model=PaymentResult)
def create_payment(loan_id: int, payload: PaymentCreate, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(404, "Loan not found")

    if loan.status not in ("DISBURSED", "ACTIVE"):
        raise HTTPException(400, f"Loan status not eligible for payment: {loan.status}")

    pay_amount = money(payload.amount_received)
    if pay_amount <= 0:
        raise HTTPException(400, "Payment amount must be > 0")

    # Allocate to installments
    allocations, remaining, applied_installments, applied_total = alloc_to_installments(
        db=db, loan_id=loan_id, amount=pay_amount
    )

    # Whatever is not used becomes advance
    if remaining > 0:
        loan.advance_balance = money(loan.advance_balance + remaining)

    # Payment date: schema uses datetime; if None use now
    pay_dt: datetime = payload.payment_date or datetime.now()

    # Create payment header (adjust fields based on your model)
    payment = LoanPayment(
        loan_id=loan_id,
        payment_date=pay_dt,
        amount=pay_amount,
        payment_mode=payload.payment_mode,
        receipt_no=payload.receipt_no,
        remarks=payload.remarks,
    )
    db.add(payment)
    db.flush()

    # Create allocation rows
    for a in allocations:
        db.add(
            LoanPaymentAllocation(
                payment_id=payment.payment_id,
                loan_id=loan_id,
                installment_id=a["installment_id"],
                amount=a["applied_amount"],
            )
        )

    # Ledger entry:
    prev_bal = last_balance(db, loan_id)
    new_bal = money(prev_bal - applied_total)

    db.add(
        LoanLedger(
            loan_id=loan_id,
            txn_type="PAYMENT",
            debit=money(0),
            credit=pay_amount,
            principal_component=money(0),
            interest_component=money(0),
            balance_outstanding=new_bal,
            narration=f"Payment received (Receipt: {payload.receipt_no})"
            if payload.receipt_no
            else "Payment received",
        )
    )

    if new_bal <= 0:
        loan.status = "CLOSED"

    db.commit()

    return PaymentResult(
        payment_id=payment.payment_id,
        applied_to_installments=applied_installments,
        advance_added=float(remaining),
        new_advance_balance=float(loan.advance_balance),
    )


# =================================================
# ✅ APPLY ADVANCE (schema-aligned)
# =================================================
@router.post("/{loan_id}/apply-advance", response_model=AdvanceApplyResult)
def apply_advance_balance(loan_id: int, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(404, "Loan not found")

    adv = money(loan.advance_balance)
    if adv <= 0:
        return AdvanceApplyResult(
            applied_installments=0,
            used_advance=0.0,
            remaining_advance=float(loan.advance_balance),
        )

    allocations, remaining, applied_installments, applied_total = alloc_to_installments(
        db=db, loan_id=loan_id, amount=adv
    )

    # reduce advance balance
    loan.advance_balance = remaining

    prev_bal = last_balance(db, loan_id)
    new_bal = money(prev_bal - applied_total)

    db.add(
        LoanLedger(
            loan_id=loan_id,
            txn_type="ADVANCE_APPLY",
            debit=money(0),
            credit=applied_total,
            principal_component=money(0),
            interest_component=money(0),
            balance_outstanding=new_bal,
            narration="Advance applied to installments",
        )
    )

    if new_bal <= 0:
        loan.status = "CLOSED"

    db.commit()

    return AdvanceApplyResult(
        applied_installments=applied_installments,
        used_advance=float(applied_total),
        remaining_advance=float(loan.advance_balance),
    )
