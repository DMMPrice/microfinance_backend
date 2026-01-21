# app/models/user_model.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.utils.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    created_on = Column(DateTime, default=datetime.utcnow)

    employee = relationship(
        "Employee",
        back_populates="user",
        uselist=False,
        passive_deletes=True,  # IMPORTANT
    )
