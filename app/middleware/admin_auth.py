from fastapi import Header, HTTPException
from app.config import settings


def verify_admin(x_admin_password: str = Header(default="")):
    if x_admin_password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
