# app/models/member_model.py
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Date,
    Boolean,
    ForeignKey,
    DateTime,
    func,
)
from app.utils.database import Base


class Member(Base):
    __tablename__ = "members"

    member_id = Column(Integer, primary_key=True, index=True)

    full_name = Column(String(150), nullable=False)
    father_or_husband_name = Column(String(150))
    mother_name = Column(String(150))

    photo_b64 = Column(Text)  # Base64 photo

    dob = Column(Date)
    phone = Column(String(20))
    aadhar_no = Column(String(20))
    pan_no = Column(String(20))
    voter_id = Column(String(30))

    present_address = Column(Text)
    permanent_address = Column(Text)
    pincode = Column(String(10))

    group_id = Column(Integer, ForeignKey("groups.group_id"))
    lo_id = Column(Integer, ForeignKey("loan_officers.lo_id"))
    branch_id = Column(Integer)
    region_id = Column(Integer)

    other_details = Column(Text)

    is_active = Column(Boolean, default=True)

    # 🔥 IMPORTANT FIX
    created_on = Column(
        DateTime, server_default=func.now()  # let DB set current timestamp
    )
