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

@router.get("/admin/regions-branches")
def admin_regions_branches(db: Session = Depends(get_db)):
    """
    Admin/SuperAdmin report:
    Returns all regions and their branches in nested format.
    (No filters, master list)
    """

    rows = db.execute(
        text("""
            SELECT
                r.region_id,
                r.region_name,
                b.branch_id,
                b.branch_name
            FROM regions r
            LEFT JOIN branches b ON b.region_id = r.region_id
            ORDER BY r.region_name ASC, b.branch_name ASC
        """)
    ).mappings().all()

    # Convert into nested JSON
    regions = {}
    for row in rows:
        rid = row["region_id"]

        if rid not in regions:
            regions[rid] = {
                "region_id": rid,
                "region_name": row["region_name"],
                "branches": []
            }

        if row["branch_id"] is not None:
            regions[rid]["branches"].append({
                "branch_id": row["branch_id"],
                "branch_name": row["branch_name"]
            })

    return {"regions": list(regions.values())}

@router.get("/admin/regions-branches/stats")
def admin_regions_branches_stats(db: Session = Depends(get_db)):
    """
    Admin/SuperAdmin report:
    Regions + branches with basic portfolio stats
    """

    rows = db.execute(
        text("""
            WITH loan_stats AS (
                SELECT
                    branch_id,
                    COUNT(*) FILTER (WHERE status IN ('DISBURSED','ACTIVE')) AS active_loans,
                    COALESCE(SUM(total_disbursed_amount) FILTER (WHERE status IN ('DISBURSED','ACTIVE')), 0) AS portfolio
                FROM loans
                GROUP BY branch_id
            )
            SELECT
                r.region_id,
                r.region_name,
                b.branch_id,
                b.branch_name,
                COALESCE(ls.active_loans, 0) AS active_loans,
                COALESCE(ls.portfolio, 0) AS portfolio
            FROM regions r
            LEFT JOIN branches b ON b.region_id = r.region_id
            LEFT JOIN loan_stats ls ON ls.branch_id = b.branch_id
            ORDER BY r.region_name ASC, b.branch_name ASC
        """)
    ).mappings().all()

    regions = {}
    for row in rows:
        rid = row["region_id"]

        if rid not in regions:
            regions[rid] = {
                "region_id": rid,
                "region_name": row["region_name"],
                "branches": []
            }

        if row["branch_id"] is not None:
            regions[rid]["branches"].append({
                "branch_id": row["branch_id"],
                "branch_name": row["branch_name"],
                "active_loans": int(row["active_loans"]),
                "portfolio": float(row["portfolio"])
            })

    return {"regions": list(regions.values())}

