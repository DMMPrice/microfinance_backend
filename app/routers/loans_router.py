# app/routers/loans_router.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from datetime import timedelta, date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.exc import IntegrityError, ProgrammingError
from starlette import status

from app.utils.database import get_db
from app.models.loan_model import Loan
from app.models.loan_installment_model import LoanInstallment
from app.models.loan_payment_model import LoanPayment
from app.models.loan_payment_allocation_model import LoanPaymentAllocation
from app.models.loan_ledger_model import LoanLedger
from app.models.loan_charge_model import LoanCharge
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
    ChargeOut,
    ChargeCollectCreate,
)

from app.utils.loan_calculations import (
    money,
    build_weekly_schedule,
)

router = APIRouter(prefix="/loans", tags=["Loans"])


# -------------------------------------------------
# ✅ NEW: DB Debug Helpers (to catch "different DB" issue)
# -------------------------------------------------
def _db_info(db: Session) -> dict:
    info = db.execute(
        text(
            """
            select
              current_database() as db,
              current_schema() as schema,
              inet_server_addr() as server_ip,
              inet_server_port() as server_port,
              current_user as db_user,
              version() as version,
              current_setting('search_path') as search_path
            """
        )
    ).mappings().first()
    return dict(info or {})


def _table_columns(db: Session, table_name: str, table_schema: str = "public") -> list[str]:
    rows = db.execute(
        text(
            """
            select column_name
            from information_schema.columns
            where table_schema = :schema
              and table_name = :tname
            order by ordinal_position
            """
        ),
        {"schema": table_schema, "tname": table_name},
    ).mappings().all()
    return [r["column_name"] for r in rows]


@router.get("/_db-info")
def loans_db_info(db: Session = Depends(get_db)):
    """
    ✅ Call this once from browser/Postman:
    GET /loans/_db-info

    If this shows a different server_ip/DB than pgAdmin,
    that is why "collected_amount does not exist".
    """
    info = _db_info(db)
    cols = _table_columns(db, "loan_charges", "public")
    return {
        "db_info": info,
        "loan_charges_columns": cols,
        "has_collected_amount": ("collected_amount" in cols),
    }


# -------------------------------------------------
# Settings helpers (single source)
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


def compute_fee_from_setting(db: Session, key: str, principal: Decimal, default_type: str) -> Decimal:
    raw_val = get_setting_str(db, key, "0")
    try:
        val = Decimal(str(raw_val).strip())
    except Exception:
        val = Decimal("0")

    fee_type = get_setting_str(db, f"{key}_TYPE", default_type).strip().upper()

    if fee_type == "PERCENT":
        return money(principal * (val / Decimal("100")))
    return money(val)


def compute_interest_tenure_flat(principal: Decimal, interest_rate_percent: Decimal) -> Decimal:
    return money(principal * interest_rate_percent / Decimal("100"))


def compute_fees_from_settings(db: Session, principal: Decimal):
    insurance_fee = compute_fee_from_setting(db, "INSURANCE_FEES", principal, default_type="PERCENT")
    processing_fee = compute_fee_from_setting(db, "PROCESSING_FEES", principal, default_type="PERCENT")
    book_price = compute_fee_from_setting(db, "BOOK_PRICE", principal, default_type="FIXED")
    fees_total = money(insurance_fee + processing_fee + book_price)
    return insurance_fee, processing_fee, book_price, fees_total


# -------- shared resolver --------
def _resolve_loan(db: Session, loan_id: Optional[int] = None, loan_account_no: Optional[str] = None) -> Loan:
    if loan_id is not None:
        loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    elif loan_account_no:
        loan = db.query(Loan).filter(Loan.loan_account_no == loan_account_no).first()
    else:
        raise HTTPException(status_code=400, detail="Either loan_id or loan_account_no is required")

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


def last_balance(db: Session, loan_id: int) -> Decimal:
    last = (
        db.query(LoanLedger)
        .filter(LoanLedger.loan_id == loan_id)
        .order_by(LoanLedger.ledger_id.desc())
        .first()
    )
    return last.balance_outstanding if last else Decimal("0.00")


