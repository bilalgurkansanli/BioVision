"""The model registry: everything loaded once, at startup, and held for the process.

Loading happens in the FastAPI ``lifespan`` handler, never inside a request. On a
CPU-only box, loading CLIP per request would put multiple seconds on every call.

Memory note, repeated wherever workers are configured: **each uvicorn worker holds
its own copy of every model**. Two workers on the 8 GB production box is the
ceiling; four exhausts RAM and takes the machine down.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from biovision.config import ModelBackend, Settings
from biovision.domains.catalog import DomainCatalog, DomainCatalogError
from biovision.models.base import GateModel, RouterModel, SpecialistModel, VLMClient
from biovision.models.mock import MockGate, MockRouter, MockSpecialist, MockVLM
from biovision.models.specialists import KNOWN_SPECIALISTS
from biovision.pipeline.redact import Redactor, build_redactor
from biovision.schemas.health import ComponentHealth

logger = logging.getLogger(__name__)


@dataclass
class ModelRegistry:
    """Every model the application can run, plus the catalogue that indexes them."""

    backend: ModelBackend
    catalog: DomainCatalog
    gate: GateModel
    router: RouterModel
    specialists: dict[str, SpecialistModel]
    """Keyed by the specialist name used in domains.yaml, not by domain key."""
    vlm: VLMClient | None
    redactor: Redactor
    """Face/plate redaction. Loaded here because it owns weights like any other model."""

    def specialist_for(self, domain: str) -> SpecialistModel | None:
        """The specialist for a domain, or ``None``.

        ``None`` is a first-class answer here, not an error path. Most domains have
        no specialist, and saying so is the point of the product.
        """
        spec = self.catalog.get(domain)
        if spec is None or spec.specialist is None:
            return None
        return self.specialists.get(spec.specialist)

    @property
    def ready(self) -> bool:
        """True when every component required to serve a request is loaded.

        The VLM is excluded on purpose: it is a fallback, and a missing VLM
        degrades the service rather than breaking it.
        """
        specialists_ready = all(model.ready for model in self.specialists.values())
        return self.gate.ready and self.router.ready and specialists_ready

    def components(self) -> list[ComponentHealth]:
        parts = [
            ComponentHealth(name=self.gate.name, ready=self.gate.ready, detail="gate"),
            ComponentHealth(name=self.router.name, ready=self.router.ready, detail="router"),
        ]
        parts.extend(
            ComponentHealth(name=model.name, ready=model.ready, detail=f"specialist:{model.domain}")
            for model in self.specialists.values()
        )
        parts.append(
            ComponentHealth(
                name=self.vlm.name if self.vlm else "vlm",
                ready=self.vlm.ready if self.vlm else False,
                detail="fallback (optional)",
            )
        )
        # Reported per class so an operator can see at a glance which kinds of
        # region are actually being redacted, rather than inferring it from a
        # single boolean.
        for label, detector in (
            ("face", self.redactor.face_detector_name),
            ("plate", self.redactor.plate_detector_name),
        ):
            parts.append(
                ComponentHealth(
                    name=detector or f"{label}-redaction-disabled",
                    ready=detector is not None,
                    detail=f"redaction:{label}",
                )
            )
        return parts


def build_registry(settings: Settings) -> ModelRegistry:
    """Load the catalogue and every model named by it."""
    catalog = DomainCatalog.load(settings.domains_path)
    logger.info(
        "domain catalogue loaded: %d domains (%d with a specialist)",
        len(catalog),
        len(catalog.with_specialist()),
    )

    # Redaction is independent of the model backend: it is real image processing,
    # not inference, so it runs the same way whether the analysis models are mocks
    # or checkpoints. If its weights are absent it reports itself as absent.
    redactor = build_redactor(settings.weights_path)

    if settings.model_backend == "mock":
        registry = _build_mock_registry(settings, catalog, redactor)
    else:
        # Phase 3 wires CLIP/SigLIP here; Phase 5 adds the CarDD specialist.
        raise NotImplementedError(
            "model_backend='real' is not implemented yet -- it arrives in Phase 3. "
            "Set BIOVISION_MODEL_BACKEND=mock."
        )

    _verify_specialists_resolve(catalog, registry)
    return registry


def _build_mock_registry(
    settings: Settings, catalog: DomainCatalog, redactor: Redactor
) -> ModelRegistry:
    specialists: dict[str, SpecialistModel] = {}
    for spec in catalog.with_specialist():
        assert spec.specialist is not None  # guaranteed by with_specialist()
        # Only names with a real implementation behind them get a mock. Building a
        # mock for whatever the YAML happens to say would make the mock backend
        # accept typos that the real backend would reject -- which would defeat the
        # purpose of testing against mocks in the first place.
        if spec.specialist not in KNOWN_SPECIALISTS:
            continue
        specialists[spec.specialist] = MockSpecialist(
            domain=spec.key, name=f"mock-{spec.specialist}-v1"
        )

    return ModelRegistry(
        backend="mock",
        catalog=catalog,
        gate=MockGate(threshold=settings.gate_threshold),
        router=MockRouter(domain_keys=catalog.keys),
        specialists=specialists,
        vlm=MockVLM() if settings.vlm_enabled else None,
        redactor=redactor,
    )


def _verify_specialists_resolve(catalog: DomainCatalog, registry: ModelRegistry) -> None:
    """Fail at startup if `domains.yaml` names a specialist that does not exist.

    Adding a domain is meant to be a one-line change, which makes a typo in the
    `specialist:` field an easy mistake. Catching it here turns that mistake into a
    loud startup failure instead of a domain that silently reports "no specialist".
    """
    missing = [
        (spec.key, spec.specialist)
        for spec in catalog.with_specialist()
        if spec.specialist not in registry.specialists
    ]
    if missing:
        details = ", ".join(f"{domain} -> '{name}'" for domain, name in missing)
        raise DomainCatalogError(
            f"domains.yaml names specialists that are not registered: {details}. "
            f"Registered names: {sorted(registry.specialists)}"
        )
