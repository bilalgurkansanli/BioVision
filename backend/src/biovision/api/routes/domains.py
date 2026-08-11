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
                specialist_model=model.name if model else None,
                calibrated=model is not None,
            )
        )

    return DomainsResponse(
        domains=infos,
        count=len(infos),
        with_specialist=sum(1 for info in infos if info.has_specialist),
    )
