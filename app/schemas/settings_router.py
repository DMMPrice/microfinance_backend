from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.models.system_settings_model import SystemSetting
from app.schemas.settings_schema import SettingPatch

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("")
def list_settings(db: Session = Depends(get_db)):
    rows = db.query(SystemSetting).all()
    return [{"key": r.key, "value": r.value, "description": r.description} for r in rows]


@router.patch("")
def update_setting(payload: SettingPatch, db: Session = Depends(get_db)):
    obj = db.query(SystemSetting).filter(SystemSetting.key == payload.key).first()
    if not obj:
        raise HTTPException(404, "Setting not found")

    obj.value = payload.value
    db.commit()
    return {"message": "updated", "key": obj.key, "value": obj.value}
