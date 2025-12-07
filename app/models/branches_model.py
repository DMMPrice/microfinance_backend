# app/models/branches_model.py
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.utils.database import Base


class Branch(Base):
    __tablename__ = "branches"

    branch_id = Column(Integer, primary_key=True, index=True)
    branch_name = Column(String(100), unique=True, nullable=False)
    region_id = Column(Integer, ForeignKey("regions.region_id"), nullable=False)

    region = relationship("Region", back_populates="branches")
    employees = relationship("Employee", back_populates="branch")
