from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.utils.database import Base


class Group(Base):
    __tablename__ = "groups"

    group_id = Column(Integer, primary_key=True, index=True)
    group_name = Column(String(100), nullable=False)

    lo_id = Column(Integer, ForeignKey("loan_officers.lo_id"), nullable=False)
    region_id = Column(Integer, ForeignKey("regions.region_id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.branch_id"), nullable=True)

    meeting_day = Column(String(15), nullable=True)

    created_on = Column(DateTime(timezone=True), server_default=func.now())

    # 🔗 back-reference to LoanOfficer
    loan_officer = relationship("LoanOfficer", back_populates="groups")
