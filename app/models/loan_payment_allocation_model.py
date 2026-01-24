# app/models/loan_payment_allocation_model.py

from sqlalchemy import (
    Column,
    Integer,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from app.utils.database import Base


class LoanPaymentAllocation(Base):
    __tablename__ = "loan_payment_allocations"

    __table_args__ = (
        UniqueConstraint("payment_id", "installment_id", name="uq_payment_installment_alloc"),
        Index("ix_alloc_payment_installment", "payment_id", "installment_id"),
    )

    allocation_id = Column(Integer, primary_key=True, index=True)

    payment_id = Column(
        Integer,
        ForeignKey("loan_payments.payment_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ✅ nullable so we can store CHARGE / ADVANCE payments without installment allocation
    installment_id = Column(
        Integer,
        ForeignKey("loan_installments.installment_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # ✅ DB-safe defaults
    principal_alloc = Column(Numeric(12, 2), nullable=False, server_default="0")
    interest_alloc = Column(Numeric(12, 2), nullable=False, server_default="0")
