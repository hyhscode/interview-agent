from functools import lru_cache

from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):
    app_env:str = "dev"
    app_name:str = "interview-agent"
    deepseek_api_key: str
    deepseek_base_url:str ="https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    siliconflow_api_key: str
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    database_url: str = "sqlite:///./app.db"
    jwt_secret_key: str
    jwt_expire_minutes:int = 120
    model_config = SettingsConfigDict(
        env_file=".env",             # 去当前工作目录的 .env 文件读
        env_file_encoding="utf-8",   # 用 utf-8 解码，否则中文可能乱码
        case_sensitive=False,        # 名字不区分大小写：DEEPSEEK_API_KEY 等同 deepseek_api_key
        extra="ignore",              # .env 里出现我没定义的键？忽略，不报错
    )

@lru_cache
def get_settings() ->Settings:
    return Settings()