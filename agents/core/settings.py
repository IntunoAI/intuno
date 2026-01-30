"""Settings for the agents project."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Agent app configuration."""

    DATABASE_URL: str = ""
    OPENAI_API_KEY: str = ""
    AGENT_CHAT_MODEL: str = "gpt-4o-mini"
    AGENTS_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
