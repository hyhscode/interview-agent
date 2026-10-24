from fastapi import APIRouter,Depends, HTTPException,status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.user import RegisterIN,UserOut
from app.services import auth as auth_service

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