"""Measure per-stage latency and print the p50/p95 table the README publishes.

    uv run python -m scripts.bench_latency --n 40

Runs the pipeline in-process rather than over HTTP: the numbers that matter are the
model and image-processing costs, and adding a network hop would measure the loopback
interface as well.

**Every sample uses a distinct image.** Repeating one would hit the encoder's
embedding cache and produce a number that looks excellent and means nothing.

Run this on the production VPS before quoting anything from it. A developer laptop
and a 4-vCPU box with no GPU are different machines, and the queue decision in README
section 9 rests on the p95 measured where the service actually runs.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass, field

from biovision.config import Settings
from biovision.errors import BioVisionError
from biovision.models.registry import build_registry
from biovision.pipeline.orchestrator import analyze_image

STAGES = ("preprocess", "gate", "router", "specialist", "vlm", "total")


@dataclass
class Samples:
    values: dict[str, list[int]] = field(default_factory=lambda: {s: [] for s in STAGES})
    rejected: int = 0
    failed: int = 0

    def record(self, timings: dict[str, int | None]) -> None:
        for stage in STAGES:
            value = timings.get(stage)
            if value is not None:
                self.values[stage].append(value)


def percentile(values: list[int], fraction: float) -> int | None:
    """Nearest-rank percentile. No interpolation -- every reported number is a
    latency that was actually observed."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * len(ordered)) - 1))
    return ordered[index]


def synthetic_images(count: int, size: tuple[int, int] = (1600, 1200)) -> list[bytes]:
    """`count` distinct JPEGs.

    Gradients, not photographs. They exercise the full cost path -- decode, EXIF,
    hash, redaction, two model passes -- because that cost depends on resolution
    rather than on content. They say nothing about accuracy, and no number produced
    from them belongs in an accuracy table.

    Generated here rather than imported from the test fixtures: a script that ships
    with the application should not depend on the test package.
    """
    import io

    import numpy as np
    from PIL import Image

    width, height = size
    grid_x, grid_y = np.meshgrid(
        np.linspace(0, 255, width, dtype=np.float32),
        np.linspace(0, 255, height, dtype=np.float32),
    )

    payloads = []
    for index in range(count):
        pixels = np.clip(
            np.stack([grid_x, grid_y, (grid_x + grid_y) / 2 + (index * 37 % 90)], axis=-1),
            0,
            255,
        ).astype(np.uint8)
        # A seed-dependent block, so each image is genuinely distinct and none of
        # them hits the encoder's embedding cache.
        block_x = (index * 53) % (width - width // 4)
        block_y = (index * 31) % (height - height // 4)
        pixels[block_y : block_y + height // 4, block_x : block_x + width // 4] = (
            20,
            200,
            120,
        )

        buffer = io.BytesIO()
        Image.fromarray(pixels, mode="RGB").save(buffer, format="JPEG", quality=90)
        payloads.append(buffer.getvalue())

    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=30, help="number of samples")
    parser.add_argument("--warmup", type=int, default=3, help="untimed runs first")
    args = parser.parse_args()

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    print(f"backend={settings.model_backend}  threads={settings.torch_num_threads}")
    print("loading models ...")

    started = time.perf_counter()
    registry = build_registry(settings)
    print(f"startup: {time.perf_counter() - started:.1f}s\n")

    images = synthetic_images(args.n + args.warmup)
    samples = Samples()

    for index, payload in enumerate(images):
        try:
            result = analyze_image(
                payload,
                settings=settings,
                registry=registry,
                language="tr",
                vlm_allowed=False,
            )
        except BioVisionError as exc:
            # A gate rejection is a real outcome, not a failure -- but its timings
            # stop early and would drag the router percentiles down.
            if index >= args.warmup:
                samples.rejected += 1
            if index == args.warmup:
                print(f"note: gate rejecting these images ({exc.code.value})")
                print("      run with BIOVISION_GATE_THRESHOLD=0.0 to time the router\n")
            continue
        except Exception as exc:
            samples.failed += 1
            print(f"failed: {exc}")
            continue

        if index >= args.warmup:
            samples.record(result.response.timing_ms.model_dump())

    print(f"{'stage':<12} {'n':>5} {'p50':>8} {'p95':>8} {'max':>8}")
    print("-" * 44)
    for stage in STAGES:
        values = samples.values[stage]
        if not values:
            print(f"{stage:<12} {0:>5} {'--':>8} {'--':>8} {'--':>8}")
            continue
        print(
            f"{stage:<12} {len(values):>5} {percentile(values, 0.50):>8} "
            f"{percentile(values, 0.95):>8} {max(values):>8}"
        )

    if samples.values["total"]:
        mean = statistics.mean(samples.values["total"])
        print(f"\nmean end-to-end: {mean:.0f} ms")
    if samples.rejected:
        print(f"gate-rejected (excluded): {samples.rejected}")
    if samples.failed:
        print(f"errors: {samples.failed}")

    p95 = percentile(samples.values["total"], 0.95)
    if p95 is not None:
        print(f"\nQueue threshold is p95 > 3000 ms (README section 9). Measured: {p95} ms.")
        print("Still synchronous." if p95 <= 3000 else "*** Time to reconsider the queue. ***")

    return 0


if __name__ == "__main__":
    sys.exit(main())
