from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ragproof"
    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://ragproof:ragproof@postgres:5432/ragproof"
    opensearch_url: str = "http://opensearch:9200"
    opensearch_index: str = "rag_documents"
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://ragproof:ragproof@rabbitmq:5672/"

    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    embedding_model: str = "baai/bge-m3"
    embedding_dim: int = 1024
    llm_model: str = "nvidia/nemotron-3-super-120b-a12b"


@lru_cache
def get_settings() -> Settings:
    return Settings()
