from sqlalchemy import (
    Column, Integer, String, DateTime, Numeric, Text, ForeignKey
)
from sqlalchemy.sql import func
from app.utils.database import Base


class LoanLedger(Base):
    __tablename__ = "loan_ledger"

    ledger_id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.loan_id"), nullable=False, index=True)

    txn_date = Column(DateTime, server_default=func.now(), nullable=False)
    txn_type = Column(String(30), nullable=False)  # DISBURSEMENT/PAYMENT/CLOSURE/...

    ref_table = Column(String(50), nullable=True)
    ref_id = Column(Integer, nullable=True)

    debit = Column(Numeric(12, 2), nullable=False, default=0)
    credit = Column(Numeric(12, 2), nullable=False, default=0)

    principal_component = Column(Numeric(12, 2), nullable=False, default=0)
    interest_component = Column(Numeric(12, 2), nullable=False, default=0)

    balance_outstanding = Column(Numeric(12, 2), nullable=False)
    narration = Column(Text, nullable=True)

    created_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    created_on = Column(DateTime, server_default=func.now())
l̥