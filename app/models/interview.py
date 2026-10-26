from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

STAGES = [
    "self_intro",          # 自我介绍
    "project_deep_dive",   # 项目深挖
    "tech_qa",             # 技术追问
    "candidate_questions", # 反问环节
]

class InterviewSession(Base):
    """一场面试。"""

    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    stage: Mapped[str] = mapped_column(String(32), default="self_intro")
    status: Mapped[str] = mapped_column(String(16), default="active")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<InterviewSession id={self.id} stage={self.stage} turns={self.turn_count}>"

class InterviewTurn(Base):
    """一轮问答。role 决定这行是"面试官说的"还是"候选人说的"。"""

    __tablename__ = "interview_turns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id"), index=True
    )

    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)

    stage: Mapped[str] = mapped_column(String(32), default="self_intro")
    turn_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Turn {self.turn_index} {self.role}>"