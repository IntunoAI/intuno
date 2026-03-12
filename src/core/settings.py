from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Secrets
    DATABASE_URL: str = ""
    OPENAI_API_KEY: str = ""
    SAPTIVA_API_KEY: str = ""
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

    # Qdrant Configuration
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    # LLM Enhancement Configuration
    ENABLE_LLM_ENHANCEMENT: bool = False  # Default to False for cost/latency reasons
    LLM_ENHANCEMENT_MODEL: str = "gpt-4o-mini"

    # Planner: when True, use LLM to decompose goal into multiple steps; when False, single-step
    PLANNER_USE_LLM: bool = False
    PLANNER_LLM_MODEL: str = "gpt-4o-mini"
    
    # Embedding Configuration
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_VERSION: str = "1.0"  # Version of embedding structure/format

    # Brand verification (email code expiry; provider config added later)
    BRAND_VERIFICATION_CODE_EXPIRY_MINUTES: int = 15

    # Task (orchestrator) timeout – global task-level timeout in seconds
    TASK_TIMEOUT_SECONDS: int = 60

    # Shared secret sent as X-API-Key when the broker calls agent invoke endpoints
    AGENTS_API_KEY: str = ""

    # Orchestrator fallback: when discovery returns no candidates, use this agent (and optionally capability)
    ORCHESTRATOR_FALLBACK_AGENT_ID: Optional[str] = None
    ORCHESTRATOR_FALLBACK_CAPABILITY_ID: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",  # Ignore extra environment variables
        case_sensitive=False,  # Allow case-insensitive env vars
    )


settings = Settings()
