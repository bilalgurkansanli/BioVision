"""Scoring helpers.

Pure numpy, so these run without torch on the import path -- which is the reason
they live outside `clip.py` in the first place.
"""

from __future__ import annotations

import numpy as np
import pytest

from biovision.models.scoring import softmax, unit


def test_softmax_sums_to_one() -> None:
    assert float(softmax(np.array([3.0, 1.0, 0.2])).sum()) == pytest.approx(1.0)


def test_softmax_preserves_ordering() -> None:
    logits = np.array([1.0, 5.0, 3.0])

    assert np.argsort(softmax(logits)).tolist() == np.argsort(logits).tolist()


def test_softmax_is_numerically_stable() -> None:
    """CLIP's learned logit scale is ~100, so large logits are routine here.

    A naive exp overflows to inf and the result becomes nan.
    """
    result = softmax(np.array([800.0, 799.0, 1.0], dtype=np.float32))

    assert np.isfinite(result).all()
    assert float(result.sum()) == pytest.approx(1.0)
    assert int(np.argmax(result)) == 0


def test_softmax_of_equal_logits_is_uniform() -> None:
    result = softmax(np.zeros(4, dtype=np.float32))

    assert result == pytest.approx(np.full(4, 0.25), abs=1e-6)


def test_unit_normalises_to_length_one() -> None:
    result = unit(np.array([3.0, 4.0], dtype=np.float32))

    assert float(np.linalg.norm(result)) == pytest.approx(1.0)
    assert result == pytest.approx(np.array([0.6, 0.8]), abs=1e-6)


def test_unit_preserves_direction() -> None:
    vector = np.array([1.0, -2.0, 3.0], dtype=np.float32)
    normalised = unit(vector)

    assert float(vector @ normalised) > 0
    assert np.allclose(normalised * float(np.linalg.norm(vector)), vector, atol=1e-5)


def test_unit_survives_the_zero_vector() -> None:
    """Not reachable from a real embedding, but a division by zero would be a nan
    that propagates silently through every downstream score."""
    result = unit(np.zeros(3, dtype=np.float32))

    assert np.isfinite(result).all()
    assert float(result.sum()) == 0.0
