import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_settings_ignores_real_env_file(test_settings):
    # ↑ 参数名 = fixture 名，pytest 自动把返回值传进来，不用自己调用它
    assert test_settings.app_env == "test"
    # ↑ 这条断言的意义：真实 .env 里 app_env 是 "dev"，
    #   这里能拿到 "test"，就证明【测试没读真实 .env】—— 隔离成功


def test_jwt_expire_is_int(test_settings):
    assert isinstance(test_settings.jwt_expire_minutes, int)
    # ↑ 测类型转换：字符串 "120" 必须变成整数


def test_missing_api_key_raises():
    with pytest.raises(ValidationError):
        Settings(_env_file=None)