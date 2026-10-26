"""面试接口。B4 只做"开局 + 查历史"，B6 加"继续回答"。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.resume import Resume
from app.models.user import User
from app.schemas.interview import InterviewCreateIn, InterviewOut, TurnOut
from app.services import interview as interview_service

router = APIRouter(prefix="/interviews", tags=["面试"])


@router.post("", response_model=InterviewOut, status_code=status.HTTP_201_CREATED)
def start_interview(
    payload: InterviewCreateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """开始一场面试。"""
    resume = db.execute(
        select(Resume).where(
            Resume.id == payload.resume_id,
            Resume.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if resume is None:
        raise HTTPException(status_code=404, detail="简历不存在")

    if resume.status != "parsed":
        raise HTTPException(status_code=400, detail="简历还没解析完成")

    session = interview_service.create_session(
        db, resume_id=resume.id, user_id=current_user.id
    )
    turns = interview_service.get_turns(db, session.id)

    return InterviewOut(
        id=session.id,
        resume_id=session.resume_id,
        stage=session.stage,
        status=session.status,
        turn_count=session.turn_count,
        created_at=session.created_at,
        turns=[TurnOut.model_validate(t) for t in turns],
    )


@router.get("/{session_id}", response_model=InterviewOut)
def get_interview(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取一场面试的完整历史。"""
    session = interview_service.get_session(
        db, session_id=session_id, user_id=current_user.id
    )

    if session is None:
        raise HTTPException(status_code=404, detail="面试会话不存在")

    turns = interview_service.get_turns(db, session.id)

    return InterviewOut(
        id=session.id,
        resume_id=session.resume_id,
        stage=session.stage,
        status=session.status,
        turn_count=session.turn_count,
        created_at=session.created_at,
        turns=[TurnOut.model_validate(t) for t in turns],
    )
