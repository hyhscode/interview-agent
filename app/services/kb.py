"""面经知识库：切块、入库、检索。"""

import json
import logging
import re

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kb import KbChunk, KbDocument
from app.services.bm25 import BM25, tokenize
from app.services.embeddings import embed_query, embed_texts


logger = logging.getLogger(__name__)

CHUNK_SIZE = 400
# 硬上限：超过这个长度就强制切开（防止单个巨块）

MIN_CHUNK = 50
# ★ 软下限：一块至少要 50 字，太短的段落（比如只有一个标题）才跟下一段合并。
#
# ★★ 这两个值的来历（实测修正）：一开始我定 500/80，用真实面经测出来
#    只有 2 块 —— 一篇讲了 6 个话题的面经被压成 2 块，
#    问「FastAPI 依赖注入」返回的是「自我介绍」。
#    因为一块里混了 3 个话题，向量被"平均"掉了。
#    最终改成"按段落切 + 50 字软下限 + 400 字硬上限"，
#    6 个话题切成 6 块，三个查询全部命中正确段落。
#
#    结论：切块大小必须用你自己的数据实测，不能拍脑袋。

CHUNK_OVERLAP = 60


def split_text(text: str) -> list[str]:
    """把长文本切成块。

    策略：以【段落】为单位（面经通常一段一个话题）：
      - 段落短于 MIN_CHUNK → 跟下一段合并，避免碎块
      - 累积长度超过 MIN_CHUNK → 就单独成一块，不再往里塞
      - 段落本身超过 CHUNK_SIZE → 硬切，并保留 CHUNK_OVERLAP 重叠
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    buffer = ""

    for para in paragraphs:
        # 超长段落：先把 pending 的 buffer 吐出来，再硬切
        while len(para) > CHUNK_SIZE:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.append(para[:CHUNK_SIZE])
            para = para[CHUNK_SIZE - CHUNK_OVERLAP :]
            # ↑ 保留重叠，避免结论落在切口上

        if not buffer:
            buffer = para
        elif len(buffer) < MIN_CHUNK:
            # 上一块太短 → 合并
            buffer = f"{buffer}\n{para}"
        else:
            # 上一块已经够长 → 各自成块
            chunks.append(buffer)
            buffer = para

    if buffer:
        chunks.append(buffer)

    return chunks


def add_document(
    db: Session, *, filename: str, text: str, uploader_id: int
) -> KbDocument:
    """入库一份文档：切块 → 批量编码 → 存库。"""
    chunks = split_text(text)
    if not chunks:
        raise ValueError("文档内容为空")

    vectors = embed_texts(chunks)

    doc = KbDocument(
        filename=filename,
        uploader_id=uploader_id,
        chunk_count=len(chunks),
    )
    db.add(doc)
    db.flush()   # 拿 doc.id

    for index, (content, vector) in enumerate(zip(chunks, vectors)):
        db.add(
            KbChunk(
                document_id=doc.id,
                chunk_index=index,
                content=content,
                embedding_json=json.dumps(vector),
            )
        )

    db.commit()
    db.refresh(doc)
    logger.info("入库完成 file=%s chunks=%d", filename, len(chunks))
    return doc


def search(db: Session, *, query: str, top_k: int = 3) -> list[tuple[KbChunk, float]]:
    """向量检索：算余弦相似度，返回最像的 top_k 块。

    ★ 注意这里用的是【暴力全量计算】，没有向量索引。
      为什么可以：几千个块 × 1024 维，numpy 矩阵乘一次几十毫秒。
      什么时候不行：十万块以上，就要上近似最近邻索引（HNSW / IVF）。
      知道边界在哪，比盲目上 Chroma 更重要。
    """
    chunks = list(db.execute(select(KbChunk)).scalars().all())
    if not chunks:
        return []

    query_vec = np.array(embed_query(query), dtype=np.float32)

    matrix = np.array(
        [json.loads(c.embedding_json) for c in chunks], dtype=np.float32
    )

    # 余弦相似度 = 点积 / (模长乘积)，用矩阵运算一次算完所有块
    dots = matrix @ query_vec
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vec) + 1e-9
    scores = dots / norms

    # argsort 升序 → 反转取前 k 个 → 得到从大到小的索引
    top_indices = scores.argsort()[::-1][:top_k]

    return [(chunks[i], float(scores[i])) for i in top_indices]


# ============================================================
# B5b：混合检索（向量 + BM25 关键词，用 RRF 融合）
# ============================================================

RECALL_K = 10
# 每一路先各取 10 个候选，再融合。取太少会漏，取太多等于没筛

RRF_K = 60
# RRF 的平滑常数。作用是压住"第 1 名"的优势，
# 让两路都排前面的文档真正胜出，而不是被某一路的第 1 名绑架


def vector_scores(db: Session, query: str) -> tuple[list[KbChunk], np.ndarray]:
    """纯向量打分，返回 (所有块, 每块的余弦分)。"""
    chunks = list(db.execute(select(KbChunk)).scalars().all())
    if not chunks:
        return [], np.array([], dtype=np.float32)

    query_vec = np.array(embed_query(query), dtype=np.float32)
    matrix = np.array([json.loads(c.embedding_json) for c in chunks], dtype=np.float32)

    dots = matrix @ query_vec
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vec) + 1e-9
    return chunks, dots / norms


def hybrid_search(
    db: Session, *, query: str, top_k: int = 3
) -> list[tuple[KbChunk, float]]:
    """混合检索：向量召回 + BM25 召回 → RRF 融合 → 取 top_k。

    ★ 为什么不能把两路分数直接相加：
      余弦相似度在 0~1 之间，BM25 的分数没有上界（可能 5，也可能 50）。
      直接相加 = 让 BM25 主导一切。所以必须【用排名融合，不用分数融合】。
    """
    chunks, vec = vector_scores(db, query)
    if not chunks:
        return []

    # ---- 第 1 路：向量召回 ----
    vec_ranked = list(vec.argsort()[::-1][:RECALL_K])

    # ---- 第 2 路：BM25 关键词召回 ----
    bm25 = BM25([tokenize(c.content) for c in chunks])
    bm25_ranked = [idx for idx, _ in bm25.rank(query)][:RECALL_K]

    # ---- 融合：Reciprocal Rank Fusion ----
    # 公式：得分 = Σ 1 / (RRF_K + 该路排名)
    # 第 1 名得 1/61，第 2 名 1/62 …… 只依排名，不依赖分数高低
    fused: dict[int, float] = {}
    for rank, idx in enumerate(vec_ranked, start=1):
        fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank)
    for rank, idx in enumerate(bm25_ranked, start=1):
        fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank)

    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [(chunks[i], score) for i, score in ordered]
