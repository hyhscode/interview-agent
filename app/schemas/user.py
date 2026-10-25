from datetime import datetime
from pydantic import BaseModel,ConfigDict,Field

class RegisterIN(BaseModel):
    email: str = Field(min_length=5,max_length=255)
    password: str = Field(min_length=8,max_length=128)

class UserOut(BaseModel):
    id:int
    email: str
    created_at:datetime

    model_config = ConfigDict(from_attributes=True)

class LoginIn(BaseModel):
    email: str
    password:str

class TokenOut(BaseModel):
    access_token:str
    token_type:str = "bearer"