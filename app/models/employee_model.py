# app/models/employee_model.py
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Date,
    Text,
    ForeignKey,
    DateTime,
    func,  # ✅ added
)
from sqlalchemy.orm import relationship
from app.utils.database import Base


class Employee(Base):
    __tablename__ = "employees"

    employee_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), unique=True, nullable=False)

    full_name = Column(String(150), nullable=False)
    phone = Column(String(20))

    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    region_id = Column(Integer, ForeignKey("regions.region_id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"), nullable=True)

    employee_code = Column(String(50), unique=True)

    # ✅ DB sets CURRENT_DATE automatically
    date_joined = Column(Date, nullable=False, server_default=func.current_date())

    notes = Column(Text)

    is_active = Column(Boolean, default=True)

    # ✅ better: DB timestamp instead of python datetime.utcnow
    created_on = Column(DateTime, nullable=False, server_default=func.now())

    user = relationship("User", back_populates="employee")
    role = relationship("Role", back_populates="employees")
    region = relationship("Region", back_populates="employees")
    branch = relationship("Branch", back_populates="employees")

    loan_officer = relationship("LoanOfficer", back_populates="employee", uselist=False)
