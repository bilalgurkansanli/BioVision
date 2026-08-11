"""Download the evaluation images listed in a manifest.

    uv run python -m scripts.fetch_eval_images router_eval
    uv run python -m scripts.fetch_eval_images --all

Images are not committed (ADR-005): licences vary and a public AGPL repository is the
wrong place for third-party photographs. The manifest records source URL, licence and
SHA-256 for each, so the set is exactly reproducible without redistributing anything.

Every download is verified against its recorded digest. A source that has silently
changed is a hard failure -- an evaluation set that quietly drifts would invalidate
every number computed from it, and nothing would look wrong.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

from scripts._evalset import DATA_ROOT, read_manifest

SETS = ("router_eval", "router_calib", "gate_eval", "redaction_eval")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_set(name: str) -> tuple[int, int, int]:
    """Returns (ok, failed, skipped)."""
    directory = DATA_ROOT / name
    manifest = directory / "manifest.csv"

    if not manifest.is_file():
        print(f"{name}: no manifest at {manifest} -- skipping")
        return 0, 0, 0

    images = directory / "images"
    images.mkdir(parents=True, exist_ok=True)

    ok = failed = skipped = 0

    for row in read_manifest(manifest):
        filename = row["filename"].strip()
        expected = row.get("sha256", "").strip().lower()
        target = images / filename

        if target.is_file():
            if expected and sha256(target) != expected:
                print(f"  MISMATCH {filename} -- delete it to re-fetch")
                failed += 1
            else:
                skipped += 1
            continue

        url = row.get("source_url", "").strip()
        if not url:
            print(f"  no source_url for {filename}")
            failed += 1
            continue

        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                payload = response.read()
        except Exception as exc:
            print(f"  FAILED   {filename}: {exc}")
            failed += 1
            continue

        actual = hashlib.sha256(payload).hexdigest()
        if expected and actual != expected:
            # A changed source means the evaluation set is no longer the one the
            # published numbers were computed from.
            print(f"  MISMATCH {filename}: expected {expected}, got {actual}")
            failed += 1
            continue

        target.write_bytes(payload)
        if not expected:
            print(f"  ok       {filename}  (record sha256: {actual})")
        else:
            print(f"  ok       {filename}")
        ok += 1

    return ok, failed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", choices=[*SETS, []], help="sets to fetch")
    parser.add_argument("--all", action="store_true", help="fetch every known set")
    args = parser.parse_args()

    names = SETS if args.all or not args.names else tuple(args.names)
    totals = [0, 0, 0]

    for name in names:
        print(f"\n{name}:")
        result = fetch_set(name)
        totals = [total + value for total, value in zip(totals, result, strict=True)]

    print(f"\ndownloaded {totals[0]}, already present {totals[2]}, failed {totals[1]}")
    return 1 if totals[1] else 0


if __name__ == "__main__":
    sys.exit(main())
