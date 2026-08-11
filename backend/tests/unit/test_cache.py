"""The description cache.

Two properties matter: a repeated image must not cost money twice, and a cached
description must never be served for the wrong language.
"""

from __future__ import annotations

import pytest

from biovision.storage.cache import DescriptionCache

# Far apart in Hamming distance, so near-matching never conflates them.
HASH_A = "0000000000000000"
HASH_B = "ffffffffffffffff"


def test_a_stored_description_comes_back() -> None:
    cache = DescriptionCache()
    cache.put(HASH_A, "tr", "Duvarda çatlak var.")

    assert cache.get(HASH_A, "tr") == "Duvarda çatlak var."


def test_an_unseen_image_misses() -> None:
    assert DescriptionCache().get(HASH_A, "tr") is None


def test_the_language_is_part_of_the_key() -> None:
    """Without this, a Turkish description gets served to an English request.

    That is a correctness bug wearing the costume of a cost optimisation.
    """
    cache = DescriptionCache()
    cache.put(HASH_A, "tr", "Duvarda çatlak var.")

    assert cache.get(HASH_A, "en") is None
    assert cache.get(HASH_A, "tr") is not None


def test_both_languages_can_be_cached_for_one_image() -> None:
    cache = DescriptionCache()
    cache.put(HASH_A, "tr", "Türkçe açıklama")
    cache.put(HASH_A, "en", "English description")

    assert cache.get(HASH_A, "tr") == "Türkçe açıklama"
    assert cache.get(HASH_A, "en") == "English description"


def test_a_near_identical_hash_hits() -> None:
    """A re-encoded copy shifts the hash by a bit or two; it is the same photo.

    Exact matching would miss exactly the case the cache exists for -- see
    MAX_HASH_DISTANCE for the measured separation this threshold sits in.
    """
    cache = DescriptionCache()
    cache.put("0000000000000000", "tr", "text")

    assert cache.get("0000000000000003", "tr") == "text"  # 2 bits apart


def test_a_distant_hash_misses() -> None:
    """Serving one photograph's description for another is a correctness bug."""
    cache = DescriptionCache()
    cache.put("0000000000000000", "tr", "text")

    assert cache.get("00000000000000ff", "tr") is None  # 8 bits apart


def test_near_matching_respects_the_language() -> None:
    cache = DescriptionCache()
    cache.put("0000000000000000", "tr", "text")

    assert cache.get("0000000000000003", "en") is None


def test_the_closest_entry_wins() -> None:
    cache = DescriptionCache()
    cache.put("0000000000000000", "tr", "closest")
    cache.put("0000000000000007", "tr", "further")

    assert cache.get("0000000000000001", "tr") == "closest"


def test_different_images_do_not_collide() -> None:
    cache = DescriptionCache()
    cache.put(HASH_A, "tr", "first")
    cache.put(HASH_B, "tr", "second")

    assert cache.get(HASH_A, "tr") == "first"
    assert cache.get(HASH_B, "tr") == "second"


def test_an_empty_description_is_never_cached() -> None:
    """A transient failure would otherwise be served from cache forever."""
    cache = DescriptionCache()
    cache.put(HASH_A, "tr", "")

    assert cache.get(HASH_A, "tr") is None


def test_hits_and_misses_are_counted() -> None:
    cache = DescriptionCache()
    cache.put(HASH_A, "tr", "text")

    cache.get(HASH_A, "tr")
    cache.get(HASH_A, "tr")
    cache.get(HASH_B, "tr")

    stats = cache.stats()
    assert (stats.hits, stats.misses) == (2, 1)
    assert stats.hit_rate == pytest.approx(2 / 3)


def test_hit_rate_is_none_before_any_lookup() -> None:
    """Reporting 0% before any traffic would misrepresent an idle cache."""
    assert DescriptionCache().stats().hit_rate is None


def test_the_oldest_entry_is_evicted_first() -> None:
    cache = DescriptionCache(max_entries=2)
    cache.put("0000000000000000", "tr", "one")
    cache.put("0f0f0f0f0f0f0f0f", "tr", "two")
    cache.put("ffffffffffffffff", "tr", "three")

    assert cache.get("0000000000000000", "tr") is None
    assert cache.get("0f0f0f0f0f0f0f0f", "tr") == "two"
    assert cache.get("ffffffffffffffff", "tr") == "three"


def test_reading_an_entry_keeps_it_alive() -> None:
    """LRU, not FIFO: a frequently-requested image should not be evicted."""
    cache = DescriptionCache(max_entries=2)
    cache.put("0000000000000000", "tr", "one")
    cache.put("0f0f0f0f0f0f0f0f", "tr", "two")

    cache.get("0000000000000000", "tr")  # refreshes the first
    cache.put("ffffffffffffffff", "tr", "three")  # evicts the now-oldest

    assert cache.get("0000000000000000", "tr") == "one"
    assert cache.get("0f0f0f0f0f0f0f0f", "tr") is None


def test_a_zero_capacity_cache_is_a_bug() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        DescriptionCache(max_entries=0)
