"""Regenerate the golden-set expectations from the current models.

    uv run python -m scripts.update_golden --review
    uv run python -m scripts.update_golden --write

`--review` shows what would change and writes nothing. `--write` accepts the new
outputs.

Regenerating without reading the diffs turns the regression tripwire into a rubber
stamp, so `--review` is the default and `--write` has to be asked for.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from biovision.config import BACKEND_ROOT, Settings

GOLDEN = BACKEND_ROOT / "tests" / "golden"
IMAGES = GOLDEN / "images"
EXPECTED = GOLDEN / "expected"

#: Fields that change every run and would make the test fail for no reason.
VOLATILE = {"request_id", "timing_ms", "integrity"}


def capture(client: Any, image_path: Path) -> dict[str, Any]:
    response = client.post(
        "/v1/analyze",
        files={"image": (image_path.name, image_path.read_bytes(), "image/jpeg")},
    )

    if response.status_code != 200:
        return {
            "expect_status": response.status_code,
            "expect_error": response.json().get("error", {}).get("code"),
        }

    body = {key: value for key, value in response.json().items() if key not in VOLATILE}
    body["findings"] = [
        {key: value for key, value in finding.items() if key != "bbox"}
        for finding in body.get("findings", [])
    ]
    if body.get("vlm_description") is not None:
        # Store presence, not prose: upstream can reword it at any time.
        body["vlm_description"] = "<present>"
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--review", action="store_true", help="show diffs, write nothing")
    group.add_argument("--write", action="store_true", help="accept the new outputs")
    args = parser.parse_args()

    review_only = not args.write

    images = sorted(
        path
        for path in IMAGES.glob("*")
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".heic"}
    )
    if not images:
        print(f"No images in {IMAGES}. See tests/golden/README.md.")
        return 1

    from fastapi.testclient import TestClient

    from biovision.main import create_app

    settings = Settings(model_backend="real", anon_daily_limit=10_000, _env_file=None)  # type: ignore[call-arg]
    EXPECTED.mkdir(parents=True, exist_ok=True)

    changed = unchanged = new = 0

    with TestClient(create_app(settings)) as client:
        for image_path in images:
            target = EXPECTED / f"{image_path.stem}.json"
            captured = capture(client, image_path)
            serialised = json.dumps(captured, indent=2, sort_keys=True) + "\n"

            if not target.is_file():
                print(f"NEW      {target.name}")
                print("  " + serialised.replace("\n", "\n  "))
                new += 1
            elif target.read_text(encoding="utf-8") == serialised:
                unchanged += 1
                continue
            else:
                print(f"CHANGED  {target.name}")
                previous = json.loads(target.read_text(encoding="utf-8"))
                for key in sorted(set(previous) | set(captured)):
                    before, after = previous.get(key), captured.get(key)
                    if before != after:
                        print(f"  {key}: {before!r} -> {after!r}")
                changed += 1

            if not review_only:
                target.write_text(serialised, encoding="utf-8")

    print(f"\n{unchanged} unchanged, {changed} changed, {new} new")
    if review_only and (changed or new):
        print("Nothing written. Read the diffs above, then re-run with --write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
