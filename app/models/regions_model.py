# app/models/regions_model.py
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.utils.database import Base


class Region(Base):
    __tablename__ = "regions"

    region_id = Column(Integer, primary_key=True, index=True)
    region_name = Column(String(100), unique=True, nullable=False)

    branches = relationship("Branch", back_populates="region")
    employees = relationship("Employee", back_populates="region")
