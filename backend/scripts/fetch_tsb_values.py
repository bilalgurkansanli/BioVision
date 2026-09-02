"""Mirror the TSB Kasko Değer Listesi into a local lookup.

    uv run python -m scripts.fetch_tsb_values

Every write-off threshold is a ratio against the vehicle's value, so without this
the product can only state percentages. With it, the lines come back in lira.

**The bulk file, not the per-query endpoints.** TSB serves both: a JSON chain
(year -> brand -> model -> amount) and one workbook holding the lot. The chain is
four unauthenticated requests per lookup against an undocumented endpoint with no
published rate limit and no terms of use; the workbook is one request per month.
Mirroring it locally is the polite option and the fast one -- a lookup becomes a
dict access rather than a round trip to someone else's server.

**Three ways this data fails quietly, all handled here rather than discovered
later.**

1. The file is revised two to four times a month, and the revision is in the
   filename (`202608R4.xlsx`). Guessing `R1` silently serves stale values, so the
   revision is resolved from `GetLatestExcelFile` and recorded in the output.
2. The list covers **15 model years**. An older vehicle is simply absent, and the
   correct behaviour is to say so -- not to fall back to the oldest column, which
   would answer a question about a 2005 car with a 2012 car's value.
3. Values are averages with no mileage, condition or damage adjustment, and per
   Kasko Genel Şartları B.3-3.3.1.1 the *policy* names the valuation reference.
   This list is the common one, not automatically the contractual one. The output
   carries that caveat so the API can repeat it.

Output is SQLite: one file, stdlib access, indexed lookup, and small enough to
sit beside the weights. Not committed -- `data/` holds no downloaded artefacts.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biovision.config import BACKEND_ROOT

TSB = "https://www.tsb.org.tr"
LATEST = "/InsuranceData/GetLatestExcelFile"

#: TSB asks nothing of clients -- no robots.txt, no terms, no documented limit --
#: so identifying the caller is a courtesy rather than a requirement. It is also
#: the only way a maintainer there could tell us to stop.
USER_AGENT = "BioVision/1.0 (research; https://github.com/bilalgurkansanli/BioVision)"

DEFAULT_OUT = BACKEND_ROOT.parent / "data" / "tsb" / "kasko_degerleri.sqlite"


def fetch_json(path: str) -> dict[str, Any]:
    request = urllib.request.Request(TSB + path, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload: dict[str, Any] = json.load(response)
    if payload.get("HasError"):
        raise RuntimeError(f"TSB reported an error for {path}: {payload.get('Message')}")
    return payload


def fetch_bytes(path: str) -> bytes:
    request = urllib.request.Request(TSB + path, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response:
        return bytes(response.read())


#: A vehicle value outside this band is not parsed, it is a parsing accident.
#: The August 2026 list runs from 6,116 TL (a 2012 125cc motorcycle) to
#: 105,777,121 TL (a 2026 Brabus G 63), so the band is wide on purpose -- it is
#: there to catch an order-of-magnitude shift, not to second-guess TSB.
PLAUSIBLE_TRY = (1_000, 500_000_000)


def parse_amount(cell: object) -> int | None:
    """One workbook cell as lira, or None where the vehicle had no value that year.

    **The string path is the dangerous one and it is now unreachable for numbers.**
    Every cell in the August 2026 list is a Python `int`, so the previous
    implementation -- `int(float(str(cell).replace(".", "")))` -- was correct by
    luck of type. Had openpyxl handed back a float, `1584880.0` would have become
    the string "1584880.0", lost its dot, and been stored as **15,848,800**: ten
    times the real value, silently, on the figure every write-off line divides by.

    So numbers are used as numbers, and the Turkish thousand-separator logic
    applies only where a string actually arrives.
    """
    if cell is None:
        return None
    if isinstance(cell, bool):  # bool is an int subclass; never a price
        return None
    if isinstance(cell, int):
        amount = cell
    elif isinstance(cell, float):
        amount = round(cell)
    else:
        text = str(cell).strip()
        if not text or text == "-":
            return None
        try:
            # "1.584.880,00" -> 1584880.0. Only reachable for a genuine string.
            amount = round(float(text.replace(".", "").replace(",", ".")))
        except ValueError:
            return None
    return amount if amount > 0 else None


def build(destination: Path) -> int:
    latest = fetch_json(LATEST)
    relative = str(latest["Result"])
    revision = Path(relative).stem  # e.g. 202608R4
    month_label = str(latest.get("Message") or "")

    print(f"latest list: {month_label} -> {relative}  (revision {revision})")

    raw = fetch_bytes(relative)
    print(f"downloaded {len(raw):,} bytes")

    import io

    from openpyxl import load_workbook

    # read_only + values_only: the workbook is ~26 MB expanded and none of the
    # styling matters.
    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    rows = sheet.iter_rows(values_only=True)

    title = next(rows, None)  # A1 carries "Ağustos 2026"
    header = next(rows, None)
    if not header:
        raise RuntimeError("workbook has no header row; TSB may have changed the layout")

    # Marka Kodu | Tip Kodu | Marka Adı | Tip Adı | 2026 | 2025 | ... | 2012
    year_columns: list[tuple[int, int]] = []
    for index, cell in enumerate(header):
        text = str(cell).strip() if cell is not None else ""
        if text.isdigit() and len(text) == 4:
            year_columns.append((index, int(text)))

    if not year_columns:
        raise RuntimeError(
            f"no model-year columns found in header {header!r}; TSB changed the layout"
        )

    print(f"model years: {year_columns[0][1]}..{year_columns[-1][1]} ({len(year_columns)} columns)")

    destination.parent.mkdir(parents=True, exist_ok=True)

    # Built beside the target, then moved over it. A running API holds the old
    # file open -- on Windows that makes deleting it fail outright, and the first
    # monthly refresh died here with a WinError 32 that said nothing about what to
    # do. Writing a complete file first also means a crash mid-build leaves the
    # previous month's data intact rather than a truncated database.
    staging = destination.with_suffix(destination.suffix + ".new")
    if staging.exists():
        staging.unlink()

    connection = sqlite3.connect(staging)
    connection.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE value (
            brand_code  INTEGER NOT NULL,
            type_code   INTEGER NOT NULL,
            brand_name  TEXT NOT NULL,
            type_name   TEXT NOT NULL,
            model_year  INTEGER NOT NULL,
            amount_try  INTEGER NOT NULL,
            PRIMARY KEY (brand_code, type_code, model_year)
        );
        CREATE INDEX idx_brand_year ON value (model_year, brand_name);
        """
    )

    written = 0
    skipped_rows = 0
    skipped_values = 0
    for row in rows:
        if not row or row[0] is None:
            skipped_rows += 1
            continue
        try:
            brand_code = int(str(row[0]).strip())
            type_code = int(str(row[1]).strip())
        except (TypeError, ValueError):
            skipped_rows += 1
            continue

        brand_name = str(row[2] or "").strip()
        type_name = str(row[3] or "").strip()
        if not brand_name or not type_name:
            skipped_rows += 1
            continue

        for index, year in year_columns:
            if index >= len(row):
                continue
            amount = parse_amount(row[index])
            if amount is None:
                # The vehicle was not sold in that model year. TSB writes a
                # literal 0 rather than leaving the cell blank -- 339,210 of the
                # 418,590 cells in the August 2026 list are zeros -- and storing
                # them would let a lookup answer "worth nothing" for a car that
                # simply did not exist that year.
                skipped_values += 1
                continue
            connection.execute(
                "INSERT OR REPLACE INTO value VALUES (?, ?, ?, ?, ?, ?)",
                (brand_code, type_code, brand_name, type_name, year, amount),
            )
            written += 1

    connection.executemany(
        "INSERT INTO meta VALUES (?, ?)",
        [
            ("revision", revision),
            ("month_label", month_label),
            ("source_url", TSB + relative),
            ("fetched_at", datetime.now(UTC).isoformat(timespec="seconds")),
            ("oldest_model_year", str(min(year for _, year in year_columns))),
            ("newest_model_year", str(max(year for _, year in year_columns))),
            ("title_cell", str(title[0]) if title and title[0] else ""),
            (
                "caveat_tr",
                "Bu liste ortalama değerler içerir; kilometre, hasar geçmişi ve "
                "donanım farkı yansıtılmaz. Kasko Genel Şartları B.3-3.3.1.1 uyarınca "
                "değerleme referansını poliçe belirler; bu liste yaygın referanstır, "
                "otomatik olarak sözleşmesel referans değildir.",
            ),
        ],
    )
    connection.commit()

    vehicles = connection.execute(
        "SELECT COUNT(DISTINCT brand_code || '-' || type_code) FROM value"
    ).fetchone()[0]
    brands = connection.execute("SELECT COUNT(DISTINCT brand_name) FROM value").fetchone()[0]
    low, high = connection.execute("SELECT MIN(amount_try), MAX(amount_try) FROM value").fetchone()
    connection.close()

    print(f"\n{written:,} values, {vehicles:,} vehicle types, {brands} brands")
    print(f"{skipped_values:,} cell(s) with no value (TSB writes 0 for a year not sold)")
    if skipped_rows:
        print(f"{skipped_rows:,} row(s) skipped (headers, blanks, malformed codes)")
    print(f"value range: {low:,} .. {high:,} TL")

    # A loud stop rather than a quiet tenfold error. Every write-off line, both
    # payout branches and the trafik shortfall are ratios against these numbers,
    # so a magnitude shift is worth more than a completed rebuild. The previous
    # mirror is left in place: stale and correct beats fresh and wrong.
    floor, ceiling = PLAUSIBLE_TRY
    if not written or low < floor or high > ceiling:
        staging.unlink(missing_ok=True)
        raise RuntimeError(
            f"values run {low:,}..{high:,} TL over {written:,} rows, outside the "
            f"plausible band {floor:,}..{ceiling:,}. That is the signature of a "
            f"parsing change -- a float reaching the string path multiplies by ten. "
            f"The previous mirror is untouched; check `parse_amount` against the "
            f"workbook before overwriting it."
        )

    # The move that makes the whole staging dance mean something.
    #
    # It was missing. The docstring above described it, the staging file was
    # built, and nothing ever put it in place -- so every refresh after the first
    # wrote `kasko_degerleri.sqlite.new`, printed a success line, exited 0, and
    # left the API serving the previous month's values indefinitely. Found by
    # rebuilding to a scratch path during a review and noticing the destination
    # was zero bytes, with a full `.new` beside it.
    #
    # `Path.replace` is atomic on POSIX and near-atomic on Windows; the reader
    # opens the file with `immutable=1`, so a worker mid-request keeps the handle
    # it already has and the next request opens the new file.
    staging.replace(destination)
    print(f"written: {destination}  ({destination.stat().st_size:,} bytes)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    arguments = parser.parse_args()
    try:
        return build(arguments.out)
    except Exception as error:
        print(f"failed: {error}")
        print(
            "\nThese endpoints are undocumented and unversioned -- no robots.txt, no "
            "terms, no stability promise. If the layout changed, the API degrades to "
            "asking the user for the value rather than serving a wrong one."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
