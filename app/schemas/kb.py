"""面经知识库的接口出入参。"""

from datetime import datetime

from pydantic import BaseModel, Field


class KbDocumentOut(BaseModel):
    """上传面经后的返回。"""

    document_id: int
    filename: str
    chunk_count: int
    created_at: datetime


class KbHit(BaseModel):
    """一条检索命中。"""

    content: str
    score: float
    source: str
    # 来源文件名 —— 让用户能判断"这条答案可不可信"
    chunk_index: int


class KbSearchOut(BaseModel):
    query: str
    hits: list[KbHit] = []


class KbSearchIn(BaseModel):
    q: str = Field(min_length=2, max_length=200)
    top_k: int = Field(default=3, ge=1, le=10)
    # ge = greater or equal（最小），le = less or equal（最大）
    # 用 Field 约束，比在函数里写 if 更好：会自动进 /docs 文档
