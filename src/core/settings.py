import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Secrets
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")

    # Configuration
    API_VERSION: str = "v1"
    CORS_ORIGINS: list[str] = ["*"]
    LOG_LEVEL: str = "DEBUG"
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"


settings = Settings()
