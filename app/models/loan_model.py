from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Numeric, Boolean, ForeignKey
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base


class Loan(Base):
    __tablename__ = "loans"

    loan_id = Column(Integer, primary_key=True, index=True)
    loan_account_no = Column(String(50), unique=True, nullable=True)

    member_id = Column(Integer, ForeignKey("members.member_id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("groups.group_id"), nullable=False, index=True)
    lo_id = Column(Integer, ForeignKey("loan_officers.lo_id"), nullable=False, index=True)

    region_id = Column(Integer, ForeignKey("regions.region_id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"), nullable=True)

    product_id = Column(Integer, ForeignKey("loan_products.product_id"), nullable=True)

    disburse_date = Column(Date, nullable=False)
    first_installment_date = Column(Date, nullable=False)

    duration_weeks = Column(Integer, nullable=False)
    installment_type = Column(String(20), nullable=False, default="WEEKLY")

    principal_amount = Column(Numeric(12, 2), nullable=False)
    interest_amount_total = Column(Numeric(12, 2), nullable=False, default=0)
    total_disbursed_amount = Column(Numeric(12, 2), nullable=False)
    installment_amount = Column(Numeric(12, 2), nullable=False)

    # rules snapshot
    min_weeks_before_closure = Column(Integer, nullable=False, default=0)
    allow_early_closure = Column(Boolean, nullable=False, default=False)

    # advance / extra money
    advance_balance = Column(Numeric(12, 2), nullable=False, default=0)

    # ✅ soft deactivate
    is_active = Column(Boolean, nullable=False, default=True)
    deactivated_on = Column(DateTime, nullable=True)

    status = Column(String(20), nullable=False, default="DISBURSED")  # DISBURSED/ACTIVE/CLOSED/CANCELLED/DEACTIVATED
    closing_date = Column(Date, nullable=True)

    created_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    created_on = Column(DateTime, server_default=func.now())

    installments = relationship(
        "LoanInstallment",
        back_populates="loan",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
