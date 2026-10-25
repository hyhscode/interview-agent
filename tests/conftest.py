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


@pytest.fixture
def test_settings():
    return Settings(
        _env_file=None,                     # 关键：不读 .env 文件
        app_name="interview-agent-test",    # 显式传参，优先级最高
        app_env="test",                     # 真实 .env 里是 dev，这里故意写 test
        deepseek_api_key="test-key",        # 假 Key，不会真的去调 API
        siliconflow_api_key="test-key",
        jwt_secret_key="test-secret",    
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
            jwt_secret_key="test-secret",
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