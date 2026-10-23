import pytest
from pydantic import ValidationError
from app.core.config import Settings

def test_setting_loads_from_env_file():
    s = Settings()
    assert s.app_name == "interview-agent"
    assert isinstance(s.jwt_expire_minutes,int)


def test_missing_api_key_raises():
    with pytest.raises(ValidationError):
        Settings(_env_file=None)