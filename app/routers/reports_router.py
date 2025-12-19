from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date

from app.utils.database import get_db

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/overdue")
def overdue_report(as_on: date, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
             select l.loan_id,
                    l.member_id,
                    m.full_name                  as member_name,
                    l.group_id,
                    g.group_name,
                    l.lo_id,
                    i.installment_no,
                    i.due_date,
                    (i.total_due - i.total_paid) as due_left
             from loan_installments i
                      join loans l on l.loan_id = i.loan_id
                      join members m on m.member_id = l.member_id
                      join groups g on g.group_id = l.group_id
             where i.status <> 'PAID'
               and i.due_date < :as_on
               and l.status in ('DISBURSED', 'ACTIVE')
             order by i.due_date asc
             """),
        {"as_on": as_on},
    ).mappings().all()

    return [
        {
            "loan_id": r["loan_id"],
            "member_id": r["member_id"],
            "member_name": r["member_name"],
            "group_id": r["group_id"],
            "group_name": r["group_name"],
            "lo_id": r["lo_id"],
            "installment_no": r["installment_no"],
            "due_date": r["due_date"],
            "due_left": float(r["due_left"]),
        }
        for r in rows
    ]


@router.get("/portfolio/branch")
def branch_portfolio(branch_id: int, db: Session = Depends(get_db)):
    row = db.execute(
        text("""
             select count(*) filter (where status in ('DISBURSED','ACTIVE')) as active_loans, coalesce(sum(total_disbursed_amount) filter(where status in ('DISBURSED','ACTIVE')), 0) as total_portfolio
             from loans
             where branch_id = :bid
             """),
        {"bid": branch_id},
    ).mappings().first()
    return {
        "branch_id": branch_id,
        "active_loans": int(row["active_loans"]),
        "total_portfolio": float(row["total_portfolio"]),
    }


@router.get("/portfolio/region")
def region_portfolio(region_id: int, db: Session = Depends(get_db)):
    row = db.execute(
        text("""
             select count(*) filter (where status in ('DISBURSED','ACTIVE')) as active_loans, coalesce(sum(total_disbursed_amount) filter(where status in ('DISBURSED','ACTIVE')), 0) as total_portfolio
             from loans
             where region_id = :rid
             """),
        {"rid": region_id},
    ).mappings().first()
    return {
        "region_id": region_id,
        "active_loans": int(row["active_loans"]),
        "total_portfolio": float(row["total_portfolio"]),
    }
