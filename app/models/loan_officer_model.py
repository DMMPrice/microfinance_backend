from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.utils.database import Base


class LoanOfficer(Base):
    __tablename__ = "loan_officers"

    lo_id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        Integer,
        ForeignKey("employees.employee_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    employee = relationship("Employee", back_populates="loan_officer")
    groups = relationship("Group", back_populates="loan_officer")  # 👈 all their groups
