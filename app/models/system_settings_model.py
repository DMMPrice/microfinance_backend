from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.utils.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(String(200), nullable=False)
    description = Column(Text)

    updated_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    updated_on = Column(DateTime, server_default=func.now(), onupdate=func.now())
