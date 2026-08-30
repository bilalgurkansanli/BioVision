"""Vehicle values from the mirrored TSB Kasko Değer Listesi.

Read-only over the SQLite file `scripts/fetch_tsb_values.py` builds. Absent that
file the module reports itself unavailable and the API asks the user for a value
instead -- which is a worse experience and a correct one. Substituting an average,
or the nearest model year, would put a confident number under a car nobody
described, and every write-off line is a ratio against that number.

**Why the user still picks the trim.** 27,906 vehicle types, and one make in one
model year carries a hundred of them, separated by engine and gearbox: CAPTUR
ICON 1.3 TCe EDC 130 is 1,584,880 TL where CAPTUR TOUCH 1.3 TCe EDC 140 is
1,348,114 TL. No vision model reads a gearbox off a body panel. The list narrows
the question to a menu; it does not answer it.

**What the number is not.** TSB values are averages with no adjustment for
mileage, condition or damage history, and Kasko Genel Şartları B.3-3.3.1.1 makes
the *policy* the authority on which reference applies. This list is the common
one, not automatically the contractual one, and `Valuation.caveat_tr` carries
that sentence into every response rather than leaving it to the UI to remember.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class ListMeta:
    """Which revision of the list answered, and what it does not account for."""

    revision: str
    month_label: str
    source_url: str
    fetched_at: str
    oldest_model_year: int
    newest_model_year: int
    caveat_tr: str


@dataclass(frozen=True)
class VehicleType:
    """One selectable trim."""

    brand_code: int
    type_code: int
    brand_name: str
    type_name: str


@dataclass(frozen=True)
class Valuation:
    """A value read from the list, with everything needed to judge it."""

    vehicle: VehicleType
    model_year: int
    amount_try: Decimal
    meta: ListMeta

    @property
    def source_label(self) -> str:
        """What the response shows next to the figure, rather than a bare URL."""
        return f"TSB Kasko Değer Listesi {self.meta.month_label} ({self.meta.revision})"


class ValueListUnavailableError(RuntimeError):
    """The mirror has not been built.

    Deliberately fatal to the lookup rather than silently returning nothing: a
    caller that cannot tell "no such vehicle" from "no list at all" would show
    the user the wrong message.
    """


class TsbValueList:
    """Read-only lookup over the mirrored list."""

    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise ValueListUnavailableError(
                f"no TSB value list at {path}. Run: uv run python -m scripts.fetch_tsb_values"
            )
        # Immutable URI: several workers share one file and none of them writes.
        self._connection = sqlite3.connect(
            f"file:{path}?immutable=1", uri=True, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._meta = self._read_meta()

    def _read_meta(self) -> ListMeta:
        rows = dict(self._connection.execute("SELECT key, value FROM meta"))
        try:
            return ListMeta(
                revision=rows["revision"],
                month_label=rows["month_label"],
                source_url=rows["source_url"],
                fetched_at=rows["fetched_at"],
                oldest_model_year=int(rows["oldest_model_year"]),
                newest_model_year=int(rows["newest_model_year"]),
                caveat_tr=rows["caveat_tr"],
            )
        except KeyError as error:
            raise ValueListUnavailableError(
                f"the value list is missing metadata {error}; rebuild it"
            ) from error

    @property
    def meta(self) -> ListMeta:
        return self._meta

    def model_years(self) -> list[int]:
        return [
            int(row[0])
            for row in self._connection.execute(
                "SELECT DISTINCT model_year FROM value ORDER BY model_year DESC"
            )
        ]

    def brands(self, model_year: int) -> list[str]:
        """Brands that actually have a value in that year, not all brands.

        Offering a brand with nothing behind it would let a user complete the
        whole menu and reach an empty answer.
        """
        return [
            str(row[0])
            for row in self._connection.execute(
                "SELECT DISTINCT brand_name FROM value WHERE model_year = ? ORDER BY brand_name",
                (model_year,),
            )
        ]

    def types(self, model_year: int, brand_name: str) -> list[VehicleType]:
        return [
            VehicleType(
                brand_code=int(row["brand_code"]),
                type_code=int(row["type_code"]),
                brand_name=str(row["brand_name"]),
                type_name=str(row["type_name"]),
            )
            for row in self._connection.execute(
                """
                SELECT brand_code, type_code, brand_name, type_name
                FROM value
                WHERE model_year = ? AND brand_name = ?
                ORDER BY type_name
                """,
                (model_year, brand_name),
            )
        ]

    def value_for(self, model_year: int, brand_code: int, type_code: int) -> Valuation | None:
        """The listed value, or None where this vehicle has none that year.

        None is a real answer: a trim not sold in a given model year has no row,
        and the nearest year is a different car. The caller asks the user rather
        than substituting.
        """
        row = self._connection.execute(
            """
            SELECT brand_code, type_code, brand_name, type_name, amount_try
            FROM value
            WHERE model_year = ? AND brand_code = ? AND type_code = ?
            """,
            (model_year, brand_code, type_code),
        ).fetchone()
        if row is None:
            return None

        return Valuation(
            vehicle=VehicleType(
                brand_code=int(row["brand_code"]),
                type_code=int(row["type_code"]),
                brand_name=str(row["brand_name"]),
                type_name=str(row["type_name"]),
            ),
            model_year=model_year,
            amount_try=Decimal(int(row["amount_try"])),
            meta=self._meta,
        )

    def covers(self, model_year: int) -> bool:
        """Whether the list reaches that year at all.

        The list spans 15 model years. Older vehicles are absent by design, and
        the honest response names that rather than reporting "not found", which
        would read as a data problem instead of a documented boundary.
        """
        return self._meta.oldest_model_year <= model_year <= self._meta.newest_model_year
