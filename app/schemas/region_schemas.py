# app/schemas/region_schemas.py

from pydantic import BaseModel
from typing import Optional


class RegionBase(BaseModel):
    region_name: str


class RegionCreate(RegionBase):
    pass


class RegionUpdate(BaseModel):
    region_name: Optional[str] = None


class RegionOut(RegionBase):
    region_id: int

    class Config:
        from_attributes = True
