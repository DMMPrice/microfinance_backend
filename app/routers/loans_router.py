from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import timedelta, date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.exc import IntegrityError
from starlette import status

from app.models.loan_charge_model import LoanCharge
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
    LoanUpdate,
    CollectionPaymentCreate,
)

from app.utils.loan_calculations import (
    money,
    compute_interest_total_from_defaults,
    build_weekly_schedule, compute_interest_total_tenure_flat,
)

router = APIRouter(prefix="/loans", tags=["Loans"])


def get_setting_decimal(db: Session, key: str, default: str = "0") -> Decimal:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    val = row.value if row and row.value is not None else default
    try:
        return Decimal(str(val).strip())
    except Exception:
        return Decimal(str(default))


def compute_fees_percent_from_settings(db: Session, principal: Decimal):
    proc_pct = get_setting_decimal(db, "PROCESSING_FEES", "0")  # 3
    ins_pct = get_setting_decimal(db, "INSURANCE_FEES", "0")  # 1
    book_price = money(get_setting_decimal(db, "BOOK_PRICE", "0"))  # 40

    processing_fee = money(principal * proc_pct / Decimal("100"))
    insurance_fee = money(principal * ins_pct / Decimal("100"))
    fees_total = money(processing_fee + insurance_fee + book_price)

    return insurance_fee, processing_fee, book_price, fees_total



# -------- shared resolver --------
def _resolve_loan(
    db: Session,
    loan_id: Optional[int] = None,
    loan_account_no: Optional[str] = None,
) -> Loan:
    if loan_id is not None:
        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    elif loan_account_no:
        loan = db.query(Loan).filter(Loan.loan_account_no == loan_account_no).first()
    else:
        raise HTTPException(
            status_code=400,
            detail="Either loan_id or loan_account_no is required",
        )

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    return loan

# -------------------------------------------------
# Settings helpers
# -------------------------------------------------
def get_setting(db: Session, key: str, default: str) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return row.value if row else default


def compute_fee_from_setting(
        db: Session,
        key: str,
        principal: Decimal,
        default_type: str,
) -> Decimal:
    """
    Reads:
      KEY = number
      KEY_TYPE = PERCENT or FIXED (optional)

    If KEY_TYPE is missing, uses default_type.

    Examples:
      PROCESSING_FEES=3 and PROCESSING_FEES_TYPE=PERCENT => 3% of principal
      BOOK_PRICE=40 and BOOK_PRICE_TYPE=FIXED => 40
    """
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    raw_val = row.value if row and row.value is not None else "0"

    try:
        val = Decimal(str(raw_val).strip())
    except Exception:
        val = Decimal("0")

    type_row = db.query(SystemSetting).filter(SystemSetting.key == f"{key}_TYPE").first()
    fee_type = (type_row.value if type_row and type_row.value else default_type).strip().upper()

    if fee_type == "PERCENT":
        return money(principal * (val / Decimal("100")))

    return money(val)


# -------------------------------------------------
# Settings helpers (add these)
# -------------------------------------------------
def get_setting_str(db: Session, key: str, default: str = "") -> str:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return (row.value or default) if row else default


def get_setting_decimal(db: Session, key: str, default: str = "0") -> Decimal:
    v = get_setting_str(db, key, default)
    try:
        return Decimal(str(v).strip())
    except Exception:
        return Decimal(str(default))


def compute_interest_tenure_flat(principal: Decimal, interest_rate_percent: Decimal) -> Decimal:
    # ✅ FLAT INTEREST FOR FULL LOAN TENURE
    return money(principal * interest_rate_percent / Decimal("100"))


