"""Application settings.

This module is the *only* place in the codebase that reads the environment. Every
other module receives a :class:`Settings` instance. That rule is what makes the app
testable: a test constructs its own Settings rather than mutating os.environ.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
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
    # In production the weights directory is a read-only mount, never a download
    # target. Setting this forces huggingface_hub offline, which turns a missing or
    # misdirected mount into an immediate error instead of a silent hang -- see
    # `_build_real_registry` for what that failure looked like before.
    require_local_weights: bool = False
    domains_file: Path = Path("src/biovision/domains/domains.yaml")
    gate_prompts_file: Path = Path("src/biovision/domains/gate.yaml")
    severity_prompts_file: Path = Path("src/biovision/domains/severity.yaml")
    regulation_file: Path = Path("src/biovision/domains/regulation.yaml")
    #: Mirrored TSB Kasko Değer Listesi, built by scripts/fetch_tsb_values.py.
    #: Absent, the API asks the user for a value rather than inventing one.
    tsb_value_list_file: Path = Path("../data/tsb/kasko_degerleri.sqlite")

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
    #: Specialist detection floor. 0.20 by measurement rather than by default:
    #: the sweep found no F1 optimum, so this is a stated trade of precision for
    #: recall. README section 7.3 carries the table.
    specialist_min_confidence: float = Field(default=0.20, ge=0.0, le=1.0)
    #: The SECOND specialist floor, used only for the damaged-area region and
    #: never to add a finding. 0.10 by measurement: pixel coverage of the
    #: annotated damage rises 0.715 -> 0.788 for 0.029 more spill, and the trade
    #: inverts below it. README section 7.9. Answering "how much of the car is
    #: damaged" and "which damages are you sure of" with one threshold means
    #: getting one of them wrong.
    specialist_region_confidence: float = Field(default=0.10, ge=0.0, le=1.0)

    #: The floor a finding must clear when the severity band says the car looks
    #: UNDAMAGED. Everywhere else `specialist_min_confidence` applies.
    #:
    #: 0.20 was chosen on damaged images only -- both published sweeps used sets
    #: that contained no intact cars, so neither could see a false alarm. Measured
    #: against 71 intact vehicles it fires on 44% of them. Raising the floor
    #: globally to 0.40 cuts that to 24% and costs 0.111 of instance recall;
    #: raising it only where a second signal disagrees cuts it to 20% and costs
    #: 0.009. README section 7.10.
    #:
    #: 0.50 is a STATED RULE, not a tuned optimum: when independent evidence says
    #: there is nothing here, only list a finding the detector holds more likely
    #: true than not. The sweep shows 0.90 would reach 11%, and picking that
    #: would be choosing a parameter by looking at the answer.
    specialist_strict_confidence: float = Field(default=0.50, ge=0.0, le=1.0)

    #: Look at the mirror image too, and union what it finds into the damaged
    #: region. Area only -- never findings, which would need cross-view NMS and
    #: would invalidate the published precision/recall table.
    #:
    #: On by measurement, not by preference: coverage 0.794 -> 0.854 for spill
    #: 0.407 -> 0.433, and a third of the previously-blind photographs gain an
    #: area (README 7.9). That a flip finds damage the original view missed is
    #: also the clearest evidence about what is wrong with this model: recall,
    #: not mask boundaries and not capacity.
    #:
    #: It costs ~198 ms, the largest single latency item here, and it is the
    #: first thing to turn off if the VPS p95 disappoints -- a figure not yet
    #: measured there.
    specialist_mirror_view: bool = True

    #: Locate the car so damage area can be reported as a fraction of the VEHICLE
    #: rather than of the photograph. Costs one extra CPU inference per request.
    #: Off makes `area_ratio_vehicle` null everywhere -- degraded, not broken.
    vehicle_extent_enabled: bool = True
    vehicle_extent_confidence: float = Field(default=0.15, ge=0.0, le=1.0)

    # --- upload limits ---
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    min_image_dimension: int = Field(default=200, gt=0)
    stored_long_edge: int = Field(default=1280, gt=0)

    # --- rate limiting ---
    anon_daily_limit: int = Field(default=20, ge=0)
    user_daily_limit: int = Field(default=100, ge=0)
    #: Accounts exempt from the daily quota, comma-separated. Intended for the
    #: operator's own account, so demonstrating the system cannot be cut off by
    #: the limit that protects it from everyone else.
    #:
    #: Deliberately a *list of addresses in configuration* rather than a flag on
    #: the user record: an exemption that lives in the database can be granted by
    #: anyone who can write to the database, and would not be visible to someone
    #: reading the deployment. This one is in `.env` next to the limits it
    #: overrides, and every use of it is logged.
    #:
    #: It does **not** exempt anyone from the VLM budget. That ceiling is about
    #: money leaving an account, and no email should be able to spend past it.
    unlimited_emails: str = ""

    # --- VLM fallback (Phase 6) ---
    # Each worker holds its own budget counter, so the monthly ceiling is divided
    # between them -- otherwise two workers would each spend the full limit and the
    # month would cost double. Must match the --workers value the server runs with.
    uvicorn_workers: int = Field(default=2, ge=1)

    vlm_enabled: bool = False
    #: Also describe images that a specialist already measured.
    #:
    #: Off by default, because it spends money on the path that has an answer.
    #: On, because a specialist answer can be thin where the model is weak: the
    #: vehicle specialist finds ~25% of dents, so a written-off car can come back
    #: as one finding, which reads as light damage to anyone who is not holding
    #: the per-class table. The description does not fix the measurement -- it
    #: sits beside it, still as `vlm_description`, still never a finding.
    vlm_augments_specialist: bool = False
    vlm_model: str = "claude-haiku-4-5"
    vlm_monthly_budget_usd: float = Field(default=5.00, ge=0.0)
    vlm_budget_warn_ratio: float = Field(default=0.80, ge=0.0, le=1.0)
    default_language: Literal["tr", "en"] = "tr"

    # --- data retention (Phase 7) ---
    retention_days: int = Field(default=7, gt=0)

    # --- secrets (unprefixed; still read only through this class) ---
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_jwt_secret: str = Field(default="", validation_alias="SUPABASE_JWT_SECRET")
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
    def unlimited_email_set(self) -> frozenset[str]:
        """Quota-exempt accounts, lowercased.

        Lowercased on both sides of the comparison because an address a user
        typed and an address a provider returns differ in case often enough that
        a case-sensitive match would silently fail to apply the exemption.
        """
        return frozenset(
            email.strip().lower() for email in self.unlimited_emails.split(",") if email.strip()
        )

    @property
    def domains_path(self) -> Path:
        return self._resolve(self.domains_file)

    @property
    def tsb_value_list_path(self) -> Path:
        return self._resolve(self.tsb_value_list_file)

    @property
    def regulation_path(self) -> Path:
        return self._resolve(self.regulation_file)

    @property
    def severity_prompts_path(self) -> Path:
        return self._resolve(self.severity_prompts_file)

    @property
    def gate_prompts_path(self) -> Path:
        return self._resolve(self.gate_prompts_file)

    @property
    def weights_path(self) -> Path:
        return self._resolve(self.weights_dir)

    @model_validator(mode="after")
    def _production_requires_local_weights(self) -> Self:
        """Production defaults to requiring local weights; an explicit value wins.

        Checking `model_fields_set` rather than the value itself is what keeps
        `BIOVISION_REQUIRE_LOCAL_WEIGHTS=false` meaningful in production -- useful
        on a first deploy where the operator genuinely does want the download.
        """
        if self.env == "production" and "require_local_weights" not in self.model_fields_set:
            object.__setattr__(self, "require_local_weights", True)
        return self

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
