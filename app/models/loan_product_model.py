from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.utils.database import Base


class LoanProduct(Base):
    __tablename__ = "loan_products"

    product_id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String(100), unique=True, nullable=False)

    repayment_frequency = Column(String(20), nullable=False, default="WEEKLY")
    interest_type = Column(String(20), nullable=False, default="FLAT")

    is_active = Column(Boolean, default=True)
    created_on = Column(DateTime, server_default=func.now())
l̥