def compute_fees_from_settings(db: Session, principal: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    # ✅ percent fees from settings
    proc_pct = get_setting_decimal(db, "PROCESSING_FEES", "0")  # e.g. 3
    ins_pct = get_setting_decimal(db, "INSURANCE_FEES", "0")  # e.g. 1
    book_price = money(get_setting_decimal(db, "BOOK_PRICE", "0"))  # e.g. 40

    processing_fee = money(principal * proc_pct / Decimal("100"))
    insurance_fee = money(principal * ins_pct / Decimal("100"))
    fees_total = money(processing_fee + insurance_fee + book_price)

    return insurance_fee, processing_fee, book_price, fees_total


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

        principal_left = money(inst.principal_due - (inst.principal_paid or 0))
        interest_left = money(inst.interest_due - (inst.interest_paid or 0))

        in_add = money(min(apply_amt, interest_left))
        rem = money(apply_amt - in_add)
        pr_add = money(min(rem, principal_left))

        inst.total_paid = money(inst.total_paid + apply_amt)
        inst.principal_paid = money((inst.principal_paid or 0) + pr_add)
        inst.interest_paid = money((inst.interest_paid or 0) + in_add)

        new_due_left = money(inst.total_due - inst.total_paid)
        if new_due_left <= 0:
            inst.status = "PAID"
            inst.paid_date = date.today()
            applied_installments += 1
        else:
            inst.status = "PENDING"

        allocations.append(
            {
                "installment_id": inst.installment_id,
                "installment_no": inst.installment_no,
                "applied_amount": apply_amt,
                "principal_alloc": pr_add,
                "interest_alloc": in_add,
            }
        )

        applied_total = money(applied_total + apply_amt)
        amount = money(amount - apply_amt)

    return allocations, amount, applied_installments, applied_total


# =================================================
# 🔹 STATS
# =================================================
@router.get("/stats", response_model=LoanStatsOut)
def loan_stats(db: Session = Depends(get_db)):
    rows = db.execute(text("select status, count(*) as c from loans group by status")).mappings().all()
    out = LoanStatsOut()
    for r in rows:
        s = (r["status"] or "").upper()
        if hasattr(out, s):
            setattr(out, s, r["c"])
        else:
            out.OTHER += r["c"]
    return out


# =================================================
# 🔹 INSTALLMENTS DUE (simple list)
# =================================================
@router.get("/installments/due")
def installments_due(as_on: Optional[date] = Query(None), db: Session = Depends(get_db)):
    sql = """
          select i.installment_id,
                 i.loan_id,
                 l.loan_account_no,
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
            and l.status in ('DISBURSED', 'ACTIVE')
            and m.is_active = true
          """

    params = {}
    if as_on:
        sql += " and i.due_date <= :as_on"
        params["as_on"] = as_on

    sql += " order by i.due_date asc"
    rows = db.execute(text(sql), params).mappings().all()

    return [
        {
            "installment_id": r["installment_id"],
            "loan_id": r["loan_id"],
            "loan_account_no": r["loan_account_no"],
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
    return db.query(Loan).filter(Loan.member_id == member_id).order_by(Loan.loan_id.desc()).all()


@router.get("/by-group/{group_id}", response_model=list[LoanListOut])
def loans_by_group(group_id: int, status_: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Loan).filter(Loan.group_id == group_id)
    if status_:
        q = q.filter(Loan.status == status_)
    return q.order_by(Loan.loan_id.desc()).all()


# =================================================
# ✅ COLLECTION LIST (FIXED + includes installment_amount)
# =================================================
@router.get("/collections/by-lo", response_model=list[CollectionRowOut])
def collections_by_lo(
        lo_id: Optional[int] = Query(None),
        as_on: Optional[date] = Query(None),
        db: Session = Depends(get_db),
):
    sql = """
          select l.loan_id,
                 l.loan_account_no,
                 l.installment_amount,
                 m.member_id,
                 m.full_name                  as member_name,
                 g.group_id,
                 g.group_name,
                 i.due_date,
                 i.installment_no,
                 i.total_due                  as total_due,
                 (i.total_due - i.total_paid) as due_left,
                 l.advance_balance,
                 i.status
          from loans l
                   join members m on m.member_id = l.member_id
                   join groups g on g.group_id = l.group_id
                   join loan_installments i on i.loan_id = l.loan_id
          where l.status in ('DISBURSED', 'ACTIVE')
            and i.status <> 'PAID'
            and m.is_active = true
          """

    params = {}
    if lo_id is not None:
        sql += " and l.lo_id = :loid"
        params["loid"] = lo_id

    if as_on:
        sql += " and i.due_date <= :as_on"
        params["as_on"] = as_on

    sql += " order by g.group_id, i.due_date, m.full_name"

    rows = db.execute(text(sql), params).mappings().all()

    return [
        CollectionRowOut(
            loan_id=r["loan_id"],
            loan_account_no=r["loan_account_no"],
            installment_amount=float(r["installment_amount"]),
            member_id=r["member_id"],
            member_name=r["member_name"],
            group_id=r["group_id"],
            group_name=r["group_name"],
            due_date=r["due_date"],
            installment_no=r["installment_no"],
            total_due=float(r["total_due"]),
            due_left=float(r["due_left"]),
            advance_balance=float(r["advance_balance"]),
            status=r["status"],
        )
        for r in rows
    ]


# =================================================
# 🔹 MASTER LIST
# =================================================
@router.get("/master", response_model=list[LoanMasterRowOut])
def loan_master(
        status_: Optional[str] = None,
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

    status_norm = status_.upper() if status_ else None

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
# ✅ LOAN CREATE (interest computed + fees in first installment)
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

    min_weeks = int(get_setting_str(db, "MIN_WEEKS_BEFORE_CLOSURE", "4"))

    principal = money(payload.principal_amount)

    # ✅ Interest Rate from DB (TENURE FLAT)
    interest_rate = get_setting_decimal(db, "INTEREST_RATE", "0")  # 12.5
    interest_total = compute_interest_tenure_flat(principal, interest_rate)

    # ✅ Fees from DB
    insurance_fee, processing_fee, book_price, fees_total = compute_fees_from_settings(db, principal)

    # ✅ Total outstanding includes interest + fees (fees collected in inst #1)
    total = money(principal + interest_total + fees_total)

    # ✅ weekly base installment excludes fees
    principal_week, interest_week, base_installment, first_extra = build_weekly_schedule(
        principal=principal,
        interest_total=interest_total,
        duration_weeks=payload.duration_weeks,
        fees_total=fees_total,
    )

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
        total_disbursed_amount=total,          # ✅ you intentionally treat this as total outstanding
        installment_amount=base_installment,   # base weekly (without fees)
        min_weeks_before_closure=min_weeks,
        allow_early_closure=False,
        advance_balance=money(0),
        status="DISBURSED",
    )

    try:
        db.add(loan)
        db.flush()  # ✅ loan_id available here

        # =========================================================
        # ✅ NEW: Record charges in loan_charges (for group log/report)
        # =========================================================
        charge_dt = datetime.combine(payload.disburse_date, datetime.min.time())

        def add_charge(charge_type: str, amt: Decimal, remark: str):
            amt = money(amt)
            if amt <= 0:
                return
            db.add(
                LoanCharge(
                    loan_id=loan.loan_id,
                    charge_type=charge_type,
                    charge_date=charge_dt,
                    amount=amt,
                    is_waived=False,
                    waived_amount=money(0),
                    remarks=remark,
                )
            )

        add_charge("INSURANCE_FEE", insurance_fee, "Insurance fee (collected in 1st installment)")
        add_charge("PROCESSING_FEE", processing_fee, "Processing fee (collected in 1st installment)")
        add_charge("BOOK_PRICE", book_price, "Book price (collected in 1st installment)")

        # =========================================================
        # ✅ Installment schedule creation
        # =========================================================
        due = payload.first_installment_date
        for i in range(1, payload.duration_weeks + 1):
            extra = first_extra if i == 1 else money(0)
            total_due = money(base_installment + extra)

            # ✅ Put all fees into interest bucket for first installment (so allocation works)
            inst_interest_due = money(interest_week + extra) if i == 1 else interest_week

            db.add(
                LoanInstallment(
                    loan_id=loan.loan_id,
                    installment_no=i,
                    due_date=due,
                    principal_due=principal_week,
                    interest_due=inst_interest_due,
                    total_due=total_due,
                    status="PENDING",
                )
            )
            due += timedelta(days=7)

        # =========================================================
        # ✅ Ledger entry (your current logic kept)
        # =========================================================
        db.add(
            LoanLedger(
                loan_id=loan.loan_id,
                txn_type="DISBURSEMENT",
                debit=total,
                credit=money(0),
                principal_component=principal,
                interest_component=money(interest_total + fees_total),
                balance_outstanding=total,
                narration=f"Loan disbursed (Fees: ins={insurance_fee}, proc={processing_fee}, book={book_price})",
            )
        )

        db.commit()
        db.refresh(loan)
        return loan

    except IntegrityError as e:
        db.rollback()
        msg = str(getattr(e, "orig", e))
        if "ux_one_active_loan_per_member" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This member already has an active loan. Please close the existing loan before creating a new one.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to create loan due to database constraints.",
        )
    except Exception:
        db.rollback()
        raise


# =================================================
# ✅ LOAN UPDATE (allowed only if no payment exists)
# =================================================
@router.put("/{loan_id}", response_model=LoanOut)
def update_loan(loan_id: int, payload: LoanUpdate, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(404, "Loan not found")

    has_payment = (
            db.query(LoanPayment.payment_id)
            .filter(LoanPayment.loan_id == loan_id)
            .first()
            is not None
    )

    term_fields = {
        "product_id",
        "disburse_date",
        "first_installment_date",
        "duration_weeks",
        "principal_amount",
        "insurance_fee",
        "processing_fee",
        "book_price",
    }
    incoming = payload.model_dump(exclude_unset=True)
    term_change_requested = any(k in incoming for k in term_fields)

    if has_payment and term_change_requested:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot edit loan terms because payments already exist. Only loan_account_no/status can be updated.",
        )

    # ---------------- basic updates ----------------
    if incoming.get("loan_account_no") is not None:
        loan.loan_account_no = str(incoming["loan_account_no"]).strip()

    if incoming.get("status") is not None:
        loan.status = str(incoming["status"]).upper()

    # ---------------- term updates (only if no payments) ----------------
    if (not has_payment) and term_change_requested:
        if incoming.get("product_id") is not None:
            loan.product_id = incoming["product_id"]

        if incoming.get("disburse_date") is not None:
            loan.disburse_date = incoming["disburse_date"]

        if incoming.get("first_installment_date") is not None:
            loan.first_installment_date = incoming["first_installment_date"]

        if incoming.get("duration_weeks") is not None:
            loan.duration_weeks = int(incoming["duration_weeks"])

        if incoming.get("principal_amount") is not None:
            loan.principal_amount = money(incoming["principal_amount"])

        # ✅ principal after potential update
        principal = money(loan.principal_amount)

        # ✅ Fees: override if provided; else compute from settings
        insurance_fee = money(incoming["insurance_fee"]) if incoming.get("insurance_fee") is not None else None
        processing_fee = money(incoming["processing_fee"]) if incoming.get("processing_fee") is not None else None
        book_price = money(incoming["book_price"]) if incoming.get("book_price") is not None else None

        if insurance_fee is None:
            insurance_fee = compute_fee_from_setting(db, "INSURANCE_FEES", principal, default_type="PERCENT")
        if processing_fee is None:
            processing_fee = compute_fee_from_setting(db, "PROCESSING_FEES", principal, default_type="PERCENT")
        if book_price is None:
            book_price = compute_fee_from_setting(db, "BOOK_PRICE", principal, default_type="FIXED")

        fees_total = money(insurance_fee + processing_fee + book_price)

        # ✅ Interest Rate from settings
        interest_rate = Decimal(get_setting(db, "INTEREST_RATE", "0"))

        # ✅ TENURE-FLAT interest (matches 538.04 base for 22,000 @12.5% over 46 weeks)
        interest_total = compute_interest_total_tenure_flat(
            principal=principal,
            interest_rate_percent=interest_rate,
        )

        # (If you want ANNUAL prorated by weeks instead, use this and comment the flat line above)
        # week_divider = Decimal(get_setting(db, "INTEREST_WEEK_DIVIDER", "52"))
        # interest_total = compute_interest_total_from_defaults(
        #     principal=principal,
        #     interest_rate_percent=interest_rate,
        #     week_divider=week_divider,
        #     duration_weeks=loan.duration_weeks,
        # )

        loan.interest_amount_total = interest_total

        # ✅ base weekly installment excludes fees; fees collected only in installment #1
        principal_week, interest_week, base_installment, first_extra = build_weekly_schedule(
            principal=principal,
            interest_total=interest_total,
            duration_weeks=loan.duration_weeks,
            fees_total=fees_total,
        )

        loan.installment_amount = base_installment
        loan.total_disbursed_amount = money(principal + interest_total + fees_total)

        # ---------------- recreate schedule ----------------
        db.query(LoanInstallment).filter(LoanInstallment.loan_id == loan_id).delete(synchronize_session=False)

        due = loan.first_installment_date
        for i in range(1, loan.duration_weeks + 1):
            extra = first_extra if i == 1 else money(0)
            total_due = money(base_installment + extra)

            # ✅ fees go into interest_due for first installment (keeps allocation correct)
            inst_interest_due = money(interest_week + extra) if i == 1 else interest_week

            db.add(
                LoanInstallment(
                    loan_id=loan.loan_id,
                    installment_no=i,
                    due_date=due,
                    principal_due=principal_week,
                    interest_due=inst_interest_due,
                    total_due=total_due,
                    status="PENDING",
                )
            )
            due += timedelta(days=7)

        # ---------------- reset ledger (since no payments) ----------------
        db.query(LoanLedger).filter(LoanLedger.loan_id == loan_id).delete(synchronize_session=False)
        total = money(loan.total_disbursed_amount)

        db.add(
            LoanLedger(
                loan_id=loan.loan_id,
                txn_type="DISBURSEMENT",
                debit=total,
                credit=money(0),
                principal_component=principal,
                # outstanding includes fees, so keep them in interest_component bucket
                interest_component=money(interest_total + fees_total),
                balance_outstanding=total,
                narration=(
                    f"Loan disbursed (updated terms) "
                    f"(Fees: ins={insurance_fee}, proc={processing_fee}, book={book_price})"
                ),
            )
        )

        if loan.status not in ("DISBURSED", "ACTIVE", "CLOSED", "CANCELLED", "INACTIVE"):
            loan.status = "DISBURSED"

    try:
        db.commit()
        db.refresh(loan)
        return loan

    except IntegrityError as e:
        db.rollback()
        msg = str(getattr(e, "orig", e))
        if "loan_account_no" in msg or "unique" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Loan account number already exists.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to update loan due to database constraints.",
        )


# =================================================
# ✅ LOAN DEACTIVATE (soft delete)
# =================================================
@router.patch("/{loan_id}/deactivate", response_model=LoanOut)
def deactivate_loan(loan_id: int, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(404, "Loan not found")

    # block if payments exist (optional rule)
    has_payment = db.query(LoanPayment.payment_id).filter(LoanPayment.loan_id == loan_id).first() is not None
    if has_payment:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot deactivate loan because payments exist. Close the loan instead.",
        )

    loan.status = "INACTIVE"
    db.commit()
    db.refresh(loan)
    return loan


# =================================================
# 🔹 SUMMARY / SCHEDULE / STATEMENT
# =================================================
@router.get("/{loan_id}/summary", response_model=LoanSummaryOut)
def loan_summary_by_id(loan_id: int, db: Session = Depends(get_db)):
    loan = _resolve_loan(db, loan_id=loan_id)

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
        {"lid": loan.loan_id},
    ).mappings().first()["paid"]

    next_inst = (
        db.query(LoanInstallment)
        .filter(LoanInstallment.loan_id == loan.loan_id, LoanInstallment.status != "PAID")
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
        outstanding=float(last_balance(db, loan.loan_id)),
        advance_balance=float(loan.advance_balance),
        status=loan.status,
        next_due_date=next_inst.due_date if next_inst else None,
        next_due_amount=float(next_inst.total_due - next_inst.total_paid) if next_inst else None,
    )


