"""面经知识库：文档 + 切块。

一对多：一份文档（kb_documents）→ 多个切块（kb_chunks）
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class KbDocument(Base):
    """一份上传的面经文档。"""

    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    filename: Mapped[str] = mapped_column(String(255))

    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 记录谁传的（用于追责/统计），但检索时不按用户过滤 ——
    # 面经是公共知识，所有人共享一份库

    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<KbDocument id={self.id} file={self.filename} chunks={self.chunk_count}>"


class KbChunk(Base):
    """一个切块 + 它的向量。

    ★ 为什么向量直接存成 JSON 字符串，不用向量数据库：
      数据量小（几千块）时，全量算余弦只要几十毫秒，
      多一个 Chroma 就多一个依赖、多一份运维成本。
      等数据量上到十万级再换 —— 这个取舍要在面试时能讲清。
    """

    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    document_id: Mapped[int] = mapped_column(ForeignKey("kb_documents.id"), index=True)

    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    # 在文档里的第几块，从 0 开始

    content: Mapped[str] = mapped_column(Text)

    embedding_json: Mapped[str] = mapped_column(Text, default="")
    # 1024 个浮点数序列化成 JSON 字符串存着

    def __repr__(self) -> str:
        return f"<KbChunk doc={self.document_id} idx={self.chunk_index}>"
