from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.core.security import hash_password,verify_password

def get_user_by_email(db:Session,email: str) ->User | None:
    stmt = select(User).where(User.email == email)
    return db.execute(stmt).scalar_one_or_none()

def create_user(db:Session,email: str,password:str) -> User:
    user = User(email=email,hashed_password=hash_password(password))

    db.add(user)
    db.commit()
    db.refresh(user)

    return user

def authenticate_user(db: Session,email:str,password:str) -> User | None:
    user = get_user_by_email(db,email)

    if user is None:
        return None
    if not verify_password(password,user.hashed_password):
        return None

    return user