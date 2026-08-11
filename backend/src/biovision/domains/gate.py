"""Loading `gate.yaml`.

Kept separate from the domain catalogue because the two answer different questions
and change for different reasons: domains are the product's surface area, while the
gate's prompt list grows in response to whatever people upload by mistake.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from biovision.domains.catalog import DomainCatalogError


class GatePrompts(BaseModel):
    """The two prompt groups the gate scores an image against."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    in_distribution: list[str] = Field(min_length=1)
    out_of_distribution: list[str] = Field(min_length=1)

    @property
    def all_prompts(self) -> list[str]:
        """Both groups, in-distribution first. Order defines the softmax indices."""
        return [*self.in_distribution, *self.out_of_distribution]

    @property
    def in_distribution_count(self) -> int:
        return len(self.in_distribution)

    @classmethod
    def load(cls, path: Path) -> GatePrompts:
        if not path.is_file():
            raise DomainCatalogError(f"gate prompts not found at {path}")
        try:
            raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise DomainCatalogError(f"{path} is not valid YAML: {exc}") from exc

        if not isinstance(raw, dict):
            raise DomainCatalogError(f"{path} must be a mapping")

        try:
            return cls.model_validate(
                {
                    "in_distribution": raw.get("in_distribution"),
                    "out_of_distribution": raw.get("out_of_distribution"),
                }
            )
        except Exception as exc:
            raise DomainCatalogError(f"{path}: invalid gate prompts: {exc}") from exc
