# app/models/roles_model.py
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.utils.database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)

    employees = relationship("Employee", back_populates="role")
