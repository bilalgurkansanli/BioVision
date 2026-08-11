"""The VLM fallback client.

Reached **only** when a domain has no specialist. Vehicle photographs — the common
case — never touch it, which is the primary cost control: the expensive path is the
one that runs rarely, by construction rather than by policy.

What it returns is a *description*, never a measurement. The response schema keeps
`vlm_description` and `findings` apart, and a validator refuses a response that
carries both. Nothing here parses the model's prose into structure; if a domain
needs structured output, the answer is to train a specialist for it.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from biovision.models.vlm.budget import MonthlyBudget
from biovision.pipeline.types import PreparedImage

logger = logging.getLogger(__name__)

#: Claude Haiku 4.5 -- vision-capable, $1/$5 per million tokens, and the cheapest
#: model that produces a usable paragraph. Alias rather than a dated snapshot.
DEFAULT_MODEL = "claude-haiku-4-5"

#: A description, not an essay. Also a cost lever: output tokens are 5x input.
MAX_OUTPUT_TOKENS = 400

_SYSTEM_PROMPT = """\
You describe damage visible in a photograph for an insurance triage system.

Report only what is visible. Describe the object, the damage you can see, and where \
it appears. If you cannot tell whether something is damage, say so plainly rather \
than guessing.

Do not estimate repair costs, severity ratings, or percentages -- this system has no \
trained model for this kind of photograph, and a number you invent would be read as \
a measurement. Two or three sentences.\
"""

_PROMPTS = {
    "tr": "Bu fotoğrafta görünen hasarı kısaca betimle.",
    "en": "Briefly describe the damage visible in this photograph.",
}


class AnthropicVLM:
    """Free-text description via the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        budget: MonthlyBudget,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("AnthropicVLM requires an API key")

        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds)
        self._model = model
        self._budget = budget
        self._ready = True

        logger.info("VLM fallback ready: %s", model)

    @property
    def name(self) -> str:
        return self._model

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def budget(self) -> MonthlyBudget:
        return self._budget

    def describe(self, image: PreparedImage, language: str) -> str:
        """Describe the image. Raises ServiceDegradedError if the budget is spent."""
        # Checked before the request, so an exhausted budget costs nothing.
        self._budget.ensure_available()

        prompt = _PROMPTS.get(language, _PROMPTS["en"])
        encoded = base64.standard_b64encode(image.stored_bytes).decode("ascii")

        response: Any = self._client.messages.create(
            model=self._model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                # The stored derivative is always JPEG, and it is
                                # what gets sent: already redacted, already stripped
                                # of EXIF, already bounded at 1280 px. The original
                                # upload never leaves this server.
                                "media_type": "image/jpeg",
                                "data": encoded,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        # Charged from reported usage rather than an estimate, so the ledger
        # reflects what was actually billed.
        self._budget.charge(response.usage.input_tokens, response.usage.output_tokens)

        return _extract_text(response)


def _extract_text(response: Any) -> str:
    """Join the text blocks of a response.

    Indexing `content[0]` would break on any response that leads with a non-text
    block, and on a refusal, where `content` is empty.
    """
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    text = " ".join(part.strip() for part in parts if part).strip()

    if not text:
        logger.warning(
            "VLM returned no text (stop_reason=%s)", getattr(response, "stop_reason", None)
        )
        return ""
    return text


def build_vlm(
    api_key: str,
    monthly_limit_usd: float,
    workers: int,
    warn_ratio: float,
    model: str = DEFAULT_MODEL,
) -> AnthropicVLM | None:
    """Construct the VLM client, or ``None`` if it cannot be used.

    ``None`` is a supported state: fallback responses then carry
    ``vlm_description: null`` alongside the warning that already explains there is
    no specialist. Missing configuration disables a feature; it never fabricates one.
    """
    if not api_key:
        logger.warning("no ANTHROPIC_API_KEY -- fallback descriptions are disabled")
        return None

    try:
        return AnthropicVLM(
            api_key=api_key,
            budget=MonthlyBudget(monthly_limit_usd, workers=workers, warn_ratio=warn_ratio),
            model=model,
        )
    except Exception:
        logger.exception("VLM client failed to initialise; descriptions are disabled")
        return None
