"""面经知识库接口。"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.kb import KbDocument
from app.models.user import User
from app.schemas.kb import KbDocumentOut, KbHit, KbSearchOut
from app.services import kb as kb_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kb", tags=["面经知识库"])

MAX_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_SUFFIX = (".txt", ".md")


@router.post(
    "/documents", response_model=KbDocumentOut, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传面经文档（txt / md），切块编码后入库。"""
    filename = file.filename or "unnamed.txt"

    if not filename.lower().endswith(ALLOWED_SUFFIX):
        raise HTTPException(status_code=400, detail="只支持 .txt / .md 文本文件")
    # ↑ 为什么先只支持纯文本：PDF 要走文字抽取（我们 B2 已经做了），
    #   但面经文档多为复制粘贴的文本，先支持最常见的

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件不能超过 5 MB")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
            # ↑ 中文 Windows 上很多 txt 是 GBK 编码，直接 utf-8 解会崩
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="无法识别文件编码，请另存为 UTF-8")

    try:
        doc = await run_in_threadpool(
            kb_service.add_document,
            db,
            filename=filename,
            text=text,
            uploader_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("面经入库失败 filename=%s", filename)
        raise HTTPException(status_code=503, detail="知识库服务暂时不可用，请稍后重试")

    return KbDocumentOut(
        document_id=doc.id,
        filename=doc.filename,
        chunk_count=doc.chunk_count,
        created_at=doc.created_at,
    )


@router.get("/search", response_model=KbSearchOut)
def search_kb(
    q: str = Query(min_length=2, max_length=200, description="检索问题"),
    top_k: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按语义检索面经片段。"""
    try:
        results = kb_service.hybrid_search(db, query=q, top_k=top_k)
    except Exception:
        logger.exception("检索失败 q=%s", q)
        raise HTTPException(status_code=503, detail="检索服务暂时不可用")

    # 先把命中的文档名查出来（一次查询，避免在循环里反复查库）
    doc_ids = {chunk.document_id for chunk, _ in results}
    filenames = {
        d.id: d.filename
        for d in db.query(KbDocument).filter(KbDocument.id.in_(doc_ids)).all()
    } if doc_ids else {}

    return KbSearchOut(
        query=q,
        hits=[
            KbHit(
                content=chunk.content,
                score=round(score, 4),
                source=filenames.get(chunk.document_id, "unknown"),
                chunk_index=chunk.chunk_index,
            )
            for chunk, score in results
        ],
    )
