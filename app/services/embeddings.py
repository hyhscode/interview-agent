"""文本 → 向量。embeddings 的唯一出口。"""

import logging

from openai import OpenAI

from app.core.config import get_settings


logger = logging.getLogger(__name__)
settings = get_settings()

_client: OpenAI | None = None

BATCH_SIZE = 16
# 一次请求编多少个文本。太大容易超时/超限，太小则请求次数多、慢


def get_client() -> OpenAI:
    """硅基流动的客户端（OpenAI 兼容协议）。"""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
            timeout=60.0,
        )
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量把文本变成向量。

    参数 texts : 文本列表
    返回       : 向量列表，长度和输入一致，每个向量 1024 维
    异常       : 网络失败 / 额度不足 时抛出
    """
    if not texts:
        return []

    vectors: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]

        resp = get_client().embeddings.create(
            model=settings.embedding_model,
            input=batch,
        )

        vectors.extend([d.embedding for d in resp.data])
        logger.info("编码 %d 条（累计 %d / %d）", len(batch), len(vectors), len(texts))

    return vectors


def embed_query(text: str) -> list[float]:
    """单条查询编码。单独一个函数是为了语义清晰 —— 查询和入库用途不同。"""
    return embed_texts([text])[0]
