from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"), index=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    jd_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    score: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[str] = mapped_column(Text, default="")

    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    def __repr__(self) -> str:
        return f"<Analysis id={self.id} resume={self.resume_id} status={self.status}>"
    