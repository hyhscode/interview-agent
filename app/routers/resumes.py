import json
import logging

from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import ResumeOut, ResumeParsed
from app.services import pdf as pdf_service
from app.services import resume_parser
from app.services import llm as llm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resumes", tags=["简历"])

MAX_FILE_SIZE = 10 * 1024 * 1024

@router.post("", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只支持 PDF 文件",
        )

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件不能超过 {MAX_FILE_SIZE // 1024 // 1024} MB",
        )
    
    try:
        text, page_count = pdf_service.extract_text(raw)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF 解析失败，请确认文件未加密且未损坏",
        )

    if pdf_service.looks_like_scanned(text):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未能从这份 PDF 中提取到文字，可能是扫描件。请上传文字版 PDF",
        )

    resume = Resume(
        user_id=current_user.id,
        filename=file.filename or "unnamed.pdf",
        raw_text=text,
        char_count=len(text.strip()),
    )
    db.add(resume)

    # ---- 解析（可能失败，失败不影响"文件已保存"这件事）----
    parsed: ResumeParsed | None = None
    try:
        parsed, _, _ = await run_in_threadpool(resume_parser.parse_resume, text)


        resume.parsed_json = json.dumps(parsed.model_dump(), ensure_ascii=False)
        resume.status = "parsed"
    except Exception as exc:
        # 不抛给用户：简历已经存好了，解析失败只标状态
        resume.status = "parse_failed"
        logger.warning("简历解析失败 resume=%s: %s", resume.filename, exc)

    db.commit()
    db.refresh(resume)

    return ResumeOut(
        id=resume.id,
        filename=resume.filename,
        char_count=resume.char_count,
        status=resume.status,
        created_at=resume.created_at,
        parsed=parsed,
    )