from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Secrets
    DATABASE_URL: str = ""
    OPENAI_API_KEY: str = ""
    JWT_SECRET_KEY: str = "dev-secret-change-in-prod"

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

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",  # Ignore extra environment variables
        case_sensitive=False,  # Allow case-insensitive env vars
    )


settings = Settings()
