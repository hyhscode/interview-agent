import pytest

from app.core.config import Settings, get_settings
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as models
from app.db.session import Base, get_db
from app.main import app

from app.schemas.resume import Project, ResumeParsed


@pytest.fixture
def test_settings():
    return Settings(
        _env_file=None,                     # 关键：不读 .env 文件
        app_name="interview-agent-test",    # 显式传参，优先级最高
        app_env="test",                     # 真实 .env 里是 dev，这里故意写 test
        deepseek_api_key="test-key",        # 假 Key，不会真的去调 API
        siliconflow_api_key="test-key",
        jwt_secret_key="test-secret-key-for-unit-tests-32chars",    
    )

@pytest.fixture
def override_settings():
    def fake_settings():
        return Settings(
            _env_file=None,
            app_name="interview-agent-test",
            app_env="overridden",           # 故意用一个特殊值，方便断言
            deepseek_api_key="test-key",
            siliconflow_api_key="test-key",
            jwt_secret_key="test-secret-key-for-unit-tests-32chars",
        )
    app.dependency_overrides[get_settings] = fake_settings
    yield
    app.dependency_overrides.clear()

@pytest.fixture
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread":False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()

@pytest.fixture
def client(test_engine):
    TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def fake_pipeline(monkeypatch):
    """把「抽 PDF 文字」和「LLM 解析」两步都换成假的。

    放在 conftest 里，因为 test_resume.py 和 test_analysis.py 都要用。
    patch 的目标路径是"【使用它的模块】.函数名"，不是"定义它的模块"。
    """

    def fake_extract(pdf_bytes):
        # 长度必须 > 50，否则会被"扫描件"判定拦住（那个阈值是 50 字符）
        return (
            "张三 某某大学 软件工程 专业技能 Python FastAPI MySQL Redis Docker "
            "项目经历 校园二手交易平台 负责后端开发",
            2,
        )

    def fake_parse(text):
        return (
            ResumeParsed(
                name="张三",
                skills=["Python", "FastAPI"],
                projects=[
                    Project(name="某项目", tech=["FastAPI"], highlights=["做了点什么"])
                ],
            ),
            100,   # 假输入 token
            50,    # 假输出 token
        )

    monkeypatch.setattr("app.routers.resumes.pdf_service.extract_text", fake_extract)
    monkeypatch.setattr("app.routers.resumes.resume_parser.parse_resume", fake_parse)