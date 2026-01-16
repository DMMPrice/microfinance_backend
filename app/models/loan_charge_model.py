# app/models/loan_charge_model.py

from sqlalchemy import Column, Integer, String, Numeric, Boolean, Text, DateTime, ForeignKey, Index, func
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

    charge_type = Column(String(30), nullable=False)

    # DB default: now()
    charge_date = Column(DateTime, server_default=func.now(), nullable=True)

    amount = Column(Numeric(12, 2), nullable=False)

    # DB default: false
    is_waived = Column(Boolean, server_default="false", nullable=True)

    # DB default: 0
    waived_amount = Column(Numeric(12, 2), server_default="0", nullable=True)

    remarks = Column(Text, nullable=True)

    # DB default: now()
    created_on = Column(DateTime, server_default=func.now(), nullable=True)

    # Optional relationship (safe even if you don’t use it)
    loan = relationship("Loan", backref="charges")

    __table_args__ = (
        Index("ix_loan_charges_loan_id", "loan_id"),
    )
