from datetime import datetime

from pydantic import BaseModel, ConfigDict

class Project(BaseModel):
    name: str = ""
    tech:list[str] = []
    highlights:list[str] =[]

class ResumeParsed(BaseModel):
    """简历解析出来的结构化结果。"""

    name: str = ""
    phone: str = ""
    email: str = ""
    skills: list[str] = []
    projects: list[Project] = []
    education: str = ""


class ResumeOut(BaseModel):
    id: int
    filename: str
    char_count: int
    status: str
    created_at: datetime
    parsed: ResumeParsed | None = None

    model_config = ConfigDict(from_attributes=True)