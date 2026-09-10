"""Application settings, loaded once from the environment.

Everything configurable lives here. Two settings carry real weight:

  ai_provider    - 'gemini' | 'openai' | 'mock'. Tests and CI force 'mock', which
                   is how the suite stays deterministic and free.
  ai_budget_usd  - the hard spend ceiling enforced in app/ai/budget.py *before*
                   any provider call is made.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "AI-Powered Customer Complaint Management System"
    api_v1_prefix: str = "/api/v1"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = True

    # ── Database ─────────────────────────────────────────────────────────────
    postgres_user: str = "ccms"
    postgres_password: str = "ccms_dev_password"
    postgres_db: str = "ccms"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url_override: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """SQLAlchemy URL. The override exists so tests can point at SQLite."""
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Auth ─────────────────────────────────────────────────────────────────
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(default=["http://localhost:5173", "http://127.0.0.1:5173"])

    # ── AI provider ──────────────────────────────────────────────────────────
    ai_provider: Literal["gemini", "openai", "mock"] = "mock"
    google_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-nano"

    # ── Cost governor ────────────────────────────────────────────────────────
    ai_budget_usd: float = 0.70
    ai_cache_enabled: bool = True
    ai_recursion_limit: int = 8
    ai_max_output_tokens: int = 2048

    # ── Uploads ──────────────────────────────────────────────────────────────
    upload_dir: str = "uploads"
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB, matches the UI's stated limit


@lru_cache
def get_settings() -> Settings:
    """Cached accessor. Import this, never instantiate Settings directly."""
    return Settings()
