from fastapi import APIRouter,Depends, HTTPException,status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.user import RegisterIN,UserOut
from app.services import auth as auth_service
from app.core.deps import get_current_user
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import LoginIn, RegisterIN, TokenOut, UserOut

router = APIRouter(prefix="/auth",tags=["认证"])

@router.post("/register",response_model=UserOut,status_code=status.HTTP_201_CREATED)
def register(payload:RegisterIN,db:Session = Depends(get_db)):
    if auth_service.get_user_by_email(db,payload.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已注册",
        )

    user = auth_service.create_user(db,payload.email,payload.password)
    return user

@router.post("/login",response_model=TokenOut)
def login(payload: LoginIn,db:Session = Depends(get_db)):
    user = auth_service.authenticate_user(db,payload.email,payload.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    return TokenOut(access_token=create_access_token(user.id))

@router.get("/me",response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user