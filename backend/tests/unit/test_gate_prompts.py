"""The gate prompt catalogue."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from biovision.config import BACKEND_ROOT
from biovision.domains.catalog import DomainCatalogError
from biovision.domains.gate import GatePrompts

REAL_PATH = BACKEND_ROOT / "src" / "biovision" / "domains" / "gate.yaml"


def test_the_shipped_catalogue_loads() -> None:
    prompts = GatePrompts.load(REAL_PATH)

    assert prompts.in_distribution
    assert prompts.out_of_distribution


def test_out_of_distribution_covers_what_people_actually_upload() -> None:
    """The harder half: accidental uploads are selfies and screenshots."""
    joined = " ".join(GatePrompts.load(REAL_PATH).out_of_distribution).lower()

    for expected in ("selfie", "screenshot", "landscape", "food", "document"):
        assert expected in joined, f"the gate has no prompt covering {expected}"


def test_prompt_order_defines_the_softmax_indices() -> None:
    """`all_prompts` must put the in-distribution group first, contiguously."""
    prompts = GatePrompts.load(REAL_PATH)
    combined = prompts.all_prompts

    assert combined[: prompts.in_distribution_count] == prompts.in_distribution
    assert combined[prompts.in_distribution_count :] == prompts.out_of_distribution
    assert len(combined) == len(prompts.in_distribution) + len(prompts.out_of_distribution)


def test_a_missing_file_is_fatal(tmp_path: Path) -> None:
    with pytest.raises(DomainCatalogError, match="not found"):
        GatePrompts.load(tmp_path / "absent.yaml")


def test_malformed_yaml_is_fatal(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text("in_distribution: [unclosed", encoding="utf-8")

    with pytest.raises(DomainCatalogError):
        GatePrompts.load(path)


@pytest.mark.parametrize(
    "document",
    [
        {"in_distribution": [], "out_of_distribution": ["a selfie"]},
        {"in_distribution": ["a car"], "out_of_distribution": []},
        {"in_distribution": ["a car"]},
    ],
)
def test_an_empty_group_is_rejected(document: dict[str, object], tmp_path: Path) -> None:
    """A one-sided softmax compares each prompt against nothing."""
    path = tmp_path / "gate.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(DomainCatalogError):
        GatePrompts.load(path)
