from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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

class AnswerIn(BaseModel):
    """提交一轮回答。"""

    answer: str = Field(min_length=2, max_length=4000)


class AnswerOut(BaseModel):
    """一轮问答之后返回什么。"""

    question: str = ""
    # 面试官的下一个问题。面试结束时会话结束时为空

    stage: str = ""
    is_finished: bool = False
    turn_count: int = 0
    turns: list[TurnOut] = []
    # 本轮新增的轮次（候选人的答 + 面试官的问），方便前端直接追加显示


class SummaryOut(BaseModel):
    """面试结束后的评估。"""

    score: int = 0
    summary: str = ""
    strengths: list[str] = []
    weaknesses: list[str] = []
