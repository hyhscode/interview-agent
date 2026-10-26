"""匹配度分析接口测试。

★ 这一单最关键的两件事：
  1. 用假 analyze 替代真 LLM —— 测试不花钱、不依赖网络
  2. 把后台任务用的 SessionLocal 换成测试库 —— 不污染真实 app.db
"""

import pytest
from sqlalchemy.orm import sessionmaker

from app.schemas.analysis import AnalysisResult


JD = (
    "岗位职责：负责 AI 应用的后端开发，使用 Python/FastAPI 构建服务，"
    "对接大模型 API，负责 RAG 检索链路优化。"
    "任职要求：熟悉 Python，了解 FastAPI 或 Flask，"
    "有 LLM 应用开发经验，了解向量数据库。"
)
# ↑ 必须 >= 20 字，否则会被 JdIn 的 min_length 拦成 422


@pytest.fixture
def fake_analyze(monkeypatch):
    """把真正的 LLM 分析换成固定结果。"""

    def fake(resume_text, parsed_summary, jd_text):
        return AnalysisResult(
            score=88,
            summary="整体匹配度较高，主要短板是缺少实习经历",
            matched=["熟悉 FastAPI", "有 LLM 应用开发经验"],
            gaps=["缺少实习经历", "缺少高并发场景经验"],
            suggestions=["补充一段实习或开源贡献", "在项目里加一条压测数据"],
        )

    # patch 的是 analyzer 模块里的那个名字，
    # 因为 run_analysis_task 内部就是按这个名字去调的
    monkeypatch.setattr("app.services.analyzer.analyze", fake)


@pytest.fixture
def test_session_factory(test_engine, monkeypatch):
    """★ 把后台任务用的 SessionLocal 换成测试库。

    为什么必须单独做这件事：
      run_analysis_task 里是 `with SessionLocal() as db`，
      它不走 FastAPI 的依赖注入，所以 client fixture 里覆盖的
      get_db 对它【完全无效】。不 patch 的话，
      测试会往真实的 app.db 写数据。
    """
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("app.services.analyzer.SessionLocal", TestSession)
    return TestSession


def _register_and_login(client, email: str) -> str:
    client.post("/auth/register", json={"email": email, "password": "12345678"})
    response = client.post("/auth/login", json={"email": email, "password": "12345678"})
    return response.json()["access_token"]


def _create_resume(client, token: str) -> int:
    """建一份简历，返回 id。上传链路由 conftest 的 fake_pipeline 假掉。"""
    response = client.post(
        "/resumes",
        files={"file": ("cv.pdf", b"%PDF-fake", "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_start_analysis_returns_202(client, fake_pipeline, fake_analyze, test_session_factory):
    """触发分析 → 立刻返回 202。"""
    token = _register_and_login(client, "start@test.com")
    resume_id = _create_resume(client, token)

    response = client.post(
        f"/resumes/{resume_id}/analysis",
        json={"jd_text": JD},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 202
    # ↑ 202 = 已受理未完成。不是 200，也不是 201
    assert response.json()["resume_id"] == resume_id


def test_analysis_completes_with_result(client, fake_pipeline, fake_analyze, test_session_factory):
    """★ 后台任务跑完后，GET 能拿到 done 和完整结果。

    关键技术点：TestClient 会【同步等待后台任务执行完】，
    所以 POST 之后立刻 GET 就有结果 ——
    不用 sleep、不用轮询、不会因为时序问题偶发失败。
    """
    token = _register_and_login(client, "done@test.com")
    resume_id = _create_resume(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    client.post(f"/resumes/{resume_id}/analysis", json={"jd_text": JD}, headers=headers)

    response = client.get(f"/resumes/{resume_id}/analysis", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["score"] == 88
    assert body["result"]["summary"].startswith("整体匹配度较高")
    assert len(body["result"]["gaps"]) == 2


def test_get_analysis_before_any(client, fake_pipeline):
    """还没分析过就查 → 404。"""
    token = _register_and_login(client, "none@test.com")
    resume_id = _create_resume(client, token)

    response = client.get(
        f"/resumes/{resume_id}/analysis",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "还没有分析记录"


def test_cannot_analyze_others_resume(client, fake_pipeline, fake_analyze, test_session_factory):
    """★ 越权：B 不能触发 A 的简历分析。"""
    token_a = _register_and_login(client, "owner@test.com")
    token_b = _register_and_login(client, "intruder@test.com")
    resume_a = _create_resume(client, token_a)

    response = client.post(
        f"/resumes/{resume_a}/analysis",
        json={"jd_text": JD},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "简历不存在"


def test_jd_too_short(client, fake_pipeline):
    """JD 太短 → 422（Pydantic 拦截，不花 token）。"""
    token = _register_and_login(client, "short@test.com")
    resume_id = _create_resume(client, token)

    response = client.post(
        f"/resumes/{resume_id}/analysis",
        json={"jd_text": "招后端"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
