# app/models/loan_installment_model.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from app.utils.database import Base


class LoanInstallment(Base):
    __tablename__ = "loan_installments"

    __table_args__ = (
        UniqueConstraint("loan_id", "installment_no", name="uq_loan_installment_no"),
        Index("ix_loan_installments_due_date", "due_date"),
        Index("ix_loan_installments_loan_id", "loan_id"),
    )

    installment_id = Column(Integer, primary_key=True, index=True)

    loan_id = Column(
        Integer,
        ForeignKey("loans.loan_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    installment_no = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False)

    principal_due = Column(Numeric(12, 2), nullable=False)
    interest_due = Column(Numeric(12, 2), nullable=False)
    total_due = Column(Numeric(12, 2), nullable=False)

    principal_paid = Column(Numeric(12, 2), nullable=False, server_default="0")
    interest_paid = Column(Numeric(12, 2), nullable=False, server_default="0")
    total_paid = Column(Numeric(12, 2), nullable=False, server_default="0")

    status = Column(String(20), nullable=False, server_default="PENDING")
    paid_date = Column(Date, nullable=True)

    loan = relationship("Loan", back_populates="installments")
