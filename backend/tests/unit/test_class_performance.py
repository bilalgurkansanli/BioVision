"""The published per-class numbers and the ones the API returns must be the same.

Two copies of a measurement drift. This asserts they have not, by reading the
README table rather than trusting a second transcription of it.
"""

from __future__ import annotations

import re

from biovision.config import BACKEND_ROOT
from biovision.models.class_performance import VEHICLE_CLASS_PERFORMANCE
from biovision.schemas.enums import DamageType

README = BACKEND_ROOT.parent / "README.md"

#: `| glass_shatter | 2,221 | **0.782** | 0.522 | 0.797 | 0.747 |`
ROW = re.compile(
    r"^\|\s*(?P<name>[a-z_]+)\s*\|\s*[\d,]+\s*\|\s*\*{0,2}(?P<map50>[\d.]+)\*{0,2}\s*\|"
    r"\s*[\d.]+\s*\|\s*(?P<precision>[\d.]+)\s*\|\s*(?P<recall>[\d.]+)\s*\|",
    re.MULTILINE,
)


#: `crack` is emitted by the building specialist, measured on METU/Ozgenel, and
#: deliberately absent from this table. Putting a METU recall in a VehiDE table
#: would merge two datasets into one number, which is the conflation this
#: project exists to refuse -- the building specialist carries its own figures,
#: including the 15-of-15 false-alarm count that argued against connecting it.
NOT_MEASURED_ON_VEHIDE = {DamageType.CRACK}


def test_every_vehicle_damage_class_has_measured_numbers() -> None:
    """A class missing here returns null rather than a wrong figure -- but no
    class the vehicle specialist can emit should be missing."""
    assert set(VEHICLE_CLASS_PERFORMANCE) == set(DamageType) - NOT_MEASURED_ON_VEHIDE


def test_a_class_from_another_dataset_is_not_given_vehide_numbers() -> None:
    """The table must stay silent about classes VehiDE never contained."""
    for damage_type in NOT_MEASURED_ON_VEHIDE:
        assert damage_type not in VEHICLE_CLASS_PERFORMANCE


def test_the_api_returns_what_the_readme_publishes() -> None:
    published = {
        match.group("name"): match for match in ROW.finditer(README.read_text(encoding="utf-8"))
    }
    assert published, "README section 7.3 per-class table not found -- did its shape change?"

    for damage_type, measured in VEHICLE_CLASS_PERFORMANCE.items():
        row = published.get(damage_type.value)
        assert row is not None, f"{damage_type.value} is in the code but not the README table"

        assert measured.map50 == float(row.group("map50")), damage_type.value
        assert measured.recall == float(row.group("recall")), damage_type.value
        assert measured.precision == float(row.group("precision")), damage_type.value


def test_the_weak_classes_are_marked_unreliable() -> None:
    """The three classes README section 7.3 calls out must not read as usable.

    `scratch` at 0.239 mAP with six times the training data of the best class is
    the finding that table exists to show. A response that presented it the same
    way as `glass_shatter` at 0.782 would be hiding it again.
    """
    for weak in (DamageType.SCRATCH, DamageType.DENT, DamageType.TORN):
        assert VEHICLE_CLASS_PERFORMANCE[weak].reliable is False, weak.value

    for usable in (DamageType.GLASS_SHATTER, DamageType.MISSING_PART):
        assert VEHICLE_CLASS_PERFORMANCE[usable].reliable is True, usable.value
