from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InterviewCreateIn(BaseModel):
    resume_id: int


class TurnOut(BaseModel):
    id: int
    role: str
    content: str
    stage: str
    turn_index: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InterviewOut(BaseModel):
    id: int
    resume_id: int
    stage: str
    status: str
    turn_count: int
    created_at: datetime
    turns: list[TurnOut] = []