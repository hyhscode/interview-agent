from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

class Resume(Base):
    __tablename__ = "resumes"

    id:Mapped[int] = mapped_column(primary_key=True,autoincrement=True)

    user_id:Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )

    filename:Mapped[str] = mapped_column(String(255))
    raw_text:Mapped[str] = mapped_column(Text,default="")
    char_count:Mapped[int] = mapped_column(Integer,default=0)
    status:Mapped[str] = mapped_column(String(32),default="text_extracted")
    created_at:Mapped[datetime] = mapped_column(DateTime,server_default=func.now())

    def __repr__(self) -> str:
        return f"<Resume id={self.id} user={self.user_id} chars={self.char_count}>"