@router.get("/by-account/{loan_account_no}/summary", response_model=LoanSummaryOut)
def loan_summary_by_account(loan_account_no: str, db: Session = Depends(get_db)):
    loan = _resolve_loan(db, loan_account_no=loan_account_no)
    # reuse the same logic by calling the id version
    return loan_summary_by_id(loan.loan_id, db)


# ========================= SCHEDULE =========================
@router.get("/{loan_id}/schedule", response_model=list[InstallmentOut])
def get_schedule_by_id(loan_id: int, db: Session = Depends(get_db)):
    loan = _resolve_loan(db, loan_id=loan_id)
    return (
        db.query(LoanInstallment)
        .filter(LoanInstallment.loan_id == loan.loan_id)
        .order_by(LoanInstallment.installment_no.asc())
        .all()
    )


@router.get("/by-account/{loan_account_no}/schedule", response_model=list[InstallmentOut])
def get_schedule_by_account(loan_account_no: str, db: Session = Depends(get_db)):
    loan = _resolve_loan(db, loan_account_no=loan_account_no)
    return get_schedule_by_id(loan.loan_id, db)


# ========================= STATEMENT =========================
@router.get("/{loan_id}/statement", response_model=list[LedgerRowOut])
def statement_by_id(loan_id: int, db: Session = Depends(get_db)):
    loan = _resolve_loan(db, loan_id=loan_id)
    return (
        db.query(LoanLedger)
        .filter(LoanLedger.loan_id == loan.loan_id)
        .order_by(LoanLedger.ledger_id.asc())
        .all()
    )


