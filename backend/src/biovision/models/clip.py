"""The shared CLIP encoder behind both zero-shot layers.

**One model, two consumers.** The gate and the router are different questions asked
of the same embedding, so they share an encoder instance. Loading two would double
the largest single allocation in the process, and with two uvicorn workers each
holding its own copy, that is the difference between fitting in 8 GB and not.

Everything here runs on CPU. There is no GPU on the production box and no code path
that assumes one.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import open_clip
import torch
from PIL import Image

from biovision.models.scoring import unit

logger = logging.getLogger(__name__)

#: ViT-B/32 is the smallest CLIP variant with usable zero-shot behaviour: ~600 MB in
#: fp32, and image encoding stays in the low hundreds of milliseconds on CPU. Larger
#: backbones score better on benchmarks and do not fit the latency budget that keeps
#: this service synchronous (see README section 9).
DEFAULT_MODEL = "ViT-B-32"
DEFAULT_PRETRAINED = "laion2b_s34b_b79k"


class ClipEncoder:
    """Wraps an open_clip model as a pair of embedding functions.

    Text embeddings are computed once, at startup, and reused for every request:
    the prompts come from configuration and never change between requests, so
    re-encoding them per call would be pure waste.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        pretrained: str = DEFAULT_PRETRAINED,
        cache_dir: Path | None = None,
        num_threads: int = 2,
    ) -> None:
        # torch defaults to one thread per core. With two uvicorn workers on four
        # vCPUs, each would spawn four and the eight would contend for the same
        # cores -- measurably slower than not parallelising at all. This is a
        # process-global setting, which is acceptable because each worker is its
        # own process.
        torch.set_num_threads(max(1, num_threads))

        logger.info("loading CLIP %s / %s on CPU", model_name, pretrained)
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name,
            pretrained=pretrained,
            device="cpu",
            cache_dir=str(cache_dir) if cache_dir else None,
        )
        model.eval()

        self._model = model
        self._preprocess = preprocess
        self._tokenizer = open_clip.get_tokenizer(model_name)
        self._name = f"{model_name}/{pretrained}"

        # CLIP learns this scale during training (~100). Applying it is what turns
        # cosine similarities in [-1, 1] into logits with a usable dynamic range;
        # a softmax over raw cosines is nearly uniform and carries no signal.
        self._logit_scale = float(model.logit_scale.exp().detach())

        # Single-entry image-embedding cache, keyed by perceptual hash.
        #
        # The gate and the router ask different questions of the *same* embedding
        # and run back to back on the same image. Without this they each encode it,
        # doubling the most expensive operation in the request -- measured at ~100 ms
        # per encode on CPU, which is roughly a third of end-to-end latency.
        #
        # Stored as one tuple so a concurrent overwrite cannot produce a key paired
        # with someone else's embedding: the read below takes a single reference,
        # and tuple assignment is atomic under the GIL.
        self._cache: tuple[str, np.ndarray] | None = None

        logger.info("CLIP ready: %s, logit_scale=%.2f", self._name, self._logit_scale)

    @property
    def name(self) -> str:
        return self._name

    @property
    def logit_scale(self) -> float:
        return self._logit_scale

    @torch.no_grad()
    def encode_image(self, rgb: np.ndarray, cache_key: str | None = None) -> np.ndarray:
        """Embed one RGB uint8 array as a unit-length float32 vector.

        Args:
            cache_key: Identifier for these pixels -- callers pass the perceptual
                hash. When it matches the previous call, the cached embedding is
                returned instead of re-encoding. Passing ``None`` always computes.
        """
        cached = self._cache
        if cache_key is not None and cached is not None and cached[0] == cache_key:
            return cached[1]

        tensor: Any = self._preprocess(Image.fromarray(rgb, mode="RGB"))
        features = self._model.encode_image(tensor.unsqueeze(0))
        embedding = unit(features.squeeze(0).numpy().astype(np.float32))

        if cache_key is not None:
            self._cache = (cache_key, embedding)
        return embedding

    @torch.no_grad()
    def encode_images(self, crops: list[np.ndarray]) -> np.ndarray:
        """Embed several RGB arrays in ONE forward pass, as (N, D) unit rows.

        Added for the building specialist's tile veto, which asks the encoder
        seventeen questions about one photograph. Seventeen sequential calls to
        `encode_image` measured at roughly 1.5 s on the production CPU; the same
        crops through one batched pass are far cheaper, because the per-call
        overhead dominates at this size rather than the arithmetic.

        Deliberately not cached: the cache is keyed on a whole image's
        perceptual hash and exists so the gate and router can share one
        embedding. Tiles are not that image, and quietly returning a cached
        frame embedding for a crop would be a correctness bug wearing a
        performance win's clothes.
        """
        if not crops:
            raise ValueError("encode_images needs at least one crop")

        batch: Any = torch.stack(
            [self._preprocess(Image.fromarray(crop, mode="RGB")) for crop in crops]
        )
        features = self._model.encode_image(batch).numpy().astype(np.float32)
        return np.stack([unit(row) for row in features])

    @torch.no_grad()
    def encode_texts(self, prompts: list[str]) -> np.ndarray:
        """Embed prompts as an (N, D) array of unit-length rows."""
        if not prompts:
            raise ValueError("encode_texts needs at least one prompt")

        tokens = self._tokenizer(prompts)
        features = self._model.encode_text(tokens).numpy().astype(np.float32)
        return np.stack([unit(row) for row in features])

    def embed_prompt_ensemble(self, prompts: list[str]) -> np.ndarray:
        """Average several phrasings of the same concept into one direction.

        Zero-shot classification from a single prompt is unstable -- the wording
        moves the result as much as the image does. Averaging unit vectors and
        renormalising is the standard remedy and is why `domains.yaml` asks for
        several prompts per domain rather than one.
        """
        return unit(self.encode_texts(prompts).mean(axis=0))
