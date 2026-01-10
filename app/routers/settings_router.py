from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.models.system_settings_model import SystemSetting
from app.schemas.settings_schema import SettingPatch, SettingCreate

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("")
def list_settings(db: Session = Depends(get_db)):
    rows = db.query(SystemSetting).all()
    return [{"key": r.key, "value": r.value, "description": r.description} for r in rows]

@router.post("", status_code=status.HTTP_201_CREATED)
def create_setting(payload: SettingCreate, db: Session = Depends(get_db)):
    # 1) Prevent duplicate key
    existing = db.query(SystemSetting).filter(SystemSetting.key == payload.key).first()
    if existing:
        raise HTTPException(status_code=409, detail="Setting key already exists")

    # 2) Create new setting
    obj = SystemSetting(
        key=payload.key.strip(),
        value=str(payload.value).strip(),
        description=(payload.description or "").strip(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)

    return {
        "message": "created",
        "key": obj.key,
        "value": obj.value,
        "description": obj.description,
    }

@router.patch("")
def update_setting(payload: SettingPatch, db: Session = Depends(get_db)):
    obj = db.query(SystemSetting).filter(SystemSetting.key == payload.key).first()
    if not obj:
        raise HTTPException(404, "Setting not found")

    obj.value = payload.value
    db.commit()
    return {"message": "updated", "key": obj.key, "value": obj.value}
