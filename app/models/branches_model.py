# app/models/branches_model.py
from sqlalchemy import Column, Integer, String, ForeignKey, Date, Numeric, Text, DateTime, func
from sqlalchemy.orm import relationship
from app.utils.database import Base


class Branch(Base):
    __tablename__ = "branches"

    branch_id = Column(Integer, primary_key=True, index=True)
    branch_name = Column(String(100), unique=True, nullable=False)
    region_id = Column(Integer, ForeignKey("regions.region_id"), nullable=False)

    region = relationship("Region", back_populates="branches")
    employees = relationship("Employee", back_populates="branch")


class BranchExpense(Base):
    __tablename__ = "branch_expenses"

    expense_id = Column(Integer, primary_key=True, index=True)

    branch_id = Column(
        Integer,
        ForeignKey("branches.branch_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    category_id = Column(
        Integer,
        ForeignKey("expense_categories.category_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True
    )

    # ✅ ADD THIS (exists in DB)
    subcategory_id = Column(
        Integer,
        ForeignKey("expense_subcategories.subcategory_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=True,
        index=True
    )

    expense_date = Column(Date, nullable=False)

    amount = Column(Numeric(12, 2), nullable=False)

    # ✅ ADD THIS (exists in DB)
    payee = Column(String(180), nullable=True)

    description = Column(Text, nullable=True)
    payment_mode = Column(String(50), nullable=True)
    reference_no = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # relationships
    branch = relationship("Branch", backref="expenses")
    category = relationship("ExpenseCategory")

    # ✅ optional but useful
    subcategory = relationship("ExpenseSubCategory")