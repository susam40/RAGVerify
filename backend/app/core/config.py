from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ragproof"
    app_env: str = "development"
    log_level: str = "INFO"

    fetch_timeout_seconds: float = 20.0
    fetch_connect_timeout_seconds: float = 10.0
    fetch_max_bytes: int = 5_000_000
    fetch_max_retries: int = 2
    fetch_ssl_verify: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
