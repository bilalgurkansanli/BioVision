"""The model registry: everything loaded once, at startup, and held for the process.

Loading happens in the FastAPI ``lifespan`` handler, never inside a request. On a
CPU-only box, loading CLIP per request would put multiple seconds on every call.

Memory note, repeated wherever workers are configured: **each uvicorn worker holds
its own copy of every model**. Two workers on the 8 GB production box is the
ceiling; four exhausts RAM and takes the machine down.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from biovision.config import ModelBackend, Settings
from biovision.domains.catalog import DomainCatalog, DomainCatalogError
from biovision.models.base import (
    GateModel,
    RouterModel,
    SeverityModel,
    SpecialistModel,
    VLMClient,
)
from biovision.models.mock import MockGate, MockRouter, MockSpecialist, MockVLM
from biovision.models.specialists import KNOWN_SPECIALISTS
from biovision.pipeline.redact import Redactor, build_redactor
from biovision.schemas.health import ComponentHealth
from biovision.storage.cache import DescriptionCache

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
    cache: DescriptionCache
    """pHash-keyed description cache. A repeated image never reaches the paid API twice."""
    severity: SeverityModel | None = None
    """Whole-photograph severity. Optional: absent under the mock backend, and the
    response then carries `overall_severity: null` rather than a guess."""

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
        registry = _build_real_registry(settings, catalog, redactor)

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
        cache=DescriptionCache(),
        # No severity estimator under mock: it needs the CLIP encoder, and the
        # mock backend exists to run without weights. `overall_severity` is then
        # null, which is the same honest answer as a domain with no specialist.
    )


def _build_real_registry(
    settings: Settings, catalog: DomainCatalog, redactor: Redactor
) -> ModelRegistry:
    """Load the real zero-shot models.

    Imported lazily so that the mock backend -- which is what CI and local
    development run -- never pays torch's multi-second import cost.
    """
    # -----------------------------------------------------------------------
    #  Found by running the container, not by reading the code.
    #
    #  With the weights directory absent or misdirected -- a mount pointing at
    #  the wrong path is the easy mistake -- huggingface_hub silently fell back
    #  to downloading. With no egress it then retried DNS five times with
    #  exponential backoff and blocked inside the lifespan handler. The result
    #  was the worst failure mode available: the container sat in `running` with
    #  exit code 0 and nothing listening on 8000. Nothing crashed, so
    #  `restart: unless-stopped` never fired, and the cause was a DNS warning
    #  forty lines deep in the log.
    #
    #  Offline mode turns that into an immediate, legible error -- but only if it
    #  is set BEFORE huggingface_hub is imported, because it reads the variable
    #  once into a module constant. Hence above the lazy imports, not below them:
    #  the first attempt at this fix sat under them and changed nothing.
    # -----------------------------------------------------------------------
    if settings.require_local_weights:
        os.environ["HF_HUB_OFFLINE"] = "1"

    from biovision.domains.gate import GatePrompts
    from biovision.domains.severity import SeverityPrompts
    from biovision.models.calibration import CALIBRATION_FILENAME, load_calibration
    from biovision.models.clip import ClipEncoder
    from biovision.models.clip_gate import ClipGate
    from biovision.models.clip_router import ClipRouter
    from biovision.models.clip_severity import ClipSeverityEstimator

    try:
        # ONE encoder, shared by both layers. The gate and the router are different
        # questions asked of the same embedding; loading two would double the largest
        # allocation in the process, and each worker holds its own copy.
        encoder = ClipEncoder(
            model_name=settings.clip_model,
            pretrained=settings.clip_pretrained,
            cache_dir=settings.weights_path,
            num_threads=settings.torch_num_threads,
        )
    except Exception as exc:
        if not settings.require_local_weights:
            raise
        raise RuntimeError(
            f"CLIP weights were not found under {settings.weights_path}. In production "
            "this directory is a read-only mount and is never downloaded into. Check "
            "that the volume points at the directory holding "
            f"'models--laion--CLIP-{settings.clip_model}-*', and run "
            "scripts/fetch_weights.py on the host if it is empty. Set "
            "BIOVISION_REQUIRE_LOCAL_WEIGHTS=false to allow a download instead."
        ) from exc

    calibration = load_calibration(
        settings.weights_path / CALIBRATION_FILENAME, expected_model_id=encoder.name
    )

    from biovision.models.specialists.vehicle_yolo import build_vehicle_specialist
    from biovision.models.vlm.client import build_vlm

    specialists: dict[str, SpecialistModel] = {}
    vehicle = build_vehicle_specialist(
        settings.weights_path,
        settings.torch_num_threads,
        confidence_threshold=settings.specialist_min_confidence,
    )
    if vehicle is not None:
        specialists["vehicle_yolo"] = vehicle
    # A missing checkpoint is not an error. The vehicle domain then behaves like
    # every other domain without a specialist, and the API says `specialist_model:
    # null` -- the same honest answer, not a degraded one.

    return ModelRegistry(
        backend="real",
        catalog=catalog,
        gate=ClipGate(
            encoder=encoder,
            prompts=GatePrompts.load(settings.gate_prompts_path),
            threshold=settings.gate_threshold,
        ),
        router=ClipRouter(encoder=encoder, catalog=catalog, calibration=calibration),
        specialists=specialists,
        vlm=build_vlm(
            api_key=settings.anthropic_api_key,
            monthly_limit_usd=settings.vlm_monthly_budget_usd,
            workers=settings.uvicorn_workers,
            warn_ratio=settings.vlm_budget_warn_ratio,
            model=settings.vlm_model,
        )
        if settings.vlm_enabled
        else None,
        redactor=redactor,
        cache=DescriptionCache(),
        # Same encoder a third time. This layer adds a dot product against 12
        # cached text vectors and no new weights -- see clip_severity for why it
        # answers a question the specialist cannot.
        severity=ClipSeverityEstimator(
            encoder=encoder, prompts=SeverityPrompts.load(settings.severity_prompts_path)
        ),
    )


def _verify_specialists_resolve(catalog: DomainCatalog, registry: ModelRegistry) -> None:
    """Check `domains.yaml` against the specialist names the code actually defines.

    Two different situations, which must not be conflated:

    * **Unknown name** -- `domains.yaml` refers to something no module implements.
      That is a typo, and it is fatal. Adding a domain is a one-line edit, which
      makes a mistyped `specialist:` easy; without this check it would produce a
      domain reporting "no specialist available" forever, a wrong answer wearing
      the costume of an honest one.

    * **Known name, not loaded in this backend** -- the implementation exists but
      this process did not load it, which is exactly where the real backend sits
      before Phase 5. Not an error: the domain behaves as though it has no
      specialist, and the API says so. That is the honest answer, and it is the
      same one every other domain gets.
    """
    unknown = [
        (spec.key, spec.specialist)
        for spec in catalog.with_specialist()
        if spec.specialist not in KNOWN_SPECIALISTS
    ]
    if unknown:
        details = ", ".join(f"{domain} -> '{name}'" for domain, name in unknown)
        raise DomainCatalogError(
            f"domains.yaml names specialists that do not exist in the code: {details}. "
            f"Known names: {sorted(KNOWN_SPECIALISTS)}"
        )

    not_loaded = [
        (spec.key, spec.specialist)
        for spec in catalog.with_specialist()
        if spec.specialist not in registry.specialists
    ]
    for domain, name in not_loaded:
        logger.warning(
            "specialist '%s' for domain '%s' is not loaded in the '%s' backend; "
            "that domain will report specialist_model=null",
            name,
            domain,
            registry.backend,
        )
