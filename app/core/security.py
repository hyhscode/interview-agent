from pwdlib import PasswordHash
from datetime import datetime,timedelta,timezone

import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import get_settings

settings = get_settings()

password_hash = PasswordHash.recommended()

def hash_password(plain:str) -> str:
    return password_hash.hash(plain)

def verify_password(plain:str,hashed:str) -> bool:
    return password_hash.verify(plain,hashed)

def create_access_token(user_id:int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)

    payload = {
        "sub":str(user_id),
        "exp":expire,
    }
    return jwt.encode(payload,settings.jwt_secret_key,algorithm="HS256")

def decode_access_token(token:str) -> dict:
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=["HS256"]
    )