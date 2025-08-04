from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    DATABASE_URL: str = os.environ.get('DATABASE_URL')
    API_VERSION: str = "v1"
    CORS_ORIGINS: list[str] = [
        "*"
    ]
    LOG_LEVEL: str = "DEBUG"
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"

settings = Settings()
