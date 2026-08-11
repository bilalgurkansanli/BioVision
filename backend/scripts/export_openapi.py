"""Regenerate `docs/openapi.json` from the running application.

The committed schema is what the frontend generates its TypeScript types from, so
it must never lag behind the Python models. `tests/contract/test_openapi_drift.py`
fails CI when the two disagree; this script is how you fix that failure.

    uv run python scripts/export_openapi.py
"""

from __future__ import annotations

import json
import sys
from typing import Any

from biovision.config import BACKEND_ROOT, Settings
from biovision.main import create_app

OUTPUT_PATH = BACKEND_ROOT.parent / "docs" / "openapi.json"


def build_schema() -> dict[str, Any]:
    """The OpenAPI document, generated from settings that do not read `.env`.

    A developer's local `.env` must not be able to change the committed schema.
    """
    app = create_app(Settings(_env_file=None))  # type: ignore[call-arg]
    schema: dict[str, Any] = app.openapi()
    return schema


def serialise(schema: dict[str, Any]) -> str:
    # Sorted keys and a trailing newline so the file produces readable diffs
    # instead of a single reordered blob.
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    payload = serialise(build_schema())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    previous = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.is_file() else None
    OUTPUT_PATH.write_text(payload, encoding="utf-8")

    if previous == payload:
        print(f"unchanged: {OUTPUT_PATH}")
    else:
        print(f"written: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
