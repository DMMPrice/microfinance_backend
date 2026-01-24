# app/models/loan_ledger_model.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Numeric,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.sql import func
from app.utils.database import Base


class LoanLedger(Base):
    __tablename__ = "loan_ledger"

    __table_args__ = (
        Index("ix_loan_ledger_loan_date", "loan_id", "txn_date"),
        Index("ix_loan_ledger_loan_type", "loan_id", "txn_type"),
    )

    ledger_id = Column(Integer, primary_key=True, index=True)

    loan_id = Column(
        Integer,
        ForeignKey("loans.loan_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    txn_date = Column(DateTime, server_default=func.now(), nullable=False)

    # Examples:
    # DISBURSEMENT / PAYMENT / ADVANCE_ADD / ADVANCE_APPLY / CHARGE / PENALTY / WAIVE / ADJUSTMENT
    txn_type = Column(String(30), nullable=False)

    ref_table = Column(String(50), nullable=True)
    ref_id = Column(Integer, nullable=True)

    # ✅ DB-side defaults (important)
    debit = Column(Numeric(12, 2), nullable=False, server_default="0")
    credit = Column(Numeric(12, 2), nullable=False, server_default="0")

    principal_component = Column(Numeric(12, 2), nullable=False, server_default="0")
    interest_component = Column(Numeric(12, 2), nullable=False, server_default="0")

    # should always be set by logic, but keep non-null
    balance_outstanding = Column(Numeric(12, 2), nullable=False)

    narration = Column(Text, nullable=True)

    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_on = Column(DateTime, server_default=func.now(), nullable=True)
