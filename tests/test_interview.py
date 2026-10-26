"""面试状态机测试。

★ 这一单的重点：状态机是【纯函数】，不依赖 LLM、不依赖网络，
  所以可以测得又准又快。这是"把流程从模型手里拿走"的最大收益 ——
  模型靠不住，代码靠得住，而代码可以测。
"""

import pytest

from app.models.interview import InterviewTurn
from app.services import interview_state


def _turn(role: str, stage: str, content: str = "x", idx: int = 1) -> InterviewTurn:
    """造一个轮次对象（不入库，只用于测试纯函数）。"""
    return InterviewTurn(
        session_id=1, role=role, stage=stage, content=content, turn_index=idx
    )


# ---------- 状态机：阶段流转 ----------

def test_self_intro_only_once():
    """自我介绍只问一次，问完就进项目深挖。"""
    turns = [_turn("interviewer", "self_intro")]

    assert interview_state.decide_next_stage("self_intro", turns) == "project_deep_dive"


def test_project_deep_dive_allows_three():
    """项目深挖问 1 次、2 次都还在本阶段，第 3 次之后才走。"""
    one = [_turn("interviewer", "project_deep_dive")]
    two = one + [_turn("interviewer", "project_deep_dive")]
    three = two + [_turn("interviewer", "project_deep_dive")]

    assert interview_state.decide_next_stage("project_deep_dive", one) == "project_deep_dive"
    assert interview_state.decide_next_stage("project_deep_dive", two) == "project_deep_dive"
    assert interview_state.decide_next_stage("project_deep_dive", three) == "tech_qa"


def test_last_stage_stays():
    """最后一个阶段问完之后不再前进（停在反问环节）。"""
    turns = [_turn("interviewer", "candidate_questions")]

    assert interview_state.decide_next_stage("candidate_questions", turns) == "candidate_questions"


def test_candidate_turns_dont_count():
    """只有面试官的提问算轮数，候选人的回答不算。"""
    turns = [
        _turn("interviewer", "self_intro"),
        _turn("candidate", "self_intro"),
        _turn("candidate", "self_intro"),
    ]

    assert interview_state.count_asked_in_stage(turns, "self_intro") == 1


# ---------- 历史压缩 ----------

def test_compress_keeps_recent_full():
    """轮次少的时候，全部完整保留。"""
    turns = [
        _turn("interviewer", "self_intro", "介绍一下自己"),
        _turn("candidate", "self_intro", "我叫张三"),
    ]

    text = interview_state.compress_history(turns)

    assert "介绍一下自己" in text
    assert "我叫张三" in text


def test_compress_drops_early_answers():
    """轮次多的时候，早期的候选人长回答被丢掉，只留问题。"""
    turns = []
    for i in range(1, 9):
        turns.append(_turn("interviewer", "tech_qa", f"第{i}个问题", i * 2 - 1))
        turns.append(_turn("candidate", "tech_qa", f"第{i}个很长的回答内容", i * 2))

    text = interview_state.compress_history(turns)

    # 早期的问题还在
    assert "第1个问题" in text
    # 早期的回答被丢掉了
    assert "第1个很长的回答内容" not in text
    # 最近的回答保留
    assert "第8个很长的回答内容" in text


# ---------- 端到端：完整面试流程 ----------

@pytest.fixture
def fake_question(monkeypatch):
    """把生成问题换成固定文本，测试不调 LLM。"""
    monkeypatch.setattr(
        "app.routers.interviews.interview_state.generate_question",
        lambda **kwargs: f"【{kwargs['stage']}】请继续说明",
    )


def _setup(client, test_engine, email: str = "iv@test.com") -> tuple[str, int]:
    """注册 → 登录 → 造一份已解析简历 → 开一场面试。

    ★ 关键：简历必须写进【测试用的内存库】，不能用 SessionLocal 写真实库。
      因为 client fixture 已经把 get_db 换成了测试库 ——
      写到真实库里，接口在测试库里当然找不到这份简历。
    """
    import json as _json

    from sqlalchemy.orm import sessionmaker

    from app.models.resume import Resume
    from app.models.user import User

    client.post("/auth/register", json={"email": email, "password": "12345678"})
    token = client.post(
        "/auth/login", json={"email": email, "password": "12345678"}
    ).json()["access_token"]

    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    db = TestSession()
    user = db.query(User).filter(User.email == email).first()
    resume = Resume(
        user_id=user.id,
        filename="cv.pdf",
        raw_text="张三 熟悉 FastAPI Redis",
        char_count=20,
        status="parsed",
        parsed_json=_json.dumps({"name": "张三", "skills": ["FastAPI"]}),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    resume_id = resume.id
    db.close()

    session = client.post(
        "/interviews",
        json={"resume_id": resume_id},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    return token, session["id"]


def test_interview_flow_advances_stage(client, fake_question, test_engine, monkeypatch):
    """完整走一轮：答完能拿到下一个问题，且阶段按规则前进。"""
    from sqlalchemy.orm import sessionmaker

    # 面试接口也用自己开的 session（start_interview 走依赖注入没问题，
    # 但这里统一 patch 一下更稳）
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("app.services.interview_state.chat", lambda *a, **k: ('{"question":"x"}', 1, 1))

    token, sid = _setup(client, test_engine, "flow@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(f"/interviews/{sid}/answer", json={"answer": "我做过后端"}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_finished"] is False
    assert body["stage"] == "project_deep_dive"
    # ↑ 自我介绍问过了，答完就该进项目深挖


def test_cannot_answer_others_session(client, fake_question, test_engine):
    """★ 越权：B 不能替 A 回答问题。"""
    token_a, sid = _setup(client, test_engine, "iv-a@test.com")
    client.post("/auth/register", json={"email": "iv-b@test.com", "password": "12345678"})
    token_b = client.post(
        "/auth/login", json={"email": "iv-b@test.com", "password": "12345678"}
    ).json()["access_token"]

    resp = client.post(
        f"/interviews/{sid}/answer",
        json={"answer": "我是 B"},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert resp.status_code == 404
