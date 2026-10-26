from datetime import datetime

from pydantic import BaseModel, ConfigDict

class ResumeOut(BaseModel):
    id:int
    filename:str
    char_count:int
    status:str
    created_at:datetime

    model_config = ConfigDict(from_attributes=True)