def alloc_to_installments(db: Session, loan_id: int, amount: Decimal):
    amount = money(amount)
    allocations = []
    applied_installments = 0
    applied_total = money(0)

    installments = (
        db.query(LoanInstallment)
        .filter(LoanInstallment.loan_id == loan_id, LoanInstallment.status.notin_(["PAID","PAUSED"]))
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
# ✅ INSTALLMENTS DUE (simple list)
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
# ✅ COLLECTION LIST (includes installment_amount)
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
# ✅ LOAN CREATE
# =================================================
@router.post("", response_model=LoanOut)
def create_loan(payload: LoanCreate, db: Session = Depends(get_db)):
    # ✅ NEW: print DB identity + columns from the SAME connection
    try:
        info = _db_info(db)
        cols = _table_columns(db, "loan_charges", "public")
        print("LOANS DB DEBUG =>", info)
        print("loan_charges columns from API =>", cols)
        print("has collected_amount =>", ("collected_amount" in cols))
    except Exception as _e:
        # don't break main logic even if debug fails
        print("DB DEBUG failed:", str(_e))

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

    interest_rate = get_setting_decimal(db, "INTEREST_RATE", "0")
    interest_total = compute_interest_tenure_flat(principal, interest_rate)

    insurance_fee, processing_fee, book_price, _fees_total = compute_fees_from_settings(db, principal)

    total_outstanding = money(principal + interest_total)

    principal_week, interest_week, base_installment, _ = build_weekly_schedule(
        principal=principal,
        interest_total=interest_total,
        duration_weeks=payload.duration_weeks,
        fees_total=money(0),
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
        total_disbursed_amount=total_outstanding,
        installment_amount=base_installment,
        min_weeks_before_closure=min_weeks,
        allow_early_closure=False,
        advance_balance=money(0),
        status="DISBURSED",
    )

    try:
        db.add(loan)
        db.flush()

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

        add_charge("INSURANCE_FEE", insurance_fee, "Insurance fee (manual collection)")
        add_charge("PROCESSING_FEE", processing_fee, "Processing fee (manual collection)")
        add_charge("BOOK_PRICE", book_price, "Book price (manual collection)")

        due = payload.first_installment_date
        for i in range(1, payload.duration_weeks + 1):
            db.add(
                LoanInstallment(
                    loan_id=loan.loan_id,
                    installment_no=i,
                    due_date=due,
                    principal_due=principal_week,
                    interest_due=interest_week,
                    total_due=money(principal_week + interest_week),
                    status="PENDING",
                )
            )
            due += timedelta(days=7)

        db.add(
            LoanLedger(
                loan_id=loan.loan_id,
                txn_type="DISBURSEMENT",
                debit=total_outstanding,
                credit=money(0),
                principal_component=principal,
                interest_component=interest_total,
                balance_outstanding=total_outstanding,
                narration="Loan disbursed",
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

    except ProgrammingError as e:
        db.rollback()
        # ✅ NEW: make the error clearer for this exact issue
        msg = str(getattr(e, "orig", e))
        raise HTTPException(
            status_code=500,
            detail=f"DB ProgrammingError (likely schema mismatch / wrong DB): {msg}",
        )

    except Exception:
        db.rollback()
        raise


# -------------------------------------------------
# ✅ Loan Charges (operations)
# -------------------------------------------------
@router.get("/{loan_id}/charges", response_model=list[ChargeOut])
def get_loan_charges(loan_id: int, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    charges = (
        db.query(LoanCharge)
        .filter(LoanCharge.loan_id == loan_id)
        .order_by(LoanCharge.charge_date.asc(), LoanCharge.charge_id.asc())
        .all()
    )
    return charges


@router.post("/{loan_id}/charges/{charge_id}/collect", status_code=status.HTTP_201_CREATED)
def collect_loan_charge(
    loan_id: int,
    charge_id: int,
    payload: ChargeCollectCreate,
    db: Session = Depends(get_db),
):
    """
    ✅ Collect a specific loan charge and record it properly:
    - Creates a LoanPayment record with purpose=CHARGE linked to charge_id
    - Updates LoanCharge collected_amount / is_collected / receipt_no / payment_mode
    - Adds a LoanLedger entry so it appears in /statement
    """
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    charge = (
        db.query(LoanCharge)
        .filter(LoanCharge.loan_id == loan_id, LoanCharge.charge_id == charge_id)
        .first()
    )
    if not charge:
        raise HTTPException(status_code=404, detail="Charge not found")

    amount_received = money(payload.amount_received)

    # Payable = amount - waived
    payable_total = money(Decimal(charge.amount or 0) - Decimal(charge.waived_amount or 0))
    already_collected = money(Decimal(charge.collected_amount or 0))
    pending = money(payable_total - already_collected)

    if pending <= 0:
        raise HTTPException(status_code=400, detail="Charge already fully collected")

    if amount_received > pending:
        raise HTTPException(
            status_code=400,
            detail=f"Amount exceeds pending charge. Pending: {pending}",
        )

    pay_dt = payload.payment_date or datetime.utcnow()

    # 1) Create payment row
    payment = LoanPayment(
        loan_id=loan.loan_id,
        member_id=loan.member_id,
        group_id=loan.group_id,
        lo_id=loan.lo_id,
        payment_date=pay_dt,
        amount_received=amount_received,
        payment_mode=payload.payment_mode,
        receipt_no=payload.receipt_no,
        collected_by=None,
        remarks=payload.remarks,
        # these fields exist in your model
        payment_purpose="CHARGE",
        charge_id=charge.charge_id,
    )
    db.add(payment)
    db.flush()  # get payment_id

    # 2) Update charge collection fields
    new_collected = money(already_collected + amount_received)
    charge.collected_amount = new_collected
    charge.payment_mode = payload.payment_mode
    charge.receipt_no = payload.receipt_no
    charge.collected_on = pay_dt
    charge.is_collected = bool(new_collected >= payable_total)

    # 3) Add ledger row (statement line)
    # Charges generally do NOT change loan outstanding, so balance stays same.
    last_bal = (
        db.query(LoanLedger.balance_outstanding)
        .filter(LoanLedger.loan_id == loan_id)
        .order_by(LoanLedger.txn_date.desc(), LoanLedger.ledger_id.desc())
        .limit(1)
        .scalar()
    )
    if last_bal is None:
        last_bal = Decimal(loan.total_disbursed_amount or 0)

    ledger = LoanLedger(
        loan_id=loan_id,
        txn_date=pay_dt,
        txn_type="CHARGE_COLLECTION",
        ref_table="loan_charges",
        ref_id=charge.charge_id,
        debit=Decimal("0"),
        credit=amount_received,
        principal_component=Decimal("0"),
        interest_component=Decimal("0"),
        balance_outstanding=last_bal,
        narration=f"Charge collected: {charge.charge_type}",
        created_by=None,
    )
    db.add(ledger)

    db.commit()

    pending_after = money(payable_total - Decimal(charge.collected_amount or 0))
    return {
        "charge_id": charge.charge_id,
        "collected_amount": float(charge.collected_amount or 0),
        "is_collected": bool(charge.is_collected),
        "pending_amount": float(pending_after if pending_after > 0 else 0),
        "payment_id": payment.payment_id,
    }


# -------------------------------------------------
# ✅ Loan Statement (passbook)
# -------------------------------------------------
@router.get("/{loan_id}/statement", response_model=list[LedgerRowOut])
def get_loan_statement(loan_id: int, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    rows = (
        db.query(LoanLedger)
        .filter(LoanLedger.loan_id == loan_id)
        .order_by(LoanLedger.txn_date.asc(), LoanLedger.ledger_id.asc())
        .all()
    )
    return rows


# -------------------------------------------------
# ✅ Loan Summary (overview) - includes charges snapshot
# -------------------------------------------------
@router.get("/{loan_id}/summary", response_model=LoanSummaryOut)
def get_loan_summary(loan_id: int, db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.loan_id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    member = db.query(Member).filter(Member.member_id == loan.member_id).first()
    group = db.query(Group).filter(Group.group_id == loan.group_id).first()

    # Payments total (exclude CHARGE payments from "loan paid" if you want pure EMI; we include only non-CHARGE)
    paid_total = (
        db.query(func.coalesce(func.sum(LoanPayment.amount_received), 0))
        .filter(LoanPayment.loan_id == loan_id)
        .filter(LoanPayment.payment_purpose != "CHARGE")
        .scalar()
    )

    # Outstanding from latest ledger (fallback to loan total)
    outstanding = (
        db.query(LoanLedger.balance_outstanding)
        .filter(LoanLedger.loan_id == loan_id)
        .order_by(LoanLedger.txn_date.desc(), LoanLedger.ledger_id.desc())
        .limit(1)
        .scalar()
    )
    if outstanding is None:
        outstanding = Decimal(loan.total_disbursed_amount or 0)

    # next due
    next_inst = (
        db.query(LoanInstallment)
        .filter(LoanInstallment.loan_id == loan_id)
        .filter(LoanInstallment.status.in_(["PENDING", "OVERDUE"]))
        .order_by(LoanInstallment.due_date.asc(), LoanInstallment.installment_no.asc())
        .first()
    )

    # charges snapshot
    ch = db.query(
        func.coalesce(func.sum(LoanCharge.amount), 0).label("total_charges"),
        func.coalesce(func.sum(LoanCharge.waived_amount), 0).label("total_waived"),
        func.coalesce(func.sum(LoanCharge.collected_amount), 0).label("total_collected"),
        func.coalesce(
            func.sum((LoanCharge.amount - LoanCharge.waived_amount) - LoanCharge.collected_amount),
            0,
        ).label("total_pending"),
    ).filter(LoanCharge.loan_id == loan_id).one()

    return LoanSummaryOut(
        loan_id=loan.loan_id,
        loan_account_no=loan.loan_account_no,
        member_id=loan.member_id,
        member_name=(member.full_name if member else ""),
        group_id=loan.group_id,
        group_name=(group.group_name if group else ""),
        lo_id=loan.lo_id,
        principal_amount=float(loan.principal_amount or 0),
        interest_amount_total=float(loan.interest_amount_total or 0),
        total_disbursed_amount=float(loan.total_disbursed_amount or 0),
        total_paid=float(paid_total or 0),
        outstanding=float(outstanding or 0),
        advance_balance=float(loan.advance_balance or 0),
        status=str(loan.status or ""),
        next_due_date=(next_inst.due_date if next_inst else None),
        next_due_amount=(float(next_inst.total_due) if next_inst else None),
        charges_total=float(ch.total_charges or 0),
        charges_waived=float(ch.total_waived or 0),
        charges_collected=float(ch.total_collected or 0),
        charges_pending=float(ch.total_pending or 0),
    )


# =================================================
# ✅ DEACTIVATE / PAUSE / RESUME (Installment freeze)
#   - When PAUSED/INACTIVE: installments won't appear in collections/due/overdue
#     because those endpoints filter l.status in ('DISBURSED','ACTIVE')
#   - We additionally set unpaid installments to status='PAUSED' for clarity
# =================================================

def _set_unpaid_installments_status(db: Session, loan_id: int, new_status: str) -> int:
    unpaid = (
        db.query(LoanInstallment)
        .filter(
            LoanInstallment.loan_id == loan_id,
            LoanInstallment.status != "PAID",
        )
        .order_by(LoanInstallment.installment_no.asc())
        .all()
    )
    for inst in unpaid:
        inst.status = new_status
    return len(unpaid)


def _resequence_unpaid_installments_weekly(db: Session, loan_id: int, start_due: date) -> int:
    """
    Reassign due_date for unpaid installments sequentially (weekly) starting from start_due.
    Does NOT touch already PAID installments.
    Also resets status from OVERDUE/PAUSED -> PENDING for unpaid items.
    """
    start_due = start_due or date.today()
    due = start_due

    unpaid = (
        db.query(LoanInstallment)
        .filter(LoanInstallment.loan_id == loan_id, LoanInstallment.status != "PAID")
        .order_by(LoanInstallment.installment_no.asc())
        .all()
    )
    for inst in unpaid:
        inst.due_date = due
        inst.status = "PENDING"
        inst.paid_date = None
        due += timedelta(days=7)

    return len(unpaid)


def _reallocate_all_payments_to_installments(db: Session, loan: Loan) -> None:
    """
    When schedule is changed (resume/reinstate), re-map existing INSTALLMENT payments
    to the current installment rows.
    - Clears LoanPaymentAllocation rows
    - Resets installment paid fields
    - Re-applies payments in chronological order (ignores CHARGE payments)
    - Updates loan.advance_balance with any leftover
    """
    # Reset installment paid fields for unpaid installments
    insts = (
        db.query(LoanInstallment)
        .filter(LoanInstallment.loan_id == loan.loan_id)
        .order_by(LoanInstallment.installment_no.asc())
        .all()
    )
    for inst in insts:
        if inst.status == "PAID":
            continue
        inst.principal_paid = money(0)
        inst.interest_paid = money(0)
        inst.total_paid = money(0)
        inst.status = "PENDING"
        inst.paid_date = None

    # Delete allocations for this loan
    payment_ids = [pid for (pid,) in db.query(LoanPayment.payment_id).filter(LoanPayment.loan_id == loan.loan_id).all()]
    if payment_ids:
        allocs = db.query(LoanPaymentAllocation).filter(LoanPaymentAllocation.payment_id.in_(payment_ids)).all()
        for a in allocs:
            db.delete(a)

    # Re-apply payments (non-CHARGE)
    payments = (
        db.query(LoanPayment)
        .filter(
            LoanPayment.loan_id == loan.loan_id,
            LoanPayment.payment_purpose != "CHARGE",
        )
        .order_by(LoanPayment.payment_date.asc(), LoanPayment.payment_id.asc())
        .all()
    )

    advance = money(0)
    for p in payments:
        allocs, remaining, _applied_cnt, _applied_total = alloc_to_installments(db, loan.loan_id, money(p.amount_received))
        for a in allocs:
            db.add(
                LoanPaymentAllocation(
                    payment_id=p.payment_id,
                    installment_id=a["installment_id"],
                    principal_alloc=a["principal_alloc"],
                    interest_alloc=a["interest_alloc"],
                )
            )
        if remaining > 0:
            advance = money(advance + remaining)

    loan.advance_balance = money(advance)


@router.patch("/{loan_id}/deactivate")
def deactivate_loan(
    loan_id: int,
    remarks: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Deactivate a loan:
    - loan.status -> INACTIVE
    - loan.is_active -> false
    - marks unpaid installments as PAUSED
    - hides from collections/due/overdue (because those endpoints filter ACTIVE/DISBURSED)
    """
    loan = _resolve_loan(db, loan_id=loan_id)

    if (loan.status or "").upper() == "CLOSED":
        raise HTTPException(status_code=400, detail="Loan is already CLOSED")

    loan.status = "INACTIVE"
    loan.is_active = False
    loan.deactivated_on = datetime.utcnow()

    count = _set_unpaid_installments_status(db, loan.loan_id, "PAUSED")

    bal = last_balance(db, loan.loan_id)
    db.add(
        LoanLedger(
            loan_id=loan.loan_id,
            txn_type="LOAN_DEACTIVATED",
            debit=money(0),
            credit=money(0),
            principal_component=money(0),
            interest_component=money(0),
            balance_outstanding=bal,
            narration=remarks or "Loan deactivated (installments paused)",
        )
    )

    db.commit()
    return {"loan_id": loan.loan_id, "status": loan.status, "paused_installments": count}


@router.patch("/{loan_id}/pause")
def pause_loan(
    loan_id: int,
    remarks: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Pause a loan temporarily:
    - loan.status -> PAUSED
    - keeps is_active as true
    - marks unpaid installments as PAUSED
    """
    loan = _resolve_loan(db, loan_id=loan_id)

    if (loan.status or "").upper() in ("CLOSED", "CANCELLED"):
        raise HTTPException(status_code=400, detail=f"Cannot pause loan with status {loan.status}")

    loan.status = "PAUSED"
    loan.is_active = True

    count = _set_unpaid_installments_status(db, loan.loan_id, "PAUSED")

    bal = last_balance(db, loan.loan_id)
    db.add(
        LoanLedger(
            loan_id=loan.loan_id,
            txn_type="LOAN_PAUSED",
            debit=money(0),
            credit=money(0),
            principal_component=money(0),
            interest_component=money(0),
            balance_outstanding=bal,
            narration=remarks or "Loan paused (installments frozen)",
        )
    )

    db.commit()
    return {"loan_id": loan.loan_id, "status": loan.status, "paused_installments": count}


@router.patch("/{loan_id}/resume")
def resume_loan(
    loan_id: int,
    resume_from: Optional[date] = Query(None, description="Start due-date for the next unpaid installment"),
    resequence: bool = Query(True, description="If true, resequence unpaid installments weekly from resume_from"),
    reallocate_payments: bool = Query(True, description="If true, re-map previous payments to the new schedule"),
    remarks: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Resume a paused/deactivated loan:
    - loan.status -> ACTIVE
    - loan.is_active -> true
    - reinstates unpaid installments to PENDING
    - optionally resequences due dates from resume_from (weekly)
    - optionally re-allocates existing payments to installments
    """
    loan = _resolve_loan(db, loan_id=loan_id)

    if (loan.status or "").upper() == "CLOSED":
        raise HTTPException(status_code=400, detail="Loan is already CLOSED")

    loan.status = "ACTIVE"
    loan.is_active = True
    loan.deactivated_on = None

    start_due = resume_from or date.today()

    if resequence:
        changed = _resequence_unpaid_installments_weekly(db, loan.loan_id, start_due)
    else:
        changed = _set_unpaid_installments_status(db, loan.loan_id, "PENDING")

    if reallocate_payments:
        _reallocate_all_payments_to_installments(db, loan)

    bal = last_balance(db, loan.loan_id)
    db.add(
        LoanLedger(
            loan_id=loan.loan_id,
            txn_type="LOAN_RESUMED",
            debit=money(0),
            credit=money(0),
            principal_component=money(0),
            interest_component=money(0),
            balance_outstanding=bal,
            narration=remarks or f"Loan resumed (reinstated {changed} installments)",
        )
    )

    db.commit()
    return {
        "loan_id": loan.loan_id,
        "status": loan.status,
        "reinstated_installments": changed,
        "advance_balance": float(loan.advance_balance),
    }


@router.post("/installments/mark-overdue")
def mark_overdue(as_on: Optional[date] = Query(None), db: Session = Depends(get_db)):
    """
    Mark installments as OVERDUE for ACTIVE/DISBURSED loans only.
    Paused/Inactive loans are excluded by loan.status filter.
    """
    as_on = as_on or date.today()

    q = (
        db.query(LoanInstallment)
        .join(Loan, Loan.loan_id == LoanInstallment.loan_id)
        .filter(
            Loan.status.in_(["DISBURSED", "ACTIVE"]),
            LoanInstallment.status == "PENDING",
            LoanInstallment.due_date < as_on,
        )
    )
    rows = q.all()
    for inst in rows:
        inst.status = "OVERDUE"

    db.commit()
    return {"as_on": as_on, "marked_overdue": len(rows)}
