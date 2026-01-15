from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date

from app.utils.database import get_db

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/cashbook/branch/passbook")
def branch_cashbook_passbook(
    branch_id: int,
    from_date: date = Query(..., description="YYYY-MM-DD"),
    to_date: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    Passbook statement (Installment shown by DUE DATE)
    - Installments: only PAID, but txn_date uses due_date so it appears in the due period
    - Disbursement: debit (real disbursement date)
    - Expenses: debit/credit based on subcategory payment_type
    - Returns running balance (opening + cumulative net)
    """

    rows = db.execute(
        text("""
        WITH txns AS (
          /* 1) EXPENSES */
          SELECT
            be.branch_id,
            be.expense_date::date AS txn_date,
            'EXPENSE'::text AS source,
            CASE WHEN esc.payment_type = 'CREDIT' THEN COALESCE(be.amount,0) ELSE 0 END AS credit,
            CASE WHEN esc.payment_type = 'DEBIT'  THEN COALESCE(be.amount,0) ELSE 0 END AS debit,
            (COALESCE(be.description,'') || CASE WHEN be.payee IS NOT NULL THEN (' | Payee: '||be.payee) ELSE '' END)::text AS remark
          FROM branch_expenses be
          LEFT JOIN expense_subcategories esc
            ON esc.subcategory_id = be.subcategory_id
          WHERE be.branch_id = :bid

          UNION ALL

          /* 2) INSTALLMENTS (PAID only, but shown on DUE DATE) ✅ with Member + Group */
          SELECT
            l.branch_id,
            li.due_date::date AS txn_date,
            'INSTALLMENT'::text AS source,
            COALESCE(li.total_paid, 0) AS credit,
            0::numeric AS debit,
            (
              'Loan '||COALESCE(l.loan_account_no, l.loan_id::text)
              ||' | Inst '||li.installment_no
              ||' | '||m.full_name
              ||' | '||g.group_name
              ||' | PaidOn '||li.paid_date
            )::text AS remark
          FROM loan_installments li
          JOIN loans   l ON l.loan_id = li.loan_id
          JOIN members m ON m.member_id = l.member_id
          JOIN groups  g ON g.group_id  = l.group_id
          WHERE l.branch_id = :bid
            AND li.status = 'PAID'
            AND li.paid_date IS NOT NULL
            AND COALESCE(li.total_paid,0) > 0

          UNION ALL

          /* 3) DISBURSEMENT ✅ with Member + Group */
          SELECT
            l.branch_id,
            l.disburse_date::date AS txn_date,
            'DISBURSEMENT'::text AS source,
            0::numeric AS credit,
            COALESCE(l.total_disbursed_amount, 0) AS debit,
            (
              'Loan '||COALESCE(l.loan_account_no, l.loan_id::text)
              ||' | Disbursement'
              ||' | '||m.full_name
              ||' | '||g.group_name
            )::text AS remark
          FROM loans l
          JOIN members m ON m.member_id = l.member_id
          JOIN groups  g ON g.group_id  = l.group_id
          WHERE l.branch_id = :bid
            AND l.disburse_date IS NOT NULL
            AND COALESCE(l.total_disbursed_amount,0) > 0
        ),
        opening AS (
          SELECT COALESCE(SUM(credit - debit), 0) AS opening_balance
          FROM txns
          WHERE txn_date < :from_date
        ),
        period AS (
          SELECT
            txn_date,
            source,
            credit,
            debit,
            (credit - debit) AS net,
            remark
          FROM txns
          WHERE txn_date BETWEEN :from_date AND :to_date
        )
        SELECT
          p.txn_date,
          p.source,
          p.credit,
          p.debit,
          p.net,
          p.remark,
          (SELECT opening_balance FROM opening)
          + SUM(p.net) OVER (
              ORDER BY p.txn_date ASC, p.source ASC, p.remark ASC
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS running_balance,
          (SELECT opening_balance FROM opening) AS opening_balance
        FROM period p
        ORDER BY p.txn_date ASC, p.source ASC, p.remark ASC;
        """),
        {"bid": branch_id, "from_date": from_date, "to_date": to_date},
    ).mappings().all()

    # Opening balance logic stays same (no need member/group joins)
    opening_row = db.execute(
        text("""
        WITH txns AS (
          SELECT
            be.branch_id,
            be.expense_date::date AS txn_date,
            CASE WHEN esc.payment_type = 'CREDIT' THEN COALESCE(be.amount,0) ELSE 0 END AS credit,
            CASE WHEN esc.payment_type = 'DEBIT'  THEN COALESCE(be.amount,0) ELSE 0 END AS debit
          FROM branch_expenses be
          LEFT JOIN expense_subcategories esc ON esc.subcategory_id = be.subcategory_id
          WHERE be.branch_id = :bid

          UNION ALL

          SELECT
            l.branch_id,
            li.due_date::date AS txn_date,
            COALESCE(li.total_paid, 0) AS credit,
            0::numeric AS debit
          FROM loan_installments li
          JOIN loans l ON l.loan_id = li.loan_id
          WHERE l.branch_id = :bid
            AND li.status='PAID'
            AND li.paid_date IS NOT NULL
            AND COALESCE(li.total_paid,0) > 0

          UNION ALL

          SELECT
            l.branch_id,
            l.disburse_date::date AS txn_date,
            0::numeric AS credit,
            COALESCE(l.total_disbursed_amount, 0) AS debit
          FROM loans l
          WHERE l.branch_id = :bid
            AND l.disburse_date IS NOT NULL
            AND COALESCE(l.total_disbursed_amount,0) > 0
        )
        SELECT COALESCE(SUM(credit - debit), 0) AS opening_balance
        FROM txns
        WHERE txn_date < :from_date;
        """),
        {"bid": branch_id, "from_date": from_date},
    ).mappings().first()

    opening_balance = float(opening_row["opening_balance"] if opening_row else 0)

    return {
        "branch_id": branch_id,
        "from_date": from_date,
        "to_date": to_date,
        "opening_balance": opening_balance,
        "transactions": [
            {
                "txn_date": r["txn_date"],
                "source": r["source"],
                "credit": float(r["credit"]),
                "debit": float(r["debit"]),
                "net": float(r["net"]),
                "running_balance": float(r["running_balance"]),
                "remark": r["remark"],
            }
            for r in rows
        ],
    }


@router.get("/cashbook/group/passbook")
def group_cashbook_passbook(
    group_id: int,
    from_date: date = Query(..., description="YYYY-MM-DD"),
    to_date: date = Query(..., description="YYYY-MM-DD"),
    include_charges: bool = Query(True, description="Include loan charges as CREDIT"),
    db: Session = Depends(get_db),
):
    """
    Group passbook statement (loan-based)
    - Installments: only PAID, txn_date uses due_date (so it appears in due period)
    - Disbursement: debit (real disbursement date)
    - Charges: credit (optional)
    - Running balance = opening + cumulative net
    """

    # --- transactions list (with running balance) ---
    rows = db.execute(
        text("""
        WITH txns AS (
          /* 1) DISBURSEMENT (outflow) */
          SELECT
            l.group_id,
            l.disburse_date::date AS txn_date,
            'DISBURSEMENT'::text AS source,
            0::numeric AS credit,
            COALESCE(l.total_disbursed_amount, 0) AS debit,
            (
              'Loan '||COALESCE(l.loan_account_no, l.loan_id::text)
              ||' | Disbursement'
              ||' | '||m.full_name
              ||' | '||g.group_name
            )::text AS remark
          FROM loans l
          JOIN members m ON m.member_id = l.member_id
          JOIN groups  g ON g.group_id  = l.group_id
          WHERE l.group_id = :gid
            AND l.disburse_date IS NOT NULL
            AND COALESCE(l.total_disbursed_amount,0) > 0

          UNION ALL

          /* 2) INSTALLMENTS (PAID only, shown on DUE DATE) */
          SELECT
            l.group_id,
            li.due_date::date AS txn_date,
            'INSTALLMENT'::text AS source,
            COALESCE(li.total_paid, 0) AS credit,
            0::numeric AS debit,
            (
              'Loan '||COALESCE(l.loan_account_no, l.loan_id::text)
              ||' | Inst '||li.installment_no
              ||' | '||m.full_name
              ||' | '||g.group_name
              ||' | PaidOn '||li.paid_date
            )::text AS remark
          FROM loan_installments li
          JOIN loans   l ON l.loan_id = li.loan_id
          JOIN members m ON m.member_id = l.member_id
          JOIN groups  g ON g.group_id  = l.group_id
          WHERE l.group_id = :gid
            AND li.status = 'PAID'
            AND li.paid_date IS NOT NULL
            AND COALESCE(li.total_paid,0) > 0

          UNION ALL

          /* 3) LOAN CHARGES (income) - optional via include_charges flag */
          SELECT
            l.group_id,
            lc.charge_date::date AS txn_date,
            'CHARGE'::text AS source,
            GREATEST(COALESCE(lc.amount,0) - COALESCE(lc.waived_amount,0), 0) AS credit,
            0::numeric AS debit,
            (
              'Loan '||COALESCE(l.loan_account_no, l.loan_id::text)
              ||' | Charge '||lc.charge_type
              ||' | '||m.full_name
              ||' | '||g.group_name
              || CASE WHEN lc.is_waived THEN (' | Waived '||COALESCE(lc.waived_amount,0)) ELSE '' END
            )::text AS remark
          FROM loan_charges lc
          JOIN loans   l ON l.loan_id = lc.loan_id
          JOIN members m ON m.member_id = l.member_id
          JOIN groups  g ON g.group_id  = l.group_id
          WHERE l.group_id = :gid
            AND :include_charges = true
            AND COALESCE(lc.amount,0) > 0
        ),
        opening AS (
          SELECT COALESCE(SUM(credit - debit), 0) AS opening_balance
          FROM txns
          WHERE txn_date < :from_date
        ),
        period AS (
          SELECT
            txn_date,
            source,
            credit,
            debit,
            (credit - debit) AS net,
            remark
          FROM txns
          WHERE txn_date BETWEEN :from_date AND :to_date
        )
        SELECT
          p.txn_date,
          p.source,
          p.credit,
          p.debit,
          p.net,
          p.remark,
          (SELECT opening_balance FROM opening)
          + SUM(p.net) OVER (
              ORDER BY p.txn_date ASC, p.source ASC, p.remark ASC
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS running_balance,
          (SELECT opening_balance FROM opening) AS opening_balance
        FROM period p
        ORDER BY p.txn_date ASC, p.source ASC, p.remark ASC;
        """),
        {"gid": group_id, "from_date": from_date, "to_date": to_date, "include_charges": include_charges},
    ).mappings().all()

    # --- opening balance only (same logic, no remark needed) ---
    opening_row = db.execute(
        text("""
        WITH txns AS (
          SELECT l.group_id, l.disburse_date::date AS txn_date,
                 0::numeric AS credit, COALESCE(l.total_disbursed_amount,0) AS debit
          FROM loans l
          WHERE l.group_id = :gid
            AND l.disburse_date IS NOT NULL
            AND COALESCE(l.total_disbursed_amount,0) > 0

          UNION ALL

          SELECT l.group_id, li.due_date::date AS txn_date,
                 COALESCE(li.total_paid,0) AS credit, 0::numeric AS debit
          FROM loan_installments li
          JOIN loans l ON l.loan_id = li.loan_id
          WHERE l.group_id = :gid
            AND li.status='PAID'
            AND li.paid_date IS NOT NULL
            AND COALESCE(li.total_paid,0) > 0

          UNION ALL

          SELECT l.group_id, lc.charge_date::date AS txn_date,
                 GREATEST(COALESCE(lc.amount,0) - COALESCE(lc.waived_amount,0), 0) AS credit,
                 0::numeric AS debit
          FROM loan_charges lc
          JOIN loans l ON l.loan_id = lc.loan_id
          WHERE l.group_id = :gid
            AND :include_charges = true
            AND COALESCE(lc.amount,0) > 0
        )
        SELECT COALESCE(SUM(credit - debit), 0) AS opening_balance
        FROM txns
        WHERE txn_date < :from_date;
        """),
        {"gid": group_id, "from_date": from_date, "include_charges": include_charges},
    ).mappings().first()

    opening_balance = float(opening_row["opening_balance"] if opening_row else 0)

    # group name (nice to include in response)
    group_meta = db.execute(
        text("select group_id, group_name, branch_id, lo_id from groups where group_id = :gid"),
        {"gid": group_id},
    ).mappings().first()

    return {
        "group_id": group_id,
        "group_name": group_meta["group_name"] if group_meta else None,
        "branch_id": int(group_meta["branch_id"]) if group_meta and group_meta["branch_id"] is not None else None,
        "lo_id": int(group_meta["lo_id"]) if group_meta and group_meta["lo_id"] is not None else None,
        "from_date": from_date,
        "to_date": to_date,
        "opening_balance": opening_balance,
        "include_charges": include_charges,
        "transactions": [
            {
                "txn_date": r["txn_date"],
                "source": r["source"],
                "credit": float(r["credit"]),
                "debit": float(r["debit"]),
                "net": float(r["net"]),
                "running_balance": float(r["running_balance"]),
                "remark": r["remark"],
            }
            for r in rows
        ],
    }
