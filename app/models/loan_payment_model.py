from sqlalchemy import (
    Column, Integer, String, DateTime, Numeric, Text, ForeignKey
)
from sqlalchemy.sql import func
from app.utils.database import Base


class LoanPayment(Base):
    __tablename__ = "loan_payments"

    payment_id = Column(Integer, primary_key=True, index=True)

    loan_id = Column(Integer, ForeignKey("loans.loan_id"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.member_id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("groups.group_id"), nullable=False)
    lo_id = Column(Integer, ForeignKey("loan_officers.lo_id"), nullable=True)

    payment_date = Column(DateTime, server_default=func.now(), nullable=False)
    amount_received = Column(Numeric(12, 2), nullable=False)

    payment_mode = Column(String(20), nullable=False, default="CASH")
    receipt_no = Column(String(50), nullable=True)

    collected_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    remarks = Column(Text, nullable=True)

    created_on = Column(DateTime, server_default=func.now())