from pydantic import BaseModel, Field


class SettingPatch(BaseModel):
    key: str
    value: str


class SettingCreate(BaseModel):
    key: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)
    description: str = Field("", max_length=500)
