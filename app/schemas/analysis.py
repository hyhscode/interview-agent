from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

class AnalysisResult(BaseModel):
    score: int = 0
    summmary:str = ""
    matched: list[str] = []
    gaps:list[str] = []
    suggestions: list[str] = []

class JdIn(BaseModel):
    jd_text:str = Field(min_length=20,max_length=8000)

class AnalysisOut(BaseModel):
    id:int 
    resume_id:int
    status:str
    score:int
    result:AnalysisResult | None = None
    created_at:datetime

    model_config = ConfigDict(from_attributes=True)