@router.get("/admin/txns")
def admin_transaction_log(
    from_date: date = Query(...),
    to_date: date = Query(...),
    region_id: int | None = Query(None),
    branch_id: int | None = Query(None),
    group_id: int | None = Query(None),
    source: str | None = Query(None, description="EXPENSE / INSTALLMENT / DISBURSEMENT / CHARGE"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Admin audit-style transaction log (NO running balance).
    Shows all txns with full metadata and filters.
    """

    rows = db.execute(
        text("""
        WITH txns AS (
          /* EXPENSE */
          SELECT
            be.expense_date::date AS txn_date,
            'EXPENSE'::text AS source,
            b.branch_id,
            b.branch_name,
            r.region_id,
            r.region_name,
            NULL::int AS group_id,
            NULL::text AS group_name,
            NULL::int AS loan_id,
            NULL::text AS loan_account_no,
            NULL::int AS member_id,
            NULL::text AS member_name,
            CASE WHEN esc.payment_type='CREDIT' THEN COALESCE(be.amount,0) ELSE 0 END AS credit,
            CASE WHEN esc.payment_type='DEBIT'  THEN COALESCE(be.amount,0) ELSE 0 END AS debit,
            (COALESCE(be.description,'') || CASE WHEN be.payee IS NOT NULL THEN (' | Payee: '||be.payee) ELSE '' END)::text AS remark
          FROM branch_expenses be
          JOIN branches b ON b.branch_id = be.branch_id
          LEFT JOIN regions r ON r.region_id = b.region_id
          LEFT JOIN expense_subcategories esc ON esc.subcategory_id = be.subcategory_id

          UNION ALL

          /* DISBURSEMENT */
          SELECT
            l.disburse_date::date AS txn_date,
            'DISBURSEMENT'::text AS source,
            b.branch_id,
            b.branch_name,
            r.region_id,
            r.region_name,
            g.group_id,
            g.group_name,
            l.loan_id,
            l.loan_account_no,
            m.member_id,
            m.full_name AS member_name,
            0::numeric AS credit,
            COALESCE(l.total_disbursed_amount,0) AS debit,
            ('Loan '||COALESCE(l.loan_account_no, l.loan_id::text)||' | Disbursement')::text AS remark
          FROM loans l
          JOIN members m ON m.member_id = l.member_id
          JOIN groups g ON g.group_id = l.group_id
          JOIN branches b ON b.branch_id = l.branch_id
          LEFT JOIN regions r ON r.region_id = b.region_id
          WHERE l.disburse_date IS NOT NULL
            AND COALESCE(l.total_disbursed_amount,0) > 0

          UNION ALL

          /* INSTALLMENT (PAID) — shown on DUE DATE (your rule) */
          SELECT
            li.due_date::date AS txn_date,
            'INSTALLMENT'::text AS source,
            b.branch_id,
            b.branch_name,
            r.region_id,
            r.region_name,
            g.group_id,
            g.group_name,
            l.loan_id,
            l.loan_account_no,
            m.member_id,
            m.full_name AS member_name,
            COALESCE(li.total_paid,0) AS credit,
            0::numeric AS debit,
            ('Inst '||li.installment_no||' | PaidOn '||li.paid_date)::text AS remark
          FROM loan_installments li
          JOIN loans l ON l.loan_id = li.loan_id
          JOIN members m ON m.member_id = l.member_id
          JOIN groups g ON g.group_id = l.group_id
          JOIN branches b ON b.branch_id = l.branch_id
          LEFT JOIN regions r ON r.region_id = b.region_id
          WHERE li.status='PAID'
            AND li.paid_date IS NOT NULL
            AND COALESCE(li.total_paid,0) > 0

          UNION ALL

          /* CHARGES */
          SELECT
            lc.charge_date::date AS txn_date,
            'CHARGE'::text AS source,
            b.branch_id,
            b.branch_name,
            r.region_id,
            r.region_name,
            g.group_id,
            g.group_name,
            l.loan_id,
            l.loan_account_no,
            m.member_id,
            m.full_name AS member_name,
            GREATEST(COALESCE(lc.amount,0) - COALESCE(lc.waived_amount,0), 0) AS credit,
            0::numeric AS debit,
            ('Charge '||lc.charge_type)::text AS remark
          FROM loan_charges lc
          JOIN loans l ON l.loan_id = lc.loan_id
          JOIN members m ON m.member_id = l.member_id
          JOIN groups g ON g.group_id = l.group_id
          JOIN branches b ON b.branch_id = l.branch_id
          LEFT JOIN regions r ON r.region_id = b.region_id
          WHERE COALESCE(lc.amount,0) > 0
        )
        SELECT *
        FROM txns
        WHERE txn_date BETWEEN :from_date AND :to_date
          AND (:region_id IS NULL OR region_id = :region_id)
          AND (:branch_id IS NULL OR branch_id = :branch_id)
          AND (:group_id  IS NULL OR group_id  = :group_id)
          AND (:source    IS NULL OR source    = :source)
        ORDER BY txn_date ASC, source ASC, remark ASC
        LIMIT :limit OFFSET :offset
        """),
        {
            "from_date": from_date,
            "to_date": to_date,
            "region_id": region_id,
            "branch_id": branch_id,
            "group_id": group_id,
            "source": source.upper() if source else None,
            "limit": limit,
            "offset": offset,
        },
    ).mappings().all()

    return {
        "from_date": from_date,
        "to_date": to_date,
        "filters": {"region_id": region_id, "branch_id": branch_id, "group_id": group_id, "source": source},
        "limit": limit,
        "offset": offset,
        "rows": [
            {
                "txn_date": r["txn_date"],
                "source": r["source"],
                "region_id": r["region_id"],
                "region_name": r["region_name"],
                "branch_id": r["branch_id"],
                "branch_name": r["branch_name"],
                "group_id": r["group_id"],
                "group_name": r["group_name"],
                "loan_id": r["loan_id"],
                "loan_account_no": r["loan_account_no"],
                "member_id": r["member_id"],
                "member_name": r["member_name"],
                "credit": float(r["credit"]),
                "debit": float(r["debit"]),
                "remark": r["remark"],
            }
            for r in rows
        ],
    }

@router.get("/admin/passbook")
def admin_passbook(
    from_date: date = Query(...),
    to_date: date = Query(...),
    region_id: int | None = Query(None),
    branch_id: int | None = Query(None),
    group_id: int | None = Query(None),
    include_charges: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Admin passbook with running balance across filtered scope.
    (If no filters -> whole company passbook)
    """

    rows = db.execute(
        text("""
        WITH txns AS (
          /* EXPENSES */
          SELECT
            be.expense_date::date AS txn_date,
            'EXPENSE'::text AS source,
            b.branch_id, b.branch_name,
            r.region_id, r.region_name,
            NULL::int AS group_id, NULL::text AS group_name,
            CASE WHEN esc.payment_type='CREDIT' THEN COALESCE(be.amount,0) ELSE 0 END AS credit,
            CASE WHEN esc.payment_type='DEBIT'  THEN COALESCE(be.amount,0) ELSE 0 END AS debit,
            (COALESCE(be.description,'') || CASE WHEN be.payee IS NOT NULL THEN (' | Payee: '||be.payee) ELSE '' END)::text AS remark
          FROM branch_expenses be
          JOIN branches b ON b.branch_id = be.branch_id
          LEFT JOIN regions r ON r.region_id = b.region_id
          LEFT JOIN expense_subcategories esc ON esc.subcategory_id = be.subcategory_id

          UNION ALL

          /* INSTALLMENTS (PAID, on DUE DATE) */
          SELECT
            li.due_date::date AS txn_date,
            'INSTALLMENT'::text AS source,
            b.branch_id, b.branch_name,
            r.region_id, r.region_name,
            g.group_id, g.group_name,
            COALESCE(li.total_paid,0) AS credit,
            0::numeric AS debit,
            ('Loan '||COALESCE(l.loan_account_no,l.loan_id::text)
              ||' | Inst '||li.installment_no
              ||' | '||m.full_name
              ||' | PaidOn '||li.paid_date)::text AS remark
          FROM loan_installments li
          JOIN loans l ON l.loan_id = li.loan_id
          JOIN members m ON m.member_id = l.member_id
          JOIN groups g ON g.group_id = l.group_id
          JOIN branches b ON b.branch_id = l.branch_id
          LEFT JOIN regions r ON r.region_id = b.region_id
          WHERE li.status='PAID'
            AND li.paid_date IS NOT NULL
            AND COALESCE(li.total_paid,0) > 0

          UNION ALL

          /* DISBURSEMENT */
          SELECT
            l.disburse_date::date AS txn_date,
            'DISBURSEMENT'::text AS source,
            b.branch_id, b.branch_name,
            r.region_id, r.region_name,
            g.group_id, g.group_name,
            0::numeric AS credit,
            COALESCE(l.total_disbursed_amount,0) AS debit,
            ('Loan '||COALESCE(l.loan_account_no,l.loan_id::text)
              ||' | Disbursement'
              ||' | '||m.full_name)::text AS remark
          FROM loans l
          JOIN members m ON m.member_id = l.member_id
          JOIN groups g ON g.group_id = l.group_id
          JOIN branches b ON b.branch_id = l.branch_id
          LEFT JOIN regions r ON r.region_id = b.region_id
          WHERE l.disburse_date IS NOT NULL
            AND COALESCE(l.total_disbursed_amount,0) > 0

          UNION ALL

          /* CHARGES (optional) */
          SELECT
            lc.charge_date::date AS txn_date,
            'CHARGE'::text AS source,
            b.branch_id, b.branch_name,
            r.region_id, r.region_name,
            g.group_id, g.group_name,
            GREATEST(COALESCE(lc.amount,0) - COALESCE(lc.waived_amount,0), 0) AS credit,
            0::numeric AS debit,
            ('Loan '||COALESCE(l.loan_account_no,l.loan_id::text)
              ||' | Charge '||lc.charge_type
              ||' | '||m.full_name)::text AS remark
          FROM loan_charges lc
          JOIN loans l ON l.loan_id = lc.loan_id
          JOIN members m ON m.member_id = l.member_id
          JOIN groups g ON g.group_id = l.group_id
          JOIN branches b ON b.branch_id = l.branch_id
          LEFT JOIN regions r ON r.region_id = b.region_id
          WHERE :include_charges = true
            AND COALESCE(lc.amount,0) > 0
        ),
        scoped AS (
          SELECT *
          FROM txns
          WHERE (:region_id IS NULL OR region_id = :region_id)
            AND (:branch_id IS NULL OR branch_id = :branch_id)
            AND (:group_id  IS NULL OR group_id  = :group_id)
        ),
        opening AS (
          SELECT COALESCE(SUM(credit - debit), 0) AS opening_balance
          FROM scoped
          WHERE txn_date < :from_date
        ),
        period AS (
          SELECT *, (credit - debit) AS net
          FROM scoped
          WHERE txn_date BETWEEN :from_date AND :to_date
        )
        SELECT
          p.*,
          (SELECT opening_balance FROM opening)
          + SUM(p.net) OVER (ORDER BY p.txn_date, p.source, p.remark
                             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_balance,
          (SELECT opening_balance FROM opening) AS opening_balance
        FROM period p
        ORDER BY p.txn_date, p.source, p.remark
        """),
        {
            "from_date": from_date,
            "to_date": to_date,
            "region_id": region_id,
            "branch_id": branch_id,
            "group_id": group_id,
            "include_charges": include_charges,
        }
    ).mappings().all()

    opening_balance = float(rows[0]["opening_balance"]) if rows else 0.0

    return {
        "from_date": from_date,
        "to_date": to_date,
        "filters": {"region_id": region_id, "branch_id": branch_id, "group_id": group_id},
        "opening_balance": opening_balance,
        "transactions": [
            {
                "txn_date": r["txn_date"],
                "source": r["source"],
                "region_id": r["region_id"],
                "region_name": r["region_name"],
                "branch_id": r["branch_id"],
                "branch_name": r["branch_name"],
                "group_id": r["group_id"],
                "group_name": r["group_name"],
                "credit": float(r["credit"]),
                "debit": float(r["debit"]),
                "net": float(r["credit"] - r["debit"]),
                "running_balance": float(r["running_balance"]),
                "remark": r["remark"],
            }
            for r in rows
        ],
    }
