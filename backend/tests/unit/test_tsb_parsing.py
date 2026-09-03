"""Reading one cell of the TSB workbook as lira.

Every write-off line, both payout branches and the trafik shortfall are ratios
against the number this function returns. It is the single highest-leverage
parse in the codebase and its failure mode is silent — a wrong value is still a
plausible-looking amount of money.

**The test that matters is the float one.** The original implementation was
`int(float(str(cell).replace(".", "").replace(",", ".")))`, which is correct for
every cell in the August 2026 list because openpyxl hands back Python `int`s. Had
one arrived as a float, `1584880.0` would have become the string "1584880.0",
lost its dot to the thousand-separator strip, and been stored as 15,848,800 —
ten times the real value, on the figure the whole product divides by. Nothing
would have looked wrong.
"""

from __future__ import annotations

import pytest
from scripts.fetch_tsb_values import PLAUSIBLE_TRY, parse_amount


def test_an_integer_cell_is_taken_as_written() -> None:
    """The real case: every cell in the August 2026 list is an int."""
    assert parse_amount(1584880) == 1584880


def test_a_float_cell_is_not_multiplied_by_ten() -> None:
    """The trap. See the module docstring; this is why the function exists."""
    assert parse_amount(1584880.0) == 1584880


def test_a_fractional_float_rounds_rather_than_truncating() -> None:
    assert parse_amount(1584880.6) == 1584881


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.584.880", 1584880),
        ("1.584.880,00", 1584880),
        ("1.584.880,50", 1584880),
        ("1584880", 1584880),
    ],
)
def test_turkish_number_formatting_is_read_correctly(text: str, expected: int) -> None:
    """Only reachable when a genuine string arrives — a dot is a thousand mark."""
    assert parse_amount(text) == expected


def test_zero_means_the_vehicle_was_not_sold_that_year() -> None:
    """TSB writes a literal 0, not a blank.

    339,210 of the 418,590 year cells in the August 2026 list are zeros. Storing
    them would let a lookup answer "worth nothing" for a car that simply did not
    exist that model year, and every ratio against it would be a division by a
    lie rather than a division by zero — which at least raises.
    """
    assert parse_amount(0) is None


@pytest.mark.parametrize("cell", [None, "", "   ", "-", "n/a", "yok"])
def test_an_absent_or_unreadable_cell_is_none(cell: object) -> None:
    assert parse_amount(cell) is None


def test_a_boolean_is_never_a_price() -> None:
    """`bool` is an `int` subclass, so it would otherwise parse as 1 lira."""
    assert parse_amount(True) is None
    assert parse_amount(False) is None


def test_a_negative_value_is_refused() -> None:
    assert parse_amount(-5000) is None


def test_the_plausibility_band_would_catch_a_tenfold_shift() -> None:
    """The build's second guard, asserted here so the band cannot quietly widen.

    A ten-fold error on the most expensive vehicle in the list (105,777,121 TL)
    lands above the ceiling and stops the build. One on the cheapest (6,116 TL)
    lands below the floor going the other way.
    """
    floor, ceiling = PLAUSIBLE_TRY
    assert floor < 6_116, "the cheapest real vehicle must pass"
    assert ceiling > 105_777_121, "the most expensive real vehicle must pass"
    assert ceiling < 105_777_121 * 10, "a tenfold error must not pass"
    assert floor > 6_116 // 10, "a tenfold error the other way must not pass"
