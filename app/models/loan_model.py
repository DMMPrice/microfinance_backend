# app/models/loan_model.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Numeric,
    Boolean,
    ForeignKey,
    Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base


class Loan(Base):
    __tablename__ = "loans"

    __table_args__ = (
        Index("ix_loans_status", "status"),
        Index("ix_loans_member_status", "member_id", "status"),
        Index("ix_loans_group_status", "group_id", "status"),
        Index("ix_loans_lo_status", "lo_id", "status"),
    )

    loan_id = Column(Integer, primary_key=True, index=True)
    loan_account_no = Column(String(50), unique=True, nullable=True)

    member_id = Column(Integer, ForeignKey("members.member_id", ondelete="RESTRICT"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("groups.group_id", ondelete="RESTRICT"), nullable=False, index=True)
    lo_id = Column(Integer, ForeignKey("loan_officers.lo_id", ondelete="RESTRICT"), nullable=False, index=True)

    region_id = Column(Integer, ForeignKey("regions.region_id", ondelete="SET NULL"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.branch_id", ondelete="SET NULL"), nullable=True)

    product_id = Column(Integer, ForeignKey("loan_products.product_id", ondelete="SET NULL"), nullable=True)

    disburse_date = Column(Date, nullable=False)
    first_installment_date = Column(Date, nullable=False)

    duration_weeks = Column(Integer, nullable=False)
    installment_type = Column(String(20), nullable=False, server_default="WEEKLY")

    principal_amount = Column(Numeric(12, 2), nullable=False)
    interest_amount_total = Column(Numeric(12, 2), nullable=False, server_default="0")

    # NOTE:
    # - total_disbursed_amount in your DB is actually the TOTAL OUTSTANDING (principal + total interest)
    total_disbursed_amount = Column(Numeric(12, 2), nullable=False)

    # ✅ NEW: cash actually handed over to member at disbursement time
    net_disbursed_cash = Column(Numeric(12, 2), nullable=False, server_default="0")

    installment_amount = Column(Numeric(12, 2), nullable=False)

    # rules snapshot
    min_weeks_before_closure = Column(Integer, nullable=False, server_default="0")
    allow_early_closure = Column(Boolean, nullable=False, server_default="false")

    # advance / extra money
    advance_balance = Column(Numeric(12, 2), nullable=False, server_default="0")

    # ✅ soft deactivate / pause
    is_active = Column(Boolean, nullable=False, server_default="true")
    deactivated_on = Column(DateTime, nullable=True)

    # DISBURSED / ACTIVE / PAUSED / INACTIVE / CLOSED / CANCELLED
    status = Column(String(20), nullable=False, server_default="DISBURSED")

    closing_date = Column(Date, nullable=True)

    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_on = Column(DateTime, server_default=func.now(), nullable=True)

    installments = relationship(
        "LoanInstallment",
        back_populates="loan",
        cascade="all, delete-orphan",
        lazy="selectin",
        passive_deletes=True,
    )
