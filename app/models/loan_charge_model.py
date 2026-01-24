# app/models/loan_charge_model.py
from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.orm import relationship

from app.utils.database import Base


class LoanCharge(Base):
    __tablename__ = "loan_charges"

    charge_id = Column(Integer, primary_key=True, index=True)

    loan_id = Column(
        Integer,
        ForeignKey("loans.loan_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Examples: INSURANCE_FEE / PROCESSING_FEE / BOOK_PRICE / OTHER
    charge_type = Column(String(30), nullable=False)

    # ✅ NEW: how this charge should be handled
    # DEDUCT_AT_DISBURSEMENT  -> deducted from principal (net cash lower)
    # COLLECT_SEPARATELY      -> collect later via CHARGE payment
    collect_mode = Column(String(30), nullable=False, server_default="COLLECT_SEPARATELY")

    # ✅ NEW: true only if deducted during disbursement finalization
    is_deducted = Column(Boolean, nullable=False, server_default="false")

    # DB default: now()
    charge_date = Column(DateTime, server_default=func.now(), nullable=True)

    amount = Column(Numeric(12, 2), nullable=False)

    # DB default: false
    is_waived = Column(Boolean, server_default="false", nullable=True)

    # DB default: 0
    waived_amount = Column(Numeric(12, 2), server_default="0", nullable=True)

    # ✅ collection tracking (supports partial)
    collected_amount = Column(Numeric(12, 2), server_default="0", nullable=True)
    is_collected = Column(Boolean, server_default="false", nullable=True)
    collected_on = Column(DateTime, nullable=True)

    payment_mode = Column(String(20), nullable=True)  # CASH/UPI/BANK/CARD/OTHER
    receipt_no = Column(String(64), nullable=True)

    remarks = Column(Text, nullable=True)

    # DB default: now()
    created_on = Column(DateTime, server_default=func.now(), nullable=True)

    loan = relationship("Loan", backref="charges")

    __table_args__ = (
        Index("ix_loan_charges_loan_id", "loan_id"),
        Index("ix_loan_charges_loan_type", "loan_id", "charge_type"),
        Index("ix_loan_charges_collected", "loan_id", "is_collected"),
        Index("ix_loan_charges_collect_mode", "loan_id", "collect_mode"),
    )
