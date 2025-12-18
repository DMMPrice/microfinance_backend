from pydantic import BaseModel


class SettingPatch(BaseModel):
    key: str
    value: str
