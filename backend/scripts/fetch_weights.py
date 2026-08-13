"""Download model checkpoints into `backend/weights/`.

Weights are not committed: they are large, they change independently of the code,
and some are licence-encumbered. This script fetches them and verifies each against
a pinned SHA-256, so a silently changed upstream file is a loud failure rather than
a quiet change in behaviour that nobody can reproduce.

    uv run python -m scripts.fetch_weights

Everything here is optional at runtime. A missing checkpoint disables its feature
and the API reports it as disabled -- it does not pretend.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from biovision.config import BACKEND_ROOT, Settings

WEIGHTS_DIR = BACKEND_ROOT / "weights"


@dataclass(frozen=True)
class Artifact:
    filename: str
    url: str
    sha256: str
    purpose: str
    licence: str


ARTIFACTS: tuple[Artifact, ...] = (
    Artifact(
        filename="face_detection_yunet_2023mar.onnx",
        url=(
            "https://github.com/opencv/opencv_zoo/raw/main/"
            "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
        ),
        sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        purpose="Face redaction (Phase 2)",
        licence="MIT (OpenCV Zoo)",
    ),
    # The CarDD-trained vehicle specialist is deliberately NOT listed here, and this
    # is not a placeholder waiting to be filled in.
    #
    # The CarDD licence forbids distributing "all or part of the dataset" without the
    # PIC Lab's authorisation, and says nothing about weights fine-tuned on it. Until
    # they answer that question, the checkpoint is treated like the data: trained
    # locally from your own copy via notebooks/train_cardd_yolo.ipynb, dropped into
    # weights/ by hand, never served from a public URL. Publishing a checkpoint is not
    # reversible; asking is one line in an email. See docs/DECISIONS.md ADR-025.
    #
    # If the PIC Lab authorises redistribution, add the Artifact entry here with its
    # SHA-256 pinned like every other row.
)


def prefetch_clip(model_name: str, pretrained: str, cache_dir: Path) -> bool:
    """Warm the open_clip cache for the zero-shot encoder.

    Not SHA-pinned, unlike everything in ARTIFACTS, and the difference is worth
    stating: open_clip resolves its own checkpoint through the HuggingFace hub and
    owns the cache layout. Pinning a digest here would mean second-guessing that
    resolution, and a hand-placed file in a cache directory we do not control is
    more fragile than the hub's own integrity checking. The checkpoint identity is
    still pinned -- by name and revision in `pyproject.toml` and `config.py`.
    """
    print(f"prefetching CLIP {model_name} / {pretrained} ...")
    try:
        import open_clip

        open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device="cpu", cache_dir=str(cache_dir)
        )
    except Exception as exc:
        print(f"FAILED   CLIP {model_name}: {exc}")
        return False

    print(f"ok       CLIP {model_name} / {pretrained}")
    return True


def fetch(artifact: Artifact, target_dir: Path) -> bool:
    """Download and verify one artifact. Returns True if it is present and correct."""
    target = target_dir / artifact.filename

    if target.is_file():
        actual = _sha256(target)
        if actual == artifact.sha256:
            print(f"ok       {artifact.filename}")
            return True
        print(f"MISMATCH {artifact.filename}: expected {artifact.sha256}, got {actual}")
        print("         refusing to overwrite -- delete it manually if this is expected")
        return False

    print(f"fetching {artifact.filename} ...")
    target_dir.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")

    try:
        # URL is a pinned https constant, and the payload is SHA-256 verified below.
        with urllib.request.urlopen(artifact.url, timeout=60) as response:
            temporary.write_bytes(response.read())
    except Exception as exc:
        print(f"FAILED   {artifact.filename}: {exc}")
        temporary.unlink(missing_ok=True)
        return False

    actual = _sha256(temporary)
    if actual != artifact.sha256:
        # Never install an artifact whose contents we cannot vouch for. A changed
        # checkpoint silently changes the privacy guarantee.
        print(f"MISMATCH {artifact.filename}: expected {artifact.sha256}, got {actual}")
        temporary.unlink(missing_ok=True)
        return False

    temporary.replace(target)
    print(f"ok       {artifact.filename}  ({artifact.licence})")
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    print(f"weights directory: {WEIGHTS_DIR}\n")
    results = [fetch(artifact, WEIGHTS_DIR) for artifact in ARTIFACTS]

    if "--with-clip" in sys.argv:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        results.append(
            prefetch_clip(settings.clip_model, settings.clip_pretrained, WEIGHTS_DIR)
        )
    else:
        print("\nskipping CLIP (~600 MB); pass --with-clip to fetch it")

    if all(results):
        print(f"\n{len(results)} artifact(s) present and verified.")
        return 0

    print("\nSome artifacts are missing. The API still starts; the features they")
    print("back report themselves as unavailable rather than pretending to work.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
