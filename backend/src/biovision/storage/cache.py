"""Perceptual-hash cache for VLM descriptions.

The same photograph submitted twice should cost money once. The key is the
perceptual hash — so a re-encoded, re-compressed, or slightly resized copy of an
image already described still hits — **combined with the response language**.

The language is not optional in that key. Without it, a cached Turkish description
would be served to a request that asked for English: a silent correctness bug that
looks like a cost optimisation working.

.. warning::
   In process memory, so it is per-worker and lost on restart. That is a cost
   inefficiency (a second worker may pay for a description the first already has),
   never a correctness problem. Phase 7 moves it to Supabase, where it is shared
   across workers and survives deploys.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass

from biovision.pipeline.phash import hamming_distance

logger = logging.getLogger(__name__)

#: Entries kept per worker. At ~300 bytes of description each this is trivial
#: memory, and the hit rate matters more than the ceiling.
DEFAULT_MAX_ENTRIES = 2048

#: Maximum Hamming distance treated as "the same photograph".
#:
#: Exact matching is too strict to be useful: a re-encoded copy of an image
#: already described shifts the hash by a bit or two, so an exact-match cache
#: would miss the case it exists for. Measured on the test corpus after full
#: ingestion (resize + JPEG re-encode):
#:
#:   * same photograph, JPEG quality 95 vs 60 vs 40, and PNG:  0-2 bits
#:   * different photographs:                                 18-30 bits
#:
#: A threshold of 4 sits in the gap with room on both sides. It is deliberately
#: far below the nearest observed cross-image distance, because the failure mode
#: it guards against -- serving one photograph's description for another -- is a
#: correctness bug, and a cache miss is only a cost.
#:
#: Measured on synthetic fixtures. Re-validate against the golden set once real
#: photographs exist; if the gap narrows, tighten this rather than widen it.
MAX_HASH_DISTANCE = 4


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    entries: int

    @property
    def hit_rate(self) -> float | None:
        total = self.hits + self.misses
        return self.hits / total if total else None


class DescriptionCache:
    """LRU cache keyed by (perceptual hash, language)."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._max_entries = max_entries
        self._entries: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, phash: str, language: str) -> str | None:
        """Find a description for this image, allowing for re-encoding drift."""
        key = self._find(phash, language)

        if key is None:
            self._misses += 1
            return None

        self._entries.move_to_end(key)
        self._hits += 1
        logger.info(
            "VLM cache hit for %s/%s (stored as %s) -- no API call", phash, language, key[0]
        )
        return self._entries[key]

    def _find(self, phash: str, language: str) -> tuple[str, str] | None:
        """The stored key for this image, or ``None``.

        Exact first -- the common case, and free. Only then the near-match scan,
        which is a 64-bit XOR per same-language entry and stays in the
        microseconds at this cache size.
        """
        exact = (phash, language)
        if exact in self._entries:
            return exact

        best_key: tuple[str, str] | None = None
        best_distance = MAX_HASH_DISTANCE + 1

        for key in self._entries:
            if key[1] != language:
                continue
            try:
                distance = hamming_distance(phash, key[0])
            except ValueError:
                continue  # different hash length: not comparable
            if distance <= MAX_HASH_DISTANCE and distance < best_distance:
                best_key, best_distance = key, distance

        return best_key

    def put(self, phash: str, language: str, description: str) -> None:
        if not description:
            # Never cache an empty description: a transient failure would then be
            # served from cache forever.
            return

        key = (phash, language)
        self._entries[key] = description
        self._entries.move_to_end(key)

        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def stats(self) -> CacheStats:
        return CacheStats(hits=self._hits, misses=self._misses, entries=len(self._entries))

    def clear(self) -> None:
        self._entries.clear()
