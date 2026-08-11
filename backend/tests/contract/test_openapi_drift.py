"""The committed OpenAPI document must match the code.

The frontend generates its types from `docs/openapi.json`. If that file is allowed
to go stale, the contract stops being a contract and becomes a comment.
"""

from __future__ import annotations

import pytest
from scripts.export_openapi import OUTPUT_PATH, build_schema, serialise


def test_committed_schema_is_current() -> None:
    if not OUTPUT_PATH.is_file():
        pytest.fail(f"{OUTPUT_PATH} is missing. Run: uv run python scripts/export_openapi.py")

    committed = OUTPUT_PATH.read_text(encoding="utf-8")
    generated = serialise(build_schema())

    assert committed == generated, (
        "docs/openapi.json is out of date with the Python models. "
        "Run: uv run python scripts/export_openapi.py"
    )


def test_every_documented_endpoint_is_present() -> None:
    paths = build_schema()["paths"]

    assert "/health" in paths
    assert "/v1/analyze" in paths
    assert "/v1/domains" in paths
    assert "/v1/requests" in paths


def test_analyze_documents_each_failure_status() -> None:
    """The README's error table and the schema must agree."""
    responses = build_schema()["paths"]["/v1/analyze"]["post"]["responses"]

    for status in ("413", "415", "422", "429", "503"):
        assert status in responses, f"{status} is missing from the OpenAPI document"
