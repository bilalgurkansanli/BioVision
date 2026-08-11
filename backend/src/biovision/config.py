"""Application settings.

This module is the *only* place in the codebase that reads the environment. Every
other module receives a :class:`Settings` instance. That rule is what makes the app
testable: a test constructs its own Settings rather than mutating os.environ.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .../backend -- settings that hold relative paths resolve against this.
BACKEND_ROOT = Path(__file__).resolve().parents[2]

ModelBackend = Literal["mock", "real"]


class Settings(BaseSettings):
    """Runtime configuration, loaded from the environment and `.env`."""

    model_config = SettingsConfigDict(
        env_prefix="BIOVISION_",
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # `model_backend` would otherwise collide with pydantic's protected
        # "model_" namespace and emit a warning on every import.
        protected_namespaces=(),
    )

    # --- application ---
    env: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # --- model backend ---
    # "mock" loads deterministic stand-ins: no weights, no network, sub-second boot.
    # CI runs exclusively against "mock"; "real" arrives in Phase 3.
    model_backend: ModelBackend = "mock"
    weights_dir: Path = Path("weights")
    domains_file: Path = Path("src/biovision/domains/domains.yaml")
    gate_prompts_file: Path = Path("src/biovision/domains/gate.yaml")

    # --- zero-shot encoder (Phase 3) ---
    clip_model: str = "ViT-B-32"
    clip_pretrained: str = "laion2b_s34b_b79k"
    # torch defaults to one thread per core. With two workers on four vCPUs, each
    # would spawn four and the eight would contend for the same cores -- measurably
    # slower than not parallelising at all.
    torch_num_threads: int = Field(default=2, ge=1)

    # --- thresholds ---
    # Placeholders until Phase 4 derives them from the calibration split. They are
    # never tuned against the test set; that would invalidate the reported numbers.
    gate_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    router_min_confidence: float = Field(default=0.45, ge=0.0, le=1.0)

    # --- upload limits ---
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    min_image_dimension: int = Field(default=200, gt=0)
    stored_long_edge: int = Field(default=1280, gt=0)

    # --- rate limiting ---
    anon_daily_limit: int = Field(default=20, ge=0)
    user_daily_limit: int = Field(default=100, ge=0)

    # --- VLM fallback (Phase 6) ---
    vlm_enabled: bool = False
    vlm_model: str = "claude-haiku-4-5-20251001"
    vlm_monthly_budget_usd: float = Field(default=5.00, ge=0.0)
    vlm_budget_warn_ratio: float = Field(default=0.80, ge=0.0, le=1.0)
    default_language: Literal["tr", "en"] = "tr"

    # --- data retention (Phase 7) ---
    retention_days: int = Field(default=7, gt=0)

    # --- secrets (unprefixed; still read only through this class) ---
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", validation_alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(
        default="", validation_alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    supabase_storage_bucket: str = Field(
        default="biovision-images", validation_alias="SUPABASE_STORAGE_BUCKET"
    )

    @field_validator("log_level")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list.

        Kept as a comma-separated string on the model because pydantic-settings
        parses `list[str]` env values as JSON, which makes `.env` files awkward.
        """
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def domains_path(self) -> Path:
        return self._resolve(self.domains_file)

    @property
    def gate_prompts_path(self) -> Path:
        return self._resolve(self.gate_prompts_file)

    @property
    def weights_path(self) -> Path:
        return self._resolve(self.weights_dir)

    @staticmethod
    def _resolve(path: Path) -> Path:
        return path if path.is_absolute() else BACKEND_ROOT / path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton.

    Cached because it is resolved on every request through a FastAPI dependency;
    re-reading `.env` per request would be pure waste. Tests bypass this by
    constructing `Settings(...)` directly and overriding the dependency.
    """
    return Settings()
