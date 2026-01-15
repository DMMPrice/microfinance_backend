# app/models/expense_subcategories_model.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from app.utils.database import Base

class PaymentType(str, enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"

class ExpenseSubCategory(Base):
    __tablename__ = "expense_subcategories"

    subcategory_id = Column(Integer, primary_key=True, index=True)

    payment_type_enum = PGEnum(
        PaymentType,
        name="payment_type_enum",
        create_type=False,  # already created in DB
    )

    payment_type = Column(
        payment_type_enum,
        nullable=False,
        server_default="DEBIT",
    )
    category_id = Column(
        Integer,
        ForeignKey(
            "expense_categories.category_id",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    subcategory_name = Column(String(120), nullable=False)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # 🔗 Relationship (optional but useful)
    category = relationship(
        "ExpenseCategory",
        backref="subcategories",
        lazy="joined",
    )

    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "subcategory_name",
            name="uq_expense_subcategory_per_category",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ExpenseSubCategory(id={self.subcategory_id}, "
            f"name={self.subcategory_name}, "
            f"category_id={self.category_id})>"
        )
