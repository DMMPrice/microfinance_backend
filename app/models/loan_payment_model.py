# app/models/loan_payment_model.py

from sqlalchemy import (
    Column, Integer, String, DateTime, Numeric, Text, ForeignKey, Index
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base


class LoanPayment(Base):
    __tablename__ = "loan_payments"

    __table_args__ = (
        Index("ix_loan_payments_loan_date", "loan_id", "payment_date"),
        Index("ix_loan_payments_purpose", "payment_purpose"),
        Index("ix_loan_payments_charge_id", "charge_id"),
    )

    payment_id = Column(Integer, primary_key=True, index=True)

    loan_id = Column(
        Integer,
        ForeignKey("loans.loan_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    member_id = Column(Integer, ForeignKey("members.member_id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("groups.group_id"), nullable=False)
    lo_id = Column(Integer, ForeignKey("loan_officers.lo_id"), nullable=True)

    payment_date = Column(DateTime, server_default=func.now(), nullable=False)
    amount_received = Column(Numeric(12, 2), nullable=False)

    payment_mode = Column(String(20), nullable=False, server_default="CASH")
    receipt_no = Column(String(50), nullable=True)

    collected_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    remarks = Column(Text, nullable=True)

    # ✅ INSTALLMENT / ADVANCE / CHARGE
    payment_purpose = Column(String(20), nullable=False, server_default="INSTALLMENT")

    # ✅ keep payment record even if charge row removed later
    charge_id = Column(
        Integer,
        ForeignKey("loan_charges.charge_id", ondelete="SET NULL"),
        nullable=True,
    )

    created_on = Column(DateTime, server_default=func.now())

    # ---------------- relationships (optional but helpful) ----------------
    charge = relationship("LoanCharge", foreign_keys=[charge_id])

    # If you want easy access to allocations from payment side
    allocations = relationship(
        "LoanPaymentAllocation",
        backref="payment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
