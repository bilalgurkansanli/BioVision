"""Loading `severity.yaml`.

Separate from the gate and the domain catalogue for the same reason those are
separate from each other: the three change for different reasons. Severity bands
follow how an assessor talks about damage; the gate's list follows what people
upload by mistake.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from biovision.domains.catalog import DomainCatalogError
from biovision.schemas.enums import Severity


class SeverityPrompts(BaseModel):
    """Prompt ensembles, one per severity band."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bands: dict[Severity, list[str]] = Field(min_length=1)

    @model_validator(mode="after")
    def _every_band_is_covered(self) -> Self:
        missing = set(Severity) - set(self.bands)
        if missing:
            # A band with no prompts can never be predicted, so the API would
            # silently lose an outcome it advertises in its schema.
            raise ValueError(f"severity bands missing prompts: {sorted(b.value for b in missing)}")
        empty = [band.value for band, prompts in self.bands.items() if not prompts]
        if empty:
            raise ValueError(f"severity bands with an empty prompt list: {sorted(empty)}")
        return self

    @property
    def band_order(self) -> list[Severity]:
        """Fixed order, so a softmax index always means the same band."""
        return [Severity.NONE, Severity.MINOR, Severity.MODERATE, Severity.SEVERE]

    def prompts_for(self, band: Severity) -> list[str]:
        return self.bands[band]

    @classmethod
    def load(cls, path: Path) -> SeverityPrompts:
        if not path.is_file():
            raise DomainCatalogError(f"severity prompts not found at {path}")
        try:
            raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            raise DomainCatalogError(
                f"severity prompts at {path} are not valid YAML: {error}"
            ) from error
        try:
            return cls.model_validate({"bands": raw.get("bands", {})})
        except ValueError as error:
            raise DomainCatalogError(f"severity prompts at {path} are invalid: {error}") from error
