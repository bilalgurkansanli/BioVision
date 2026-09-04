"""No module may depend on being imported second.

`schemas.analyze` imported `Band` and `Level` from `models.damage_position`, which
closed a cycle: `schemas.analyze` -> `models` -> `models.base` -> `pipeline.types`
-> `pipeline/__init__` -> `ingest` -> `exif` -> `schemas.analyze`, still half
built. The application never hit it because `models` sorts before `pipeline` and
before `schemas`, so every real entry point imported the cycle from a direction
that happened to work.

That made it invisible and load-bearing at once: `import biovision.pipeline.
orchestrator` in a fresh interpreter raised ImportError, and reordering two import
lines -- something a formatter is allowed to do -- would have broken the server.
The enums now live in `schemas.enums`, which imports nothing from this package.

Each module is imported in its own interpreter, because within one process an
earlier test's imports would satisfy the cycle and the check would pass whatever
the code did.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

#: Every module a script, a test or a tool might reach for first. The pipeline and
#: schema entries are the ones that used to fail.
ENTRY_POINTS = [
    "biovision.main",
    "biovision.config",
    "biovision.schemas.analyze",
    "biovision.schemas.enums",
    "biovision.schemas.photoset",
    "biovision.pipeline",
    "biovision.pipeline.ingest",
    "biovision.pipeline.orchestrator",
    "biovision.pipeline.types",
    "biovision.models",
    "biovision.models.base",
    "biovision.models.damage_position",
    "biovision.models.mask_geometry",
    "biovision.models.registry",
    "biovision.models.specialists.vehicle_yolo",
    "biovision.models.vehicle_extent",
]


@pytest.mark.parametrize("module", ENTRY_POINTS)
def test_module_imports_as_the_first_import(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"`import {module}` fails in a fresh interpreter, so this module only "
        f"works when something else is imported first:\n{result.stderr}"
    )


def test_the_response_contract_does_not_import_the_model_layer() -> None:
    """The edge that closed the cycle, asserted as a rule rather than an outcome.

    `schemas` describes what the API returns; `models` produces it. One direction
    is a dependency and the other is a cycle waiting for an import to be sorted.
    """
    from pathlib import Path

    from biovision.config import BACKEND_ROOT

    schemas = Path(BACKEND_ROOT) / "src" / "biovision" / "schemas"
    offenders = [
        f"{path.name}:{number}: {line.strip()}"
        for path in sorted(schemas.glob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if line.startswith(("from biovision.models", "import biovision.models"))
    ]

    assert not offenders, (
        "schemas must not import models -- that is the edge that closed the "
        "import cycle. Move the shared vocabulary into schemas.enums instead:\n"
        + "\n".join(offenders)
    )
