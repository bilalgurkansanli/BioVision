"""Where the repository is, worked out rather than written down.

Every evaluation script needs the same four or five directories. They used to be
spelled out as absolute paths on one Windows machine, which meant the scripts
behind every number in the README ran for exactly one person -- while
CONTRIBUTING.md told a reader that those scripts were how a claim gets checked.
A measurement nobody else can repeat is an assertion.

`REPO` is derived from this file's own location: `backend/scripts/_paths.py`, so
two parents up is the repository root wherever it has been cloned to.
"""

from __future__ import annotations

from pathlib import Path

#: backend/scripts/_paths.py -> backend/scripts -> backend -> repository root
REPO = Path(__file__).resolve().parents[2]

BACKEND = REPO / "backend"
SRC = BACKEND / "src"
WEIGHTS = BACKEND / "weights"
DATA = REPO / "data"
SOURCES = DATA / "_sources"
CACHE = DATA / ".cache"


def require(path: Path, what: str) -> Path:
    """Fail with the path and what was expected, rather than an empty result.

    A script that finds no images should say the directory is missing, not print
    "0/0" and let the reader conclude the model scored nothing.
    """
    if not path.exists():
        raise SystemExit(
            f"{what} not found at {path}\n"
            f"  repository root resolved to: {REPO}\n"
            f"  see data/README.md for how to fetch it"
        )
    return path
