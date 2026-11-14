from fastapi import APIRouter, Depends, HTTPException

from backend.database import User
from backend.dependencies import get_db
from backend.schemas import LoginRequest, success
from backend.security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login")
def login(payload: LoginRequest, db=Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return success(
        {
            "access_token": create_access_token(user.username, user.role),
            "token_type": "bearer",
            "username": user.username,
            "role": user.role,
        }
    )
