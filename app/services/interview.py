from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interview import InterviewSession, InterviewTurn


OPENING_QUESTION = (
    "我们开始面试。先请你用两分钟做个自我介绍，"
    "重点说一个你最熟悉的项目，以及你在其中具体负责什么。"
)
# ↑ B4 阶段先用固定开场白（不调 LLM），
#   B6 会按简历内容动态生成 —— 先把存储链路打通，再换智能


def create_session(db: Session, *, resume_id: int, user_id: int) -> InterviewSession:
    """创建一场面试，并写入第一条（面试官的提问）。"""
    session = InterviewSession(
        resume_id=resume_id,
        user_id=user_id,
        stage="self_intro",
        status="active",
        turn_count=1,
    )
    db.add(session)
    db.flush()
    # ↑ flush 不等于 commit：它把 SQL 发给数据库但【不提交事务】，
    #   目的是拿到自增的 session.id。后面还要写 turn，最后一起 commit

    db.add(
        InterviewTurn(
            session_id=session.id,
            role="interviewer",
            content=OPENING_QUESTION,
            stage="self_intro",
            turn_index=1,
        )
    )
    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, *, session_id: int, user_id: int) -> InterviewSession | None:

    stmt = select(InterviewSession).where(
        InterviewSession.id == session_id,
        InterviewSession.user_id == user_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_turns(db: Session, session_id: int) -> list[InterviewTurn]:
    """取一场面试的所有轮次，按轮次号升序。"""
    stmt = (
        select(InterviewTurn)
        .where(InterviewTurn.session_id == session_id)
        .order_by(InterviewTurn.turn_index)
    )
    return list(db.execute(stmt).scalars().all())