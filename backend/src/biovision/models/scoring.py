"""Scoring helpers shared by the zero-shot layers.

Pure numpy, deliberately. These live outside `clip.py` because that module imports
torch and open_clip, and importing a four-line softmax should not drag several
hundred megabytes of deep-learning framework into a process -- or into a test run
that never touches a model.
"""

from __future__ import annotations

import numpy as np


def softmax(logits: np.ndarray) -> np.ndarray:
    """Numerically stable softmax over a 1-D array.

    Subtracting the maximum before exponentiating is not optional here: CLIP's
    learned logit scale is around 100, so raw logits routinely reach magnitudes
    where a naive ``exp`` overflows to infinity.
    """
    shifted = logits - np.max(logits)
    exponentiated = np.exp(shifted)
    result: np.ndarray = (exponentiated / exponentiated.sum()).astype(np.float32)
    return result


def unit(vector: np.ndarray) -> np.ndarray:
    """L2-normalise, guarding the degenerate zero vector."""
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        return vector.astype(np.float32)
    result: np.ndarray = (vector / norm).astype(np.float32)
    return result
