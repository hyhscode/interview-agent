"""简历接口。"""

import json
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import ResumeOut, ResumeParsed
from app.services import pdf as pdf_service
from app.services import resume_parser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resumes", tags=["简历"])

MAX_FILE_SIZE = 10 * 1024 * 1024


def _to_out(resume: Resume) -> ResumeOut:

    parsed = None
    if resume.parsed_json:
        parsed = ResumeParsed.model_validate_json(resume.parsed_json)

    return ResumeOut(
        id=resume.id,
        filename=resume.filename,
        char_count=resume.char_count,
        status=resume.status,
        created_at=resume.created_at,
        parsed=parsed,
    )


@router.post("", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="只支持 PDF 文件")

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件不能超过 {MAX_FILE_SIZE // 1024 // 1024} MB",
        )


    try:
        text, _page_count = pdf_service.extract_text(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="PDF 解析失败，请确认文件未加密且未损坏")

    if pdf_service.looks_like_scanned(text):
        raise HTTPException(
            status_code=400,
            detail="未能从这份 PDF 中提取到文字，可能是扫描件。请上传文字版 PDF",
        )


    try:
        parsed, _in_tok, _out_tok = await run_in_threadpool(
            resume_parser.parse_resume, text
        )
    except Exception as exc:

        logger.exception("简历解析失败 filename=%s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 解析服务暂时不可用，请稍后重试",
        )


    if not resume_parser.looks_like_resume(parsed):
        raise HTTPException(
            status_code=400,
            detail="这份文件里没有识别出简历信息，请确认上传的是简历而不是其他文档",
        )

    resume = Resume(
        user_id=current_user.id,
        filename=file.filename or "unnamed.pdf",
        raw_text=text,
        char_count=len(text.strip()),
        parsed_json=json.dumps(parsed.model_dump(), ensure_ascii=False),
        status="parsed",
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    return _to_out(resume)


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    stmt = select(Resume).where(
        Resume.id == resume_id,
        Resume.user_id == current_user.id,
        # ↑ 这个条件不能少。少了它，任何人拿到 id 就能看别人的简历
    )
    resume = db.execute(stmt).scalar_one_or_none()

    if resume is None:
        raise HTTPException(status_code=404, detail="简历不存在")


    return _to_out(resume)
