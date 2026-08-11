"""Loading and validating `domains.yaml`.

The catalogue is read once at startup and held immutable. Every consumer -- the
router's candidate prompts, `/v1/domains`, the specialist lookup -- goes through
this object, so a domain cannot exist in one place and be missing from another.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Reserved: returned when the router is not confident enough to pick a domain.
#: Rejected as a catalogue key so the two states can never be confused.
RESERVED_KEYS = frozenset({"unknown"})


class DomainSpec(BaseModel):
    """One entry from `domains.yaml`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    specialist: str | None = None
    prompts: list[str] = Field(min_length=1)

    @field_validator("key")
    @classmethod
    def _not_reserved(cls, value: str) -> str:
        if value in RESERVED_KEYS:
            raise ValueError(f"'{value}' is reserved and cannot be used as a domain key")
        return value

    @property
    def has_specialist(self) -> bool:
        return self.specialist is not None


class DomainCatalogError(RuntimeError):
    """Raised when `domains.yaml` is missing, malformed, or internally inconsistent.

    Deliberately fatal at startup: a half-loaded catalogue would silently change
    which domains the router can predict, and that is not something to discover
    from a wrong answer in production.
    """


class DomainCatalog:
    """An immutable, ordered collection of domain specs."""

    def __init__(self, specs: list[DomainSpec]) -> None:
        if not specs:
            raise DomainCatalogError("domain catalogue is empty")

        keys = [spec.key for spec in specs]
        duplicates = {key for key in keys if keys.count(key) > 1}
        if duplicates:
            raise DomainCatalogError(f"duplicate domain keys: {sorted(duplicates)}")

        self._specs = tuple(specs)
        self._by_key = {spec.key: spec for spec in specs}

    # --- construction ---------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> DomainCatalog:
        if not path.is_file():
            raise DomainCatalogError(f"domain catalogue not found at {path}")
        try:
            raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise DomainCatalogError(f"{path} is not valid YAML: {exc}") from exc

        if not isinstance(raw, dict) or "domains" not in raw:
            raise DomainCatalogError(f"{path} must be a mapping containing a 'domains' key")

        entries = raw["domains"]
        if not isinstance(entries, list):
            raise DomainCatalogError(f"{path}: 'domains' must be a list")

        try:
            specs = [DomainSpec.model_validate(entry) for entry in entries]
        except Exception as exc:  # pydantic ValidationError, re-raised with context
            raise DomainCatalogError(f"{path}: invalid domain entry: {exc}") from exc

        return cls(specs)

    # --- access ---------------------------------------------------------

    def __len__(self) -> int:
        return len(self._specs)

    def __iter__(self) -> Any:
        return iter(self._specs)

    @property
    def specs(self) -> tuple[DomainSpec, ...]:
        return self._specs

    @property
    def keys(self) -> list[str]:
        return [spec.key for spec in self._specs]

    def get(self, key: str) -> DomainSpec | None:
        return self._by_key.get(key)

    def prompt_map(self) -> dict[str, list[str]]:
        """Zero-shot candidates per domain, consumed by the router in Phase 3."""
        return {spec.key: list(spec.prompts) for spec in self._specs}

    def with_specialist(self) -> list[DomainSpec]:
        return [spec for spec in self._specs if spec.has_specialist]
