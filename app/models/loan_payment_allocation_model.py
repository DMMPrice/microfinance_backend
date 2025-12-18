from sqlalchemy import Column, Integer, Numeric, ForeignKey
from app.utils.database import Base


class LoanPaymentAllocation(Base):
    __tablename__ = "loan_payment_allocations"

    allocation_id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("loan_payments.payment_id"), nullable=False, index=True)
    installment_id = Column(Integer, ForeignKey("loan_installments.installment_id"), nullable=False, index=True)

    principal_alloc = Column(Numeric(12, 2), nullable=False, default=0)
    interest_alloc = Column(Numeric(12, 2), nullable=False, default=0)
l̥