"""面试接口。B4 只做"开局 + 查历史"，B6 加"继续回答"。"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.interview import InterviewTurn
from app.models.resume import Resume
from app.models.user import User
from app.schemas.interview import (
    AnswerIn,
    AnswerOut,
    InterviewCreateIn,
    InterviewOut,
    SummaryOut,
    TurnOut,
)
from app.services import interview as interview_service
from app.services import interview_state

logger = logging.getLogger(__name__)

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


@router.post("/{session_id}/answer", response_model=AnswerOut)
async def answer_question(
    session_id: int,
    payload: AnswerIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交一轮回答，拿到面试官的下一个问题。

    ★ 这个接口的流程体现了"状态机控制流程、模型只管措辞"：
      1. 代码先决定【下一个问题属于哪个阶段】
      2. 再把"阶段 + 历史 + 刚才的回答"交给模型，只让它生成一句话
      3. 模型返回后，代码再决定【要不要结束】
    """
    session = interview_service.get_session(
        db, session_id=session_id, user_id=current_user.id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="面试会话不存在")

    if session.status != "active":
        raise HTTPException(status_code=400, detail="这场面试已经结束了")

    # ---- 1. 记下候选人的回答 ----
    candidate_turn = InterviewTurn(
        session_id=session.id,
        role="candidate",
        content=payload.answer,
        stage=session.stage,
        turn_index=session.turn_count + 1,
    )
    db.add(candidate_turn)
    db.flush()

    turns = interview_service.get_turns(db, session.id)
    # 注意要重新查：刚 add 的那条 flush 后已在库里

    # ---- 2. 代码决定下一个阶段（不看模型脸色）----
    next_stage = interview_state.decide_next_stage(session.stage, turns)

    # ---- 3. 判断是否该结束 ----
    reached_end = (
        next_stage == interview_state.STAGE_FLOW[-1]
        and interview_state.count_asked_in_stage(turns, next_stage) >= 1
    )
    too_long = len(turns) >= interview_state.MAX_TOTAL_TURNS

    if reached_end or too_long:
        session.status = "finished"
        session.finished_at = datetime.now(timezone.utc)
        session.stage = next_stage
        session.turn_count = len(turns)
        db.commit()

        return AnswerOut(
            question="",
            stage=next_stage,
            is_finished=True,
            turn_count=len(turns),
            turns=[TurnOut.model_validate(candidate_turn)],
        )

    # ---- 4. 让模型生成"这一个"问题 ----
    history_text = interview_state.compress_history(turns[:-1])
    resume_summary = ""
    resume = db.execute(
        select(Resume).where(Resume.id == session.resume_id)
    ).scalar_one_or_none()
    if resume is not None:
        resume_summary = resume.parsed_json or resume.raw_text

    try:
        question = await run_in_threadpool(
            interview_state.generate_question,
            stage=next_stage,
            resume_summary=resume_summary,
            history_text=history_text,
            last_answer=payload.answer,
        )
    except Exception:
        logger.exception("生成问题失败 session=%s", session_id)
        # 已经记下回答了，不能假装整轮成功。回滚候选轮，让用户重试
        db.rollback()
        raise HTTPException(status_code=503, detail="AI 面试官暂时不可用，请稍后重试")

    # ---- 5. 记下面试官的问题 ----
    interviewer_turn = InterviewTurn(
        session_id=session.id,
        role="interviewer",
        content=question,
        stage=next_stage,
        turn_index=len(turns) + 1,
    )
    db.add(interviewer_turn)

    session.stage = next_stage
    session.turn_count = len(turns) + 1
    db.commit()
    db.refresh(interviewer_turn)

    return AnswerOut(
        question=question,
        stage=next_stage,
        is_finished=False,
        turn_count=session.turn_count,
        turns=[
            TurnOut.model_validate(candidate_turn),
            TurnOut.model_validate(interviewer_turn),
        ],
    )


@router.post("/{session_id}/finish", response_model=SummaryOut)
async def finish_interview(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """结束面试并生成评估。"""
    session = interview_service.get_session(
        db, session_id=session_id, user_id=current_user.id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="面试会话不存在")

    turns = interview_service.get_turns(db, session.id)
    if not turns:
        raise HTTPException(status_code=400, detail="这场面试还没有任何对话")

    history_text = "\n".join(
        f"{'面试官' if t.role == 'interviewer' else '候选人'}：{t.content}"
        for t in turns
    )

    try:
        data = await run_in_threadpool(interview_state.generate_summary, history_text)
    except Exception:
        logger.exception("生成总结失败 session=%s", session_id)
        raise HTTPException(status_code=503, detail="AI 评估暂时不可用，请稍后重试")

    session.status = "finished"
    session.finished_at = datetime.now(timezone.utc)
    db.commit()

    return SummaryOut(
        score=int(data.get("score", 0)),
        summary=data.get("summary", ""),
        strengths=data.get("strengths", []),
        weaknesses=data.get("weaknesses", []),
    )
