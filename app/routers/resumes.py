from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import ResumeOut
from app.services import pdf as pdf_service

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
        user_id=current_user.id,   # ← 身份来自 token
        filename=file.filename or "unnamed.pdf",
        raw_text=text,
        char_count=len(text.strip()),
    )

    db.add(resume)
    db.commit()
    db.refresh(resume)

    return resume