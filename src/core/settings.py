import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Secrets
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-prod")

    # Configuration
    API_VERSION: str = "v1"
    CORS_ORIGINS: list[str] = ["*"]
    LOG_LEVEL: str = "DEBUG"
    ENVIRONMENT: str = "development"

    # JWT Configuration
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60 * 24 * 7  # 7 days

    # API Key Configuration
    API_KEY_LENGTH: int = 32

    class Config:
        env_file = ".env"


settings = Settings()
