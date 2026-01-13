# app/models/expense_categories_model.py

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func

from app.utils.database import Base


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"

    category_id = Column(Integer, primary_key=True, index=True)
    category_name = Column(String(120), nullable=False, unique=True, index=True)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ExpenseCategory(id={self.category_id}, name={self.category_name})>"
