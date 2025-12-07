import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from datetime import datetime
from app.core.config import JWT_SECRET, JWT_ALGO

security = HTTPBearer()

def get_current_user(token: str = Depends(security)):
    try:
        payload = jwt.decode(token.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
    except Exception:
        raise HTTPException(401, "Invalid token")

    # Validate if expired
    if "exp" in payload and payload["exp"] < datetime.utcnow().timestamp():
        raise HTTPException(401, "Token expired")

    return payload
