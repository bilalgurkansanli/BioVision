"""Domain discovery."""

from __future__ import annotations

from fastapi import APIRouter

from biovision.api.deps import RegistryDep
from biovision.schemas.domains import DomainInfo, DomainsResponse

router = APIRouter(prefix="/v1", tags=["domains"])


@router.get("/domains", response_model=DomainsResponse, summary="Supported domains")
def list_domains(registry: RegistryDep) -> DomainsResponse:
    """List every domain and whether a specialist backs it.

    Rendered from the loaded catalogue, never from a literal list in this file.
    That is what makes "adding a domain is one line in domains.yaml" true rather
    than aspirational -- and it is why a client can discover, without asking us,
    which domains produce measurements and which produce descriptions.
    """
    infos = []
    for spec in registry.catalog.specs:
        model = registry.specialist_for(spec.key)
        infos.append(
            DomainInfo(
                key=spec.key,
                label=spec.label,
                has_specialist=model is not None,
                # Both conditions, matching what /v1/analyze actually returns:
                # a specialist to produce the measurement, and a calibrated router
                # behind the confidence. Deriving this from the specialist alone
                # made this endpoint promise `calibrated: true` for a domain whose
                # analyses return false -- invisible while no specialist existed,
                # and wrong the moment one did.
                specialist_model=model.name if model else None,
                calibrated=model is not None and registry.router.calibrated,
            )
        )

    return DomainsResponse(
        domains=infos,
        count=len(infos),
        with_specialist=sum(1 for info in infos if info.has_specialist),
    )
