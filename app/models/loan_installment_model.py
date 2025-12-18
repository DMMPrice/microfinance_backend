from sqlalchemy import (
    Column, Integer, String, Date, Numeric, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.utils.database import Base


class LoanInstallment(Base):
    __tablename__ = "loan_installments"
    __table_args__ = (
        UniqueConstraint("loan_id", "installment_no", name="uq_loan_installment_no"),
    )

    installment_id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.loan_id"), nullable=False, index=True)

    installment_no = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False, index=True)

    principal_due = Column(Numeric(12, 2), nullable=False)
    interest_due = Column(Numeric(12, 2), nullable=False)
    total_due = Column(Numeric(12, 2), nullable=False)

    principal_paid = Column(Numeric(12, 2), nullable=False, default=0)
    interest_paid = Column(Numeric(12, 2), nullable=False, default=0)
    total_paid = Column(Numeric(12, 2), nullable=False, default=0)

    status = Column(String(20), nullable=False, default="PENDING")
    paid_date = Column(Date, nullable=True)

    loan = relationship("Loan", back_populates="installments")