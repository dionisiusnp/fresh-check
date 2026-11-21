from enum import Enum
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppMode(str, Enum):
    DEMO = "demo"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_mode: AppMode = AppMode.DEMO

    bifrost_base_url: str = "http://localhost:8080"
    bifrost_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    tavily_api_key: str = ""
    tavily_max_results: int = 3
    tavily_rate_limit_rpm: int = 10


settings = Settings()
