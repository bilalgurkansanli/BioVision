"""The severity prompt file, and the invariants that keep it honest."""

from __future__ import annotations

from pathlib import Path

import pytest

from biovision.config import Settings
from biovision.domains.catalog import DomainCatalogError
from biovision.domains.severity import SeverityPrompts
from biovision.schemas.enums import Severity


def test_the_shipped_file_loads_and_covers_every_band(settings: Settings) -> None:
    prompts = SeverityPrompts.load(settings.severity_prompts_path)

    assert set(prompts.bands) == set(Severity)
    for band in Severity:
        assert prompts.prompts_for(band), band.value


def test_a_missing_band_is_refused(tmp_path: Path) -> None:
    """A band with no prompts can never be predicted.

    The API advertises three outcomes in its schema; silently losing one would
    mean a band that is unreachable rather than merely rare.
    """
    path = tmp_path / "severity.yaml"
    path.write_text("bands:\n  minor: ['a']\n  moderate: ['b']\n", encoding="utf-8")

    with pytest.raises(DomainCatalogError, match="missing prompts"):
        SeverityPrompts.load(path)


def test_an_empty_prompt_list_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "severity.yaml"
    path.write_text(
        "bands:\n  minor: ['a']\n  moderate: []\n  severe: ['c']\n", encoding="utf-8"
    )

    with pytest.raises(DomainCatalogError, match="empty prompt list"):
        SeverityPrompts.load(path)


def test_band_order_is_fixed() -> None:
    """The softmax index must always mean the same band.

    Reordering this list silently relabels every estimate, the same failure the
    damage-class order guards against.
    """
    prompts = SeverityPrompts(bands={band: ["x"] for band in Severity})
    assert prompts.band_order == [Severity.MINOR, Severity.MODERATE, Severity.SEVERE]


def test_a_missing_file_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(DomainCatalogError, match="not found"):
        SeverityPrompts.load(tmp_path / "nope.yaml")