@router.get("/by-account/{loan_account_no}/statement", response_model=list[LedgerRowOut])
def statement_by_account(loan_account_no: str, db: Session = Depends(get_db)):
    loan = _resolve_loan(db, loan_account_no=loan_account_no)
    return statement_by_id(loan.loan_id, db)


# =================================================
# ✅ PAYMENTS (used by collection)
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

    allocations, remaining, applied_installments, applied_total = alloc_to_installments(
        db=db, loan_id=loan_id, amount=pay_amount
    )

    if remaining > 0:
        loan.advance_balance = money(loan.advance_balance + remaining)

    pay_dt: datetime = payload.payment_date or datetime.now()

    total_principal = money(sum((a["principal_alloc"] for a in allocations), Decimal("0")))
    total_interest = money(sum((a["interest_alloc"] for a in allocations), Decimal("0")))

    payment = LoanPayment(
        loan_id=loan_id,
        member_id=loan.member_id,
        group_id=loan.group_id,
        lo_id=loan.lo_id,
        payment_date=pay_dt,
        amount_received=pay_amount,
        payment_mode=payload.payment_mode,
        receipt_no=payload.receipt_no,
        collected_by=None,
        remarks=payload.remarks,
    )
    db.add(payment)
    db.flush()

    for a in allocations:
        db.add(
            LoanPaymentAllocation(
                payment_id=payment.payment_id,
                installment_id=a["installment_id"],
                principal_alloc=a["principal_alloc"],
                interest_alloc=a["interest_alloc"],
            )
        )

    prev_bal = last_balance(db, loan_id)
    new_bal = money(prev_bal - applied_total)

    db.add(
        LoanLedger(
            loan_id=loan_id,
            txn_type="PAYMENT",
            debit=money(0),
            credit=applied_total,
            principal_component=total_principal,
            interest_component=total_interest,
            balance_outstanding=new_bal,
            narration=f"Payment received (Receipt: {payload.receipt_no})" if payload.receipt_no else "Payment received",
        )
    )

    if remaining > 0:
        db.add(
            LoanLedger(
                loan_id=loan_id,
                txn_type="ADVANCE_ADD",
                debit=money(0),
                credit=remaining,
                principal_component=money(0),
                interest_component=money(0),
                balance_outstanding=new_bal,
                narration="Excess payment added as advance",
            )
        )

    if new_bal <= 0:
        loan.status = "CLOSED"
    elif loan.status == "DISBURSED" and applied_total > 0:
        loan.status = "ACTIVE"

    db.commit()

    return PaymentResult(
        payment_id=payment.payment_id,
        applied_to_installments=applied_installments,
        advance_added=float(remaining),
        new_advance_balance=float(loan.advance_balance),
    )


# =================================================
# ✅ COLLECTION ENTRY (shortcut API for UI)
# =================================================
@router.post("/collections/entry", response_model=PaymentResult)
def collection_entry(payload: CollectionPaymentCreate, db: Session = Depends(get_db)):
    payment_payload = PaymentCreate(
        payment_date=payload.payment_date,
        amount_received=payload.amount_received,
        payment_mode=payload.payment_mode,
        receipt_no=payload.receipt_no,
        remarks=payload.remarks,
    )
    return create_payment(loan_id=payload.loan_id, payload=payment_payload, db=db)


# =================================================
# ✅ APPLY ADVANCE (only once – removed duplicate)
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

    loan.advance_balance = remaining

    total_principal = money(sum((a["principal_alloc"] for a in allocations), Decimal("0")))
    total_interest = money(sum((a["interest_alloc"] for a in allocations), Decimal("0")))

    prev_bal = last_balance(db, loan_id)
    new_bal = money(prev_bal - applied_total)

    db.add(
        LoanLedger(
            loan_id=loan_id,
            txn_type="ADVANCE_APPLY",
            debit=money(0),
            credit=applied_total,
            principal_component=total_principal,
            interest_component=total_interest,
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
