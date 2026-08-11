"""Per-stage wall-clock measurement.

Every response carries its own timing breakdown. That is not decoration: the
decision to stay synchronous instead of adding a queue is justified by a p95
number, and the p95 number has to come from production traffic rather than from a
benchmark run once on a laptop.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from biovision.schemas.analyze import TimingMs


class StageTimer:
    """Accumulates per-stage durations for one request.

    Stages that never run stay absent and serialise as ``null`` rather than ``0``:
    a zero would silently drag down any percentile computed over the field.
    """

    def __init__(self) -> None:
        self._started = time.perf_counter()
        self._stages: dict[str, int] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self._stages[name] = _elapsed_ms(started)

    def total_ms(self) -> int:
        return _elapsed_ms(self._started)

    def build(self) -> TimingMs:
        return TimingMs(
            preprocess=self._stages.get("preprocess"),
            gate=self._stages.get("gate"),
            router=self._stages.get("router"),
            specialist=self._stages.get("specialist"),
            vlm=self._stages.get("vlm"),
            total=self.total_ms(),
        )


def _elapsed_ms(since: float) -> int:
    return max(0, round((time.perf_counter() - since) * 1000))
