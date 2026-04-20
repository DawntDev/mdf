"""Global application configuration.

All runtime configuration is exposed through a single :class:`Settings`
instance read from environment variables. This module never calls
``load_dotenv`` — that responsibility belongs exclusively to ``main.py``.

Usage
-----
>>> from core.config import get_settings
>>> settings = get_settings()
>>> settings.available_providers()
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    MISTRAL = "mistral"


class Settings(BaseSettings):
    """Typed runtime settings sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=None,  # .env loading is handled exclusively by main.py
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    max_upload_mb: int = Field(default=50, ge=1, le=500)

    # LLM provider API keys (SecretStr so they never appear in repr/logs)
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    mistral_api_key: SecretStr | None = None

    # OCR (automatic fallback)
    tesseract_cmd: str | None = None
    ocr_languages: str = "spa+eng"
    ocr_dpi: int = Field(default=300, ge=72, le=600)

    # Extraction heuristics
    pdf_image_text_ratio_threshold: float = Field(default=0.02, ge=0.0)
    pdf_page_sample_size: int = Field(default=5, ge=1, le=50)

    # Agent
    agent_max_retries: int = Field(default=2, ge=0, le=5)
    agent_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    agent_max_concurrency: int = Field(default=5, ge=1, le=32)

    @field_validator("tesseract_cmd", mode="before")
    @classmethod
    def _empty_to_none(cls, v: str | None) -> str | None:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------
    def available_providers(self) -> list[LLMProvider]:
        """Return providers that have a non-empty API key configured."""
        mapping: dict[LLMProvider, SecretStr | None] = {
            LLMProvider.OPENAI: self.openai_api_key,
            LLMProvider.ANTHROPIC: self.anthropic_api_key,
            LLMProvider.GOOGLE: self.google_api_key,
            LLMProvider.MISTRAL: self.mistral_api_key,
        }
        return [p for p, key in mapping.items() if key and key.get_secret_value()]

    def api_key_for(self, provider: LLMProvider) -> str | None:
        attr = {
            LLMProvider.OPENAI: self.openai_api_key,
            LLMProvider.ANTHROPIC: self.anthropic_api_key,
            LLMProvider.GOOGLE: self.google_api_key,
            LLMProvider.MISTRAL: self.mistral_api_key,
        }[provider]
        return attr.get_secret_value() if attr else None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()
