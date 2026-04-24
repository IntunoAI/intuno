from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Secrets
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    OPENAI_API_KEY: str = ""
    JWT_SECRET_KEY: str = ""

    # Configuration
    API_VERSION: str = "v1"
    BASE_URL: str = "https://api.intuno.net"
    CORS_ORIGINS: list[str] = ["*"]
    LOG_LEVEL: str = "DEBUG"
    ENVIRONMENT: str = "development"

    # JWT Configuration
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60 * 24 * 7  # 7 days

    # API Key Configuration
    API_KEY_LENGTH: int = 32

    # ── Database connection pool ────────────────────────────────────────
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 3600  # seconds

    # ── HTTP client pool (broker → agent invocations) ─────────────────
    BROKER_HTTP_POOL_SIZE: int = 100  # max keepalive connections
    BROKER_HTTP_MAX_CONNECTIONS: int = 200

    # ── Embedding provider ────────────────────────────────────────────
    EMBEDDING_PROVIDER: str = "openai"  # "openai" | "ollama"
    EMBEDDING_URL: str = "http://localhost:11434"  # Ollama base URL
    EMBEDDING_CACHE_TTL: int = 3600  # seconds; 0 = no cache

    # Redis Configuration (for caching; empty = no cache)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Dashboard cache TTL in seconds (0 = no cache)
    DASHBOARD_CACHE_TTL: int = 120

    # Qdrant Configuration
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    # LLM Enhancement Configuration
    ENABLE_LLM_ENHANCEMENT: bool = True  # Default to True for cost/latency reasons
    LLM_ENHANCEMENT_MODEL: str = "gpt-4o-mini"

    # Planner: when True, use LLM to decompose goal into multiple steps; when False, single-step
    PLANNER_USE_LLM: bool = False
    PLANNER_LLM_MODEL: str = "gpt-4o-mini"

    # Brand agent: LLM for conversational responses (uses OPENAI_API_KEY)
    BRAND_AGENT_LLM_MODEL: str = "gpt-4o-mini"
    # Placeholder invoke URL for brand agents (never called; add to INVOKE_ENDPOINT_ALLOWED_HOSTS if needed)
    BRAND_AGENT_PLACEHOLDER_URL: str = "https://brand-agent.internal/"

    # Embedding Configuration
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_VERSION: str = "1.0"  # Version of embedding structure/format

    # Brand verification email (Resend provider)
    RESEND_API_KEY: str = ""
    EMAIL_FROM_ADDRESS: str = "noreply@example.com"
    EMAIL_FROM_NAME: str = "Intuno"
    BRAND_VERIFICATION_CODE_EXPIRY_MINUTES: int = 15

    # Task (orchestrator) timeout – global task-level timeout in seconds
    TASK_TIMEOUT_SECONDS: int = 60

    # SSRF protection: comma-separated host patterns for invoke_endpoint (e.g. "*.example.com").
    # Empty = allow public IPs only (reject private/loopback).
    INVOKE_ENDPOINT_ALLOWED_HOSTS: str = ""

    # Encryption key for per-agent credentials (defaults to JWT_SECRET_KEY-derived if empty)
    CREDENTIALS_ENCRYPTION_KEY: str = ""

    # ── Rate limiting ─────────────────────────────────────────────────────
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 120

    # Orchestrator fallback: when discovery returns no candidates, use this agent
    ORCHESTRATOR_FALLBACK_AGENT_ID: Optional[str] = None

    # ── Workflow settings (from agent-os) ──────────────────────────────
    WORKFLOW_CONTEXT_BUS_TTL_SECONDS: int = 86400
    WORKFLOW_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    WORKFLOW_CIRCUIT_BREAKER_WINDOW_SECONDS: int = 60
    WORKFLOW_CIRCUIT_BREAKER_COOLDOWN_SECONDS: int = 300
    WORKFLOW_DEFAULT_MAX_DURATION_SECONDS: int = 300
    WORKFLOW_DEFAULT_MAX_CONCURRENT_PER_AGENT: int = 10
    WORKFLOW_DEFAULT_MAX_CONCURRENT_EXECUTIONS: int = 5

    # ── Network settings (communication networks) ─────────────────────
    NETWORK_CONTEXT_TTL_SECONDS: int = 86400 * 7  # 7 days
    NETWORK_CONTEXT_MAX_ENTRIES: int = 500  # max messages in Redis context stream
    NETWORK_MAX_PARTICIPANTS: int = 50
    NETWORK_CALLBACK_TIMEOUT_SECONDS: int = 30
    NETWORK_MESSAGE_DELIVERY_MAX_RETRIES: int = 3

    # ── Safety & Governance ─────────────────────────────────────────────
    SAFETY_CHECK_ENABLED: bool = True
    AGENT_STATUS_CACHE_TTL: int = 300  # seconds to cache agent active status in Redis

    # ── Intuno Personal (hosted entity service — wisdom-agents proxy) ──
    # wisdom proxies /personal/entities/* to wisdom-agents, which is a
    # private internal service (never exposed to the public internet).
    INTUNO_AGENTS_BASE_URL: str = "http://localhost:8001"
    INTUNO_AGENTS_API_KEY: str = ""  # shared secret; the same AGENTS_API_KEY from wisdom-agents
    INTUNO_AGENTS_TIMEOUT_SECONDS: float = 30.0
    INTUNO_AGENTS_CHAT_TIMEOUT_SECONDS: float = 60.0  # chat waits on LLM response
    PERSONAL_FREE_TIER_ENTITY_CAP: int = 1  # entities allowed on Free plan — Pro is handled separately

    # Service credential for wisdom-agents to make network/registry/broker
    # calls on behalf of a specific user (the entity's owner). Not tied to
    # any user account; set once per deployment. Paired with an X-On-Behalf-Of
    # header containing the target user UUID. See get_current_user_or_service.
    AGENTS_SERVICE_API_KEY: str = ""

    # ── Economy settings (from agent-economy) ──────────────────────────
    ECONOMY_WELCOME_BONUS_CREDITS: int = 500
    ECONOMY_CREDIT_PACKAGES: list[dict] = [
        {"id": "starter", "credits": 500, "price_cents": 500, "label": "$5"},
        {"id": "pro", "credits": 1200, "price_cents": 1000, "label": "$10"},
        {"id": "enterprise", "credits": 5000, "price_cents": 3500, "label": "$35"},
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",  # Ignore extra environment variables
        case_sensitive=False,  # Allow case-insensitive env vars
    )


settings = Settings()
