"""The analysis endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

from biovision.api.deps import (
    LanguageDep,
    RegistryDep,
    RepositoryDep,
    SettingsDep,
    UserDep,
    enforce_rate_limit,
)
from biovision.errors import FileTooLargeError
from biovision.pipeline.orchestrator import analyze_image
from biovision.schemas.analyze import AnalyzeResponse
from biovision.schemas.errors import ErrorResponse

router = APIRouter(prefix="/v1", tags=["analyze"])

#: Upload read granularity. Small enough that an oversized file is rejected after a
#: few hundred KB rather than after the whole body has been buffered.
_CHUNK_BYTES = 256 * 1024

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    413: {"model": ErrorResponse, "description": "Image exceeds the size limit"},
    415: {"model": ErrorResponse, "description": "Unsupported or animated image format"},
    422: {"model": ErrorResponse, "description": "Rejected by the gate, or unreadable image"},
    429: {"model": ErrorResponse, "description": "Daily request quota exceeded"},
    503: {"model": ErrorResponse, "description": "VLM budget exhausted (service_degraded)"},
}


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses=_ERROR_RESPONSES,
    dependencies=[Depends(enforce_rate_limit)],
    summary="Analyze one damage photograph",
)
async def analyze(
    settings: SettingsDep,
    registry: RegistryDep,
    language: LanguageDep,
    user: UserDep,
    repository: RepositoryDep,
    image: UploadFile = File(description="JPEG, PNG, WebP or HEIC, at most 10 MB."),
) -> AnalyzeResponse:
    """Gate, route, then either measure with a specialist or describe honestly.

    The handler stays thin on purpose: the order of operations lives in
    ``pipeline.orchestrator``, so "what happens to an image" has exactly one answer.
    """
    raw = await _read_capped(image, settings.max_upload_bytes)

    # Inference is CPU-bound and synchronous. Running it in the threadpool keeps the
    # event loop free to accept and reject other requests -- notably the cheap 413
    # and 429 paths -- while a model is busy. torch releases the GIL during
    # inference, so this is real overlap rather than bookkeeping.
    result = await run_in_threadpool(
        analyze_image,
        raw,
        settings=settings,
        registry=registry,
        language=language,
        # Anonymous demo traffic may use the specialist path but never the paid
        # fallback. This is the mechanism that makes a public demo link safe to
        # publish: unauthenticated callers cannot spend the monthly VLM budget.
        vlm_allowed=user is not None,
    )

    # Anonymous analyses are not stored at all. Nobody could ever retrieve or
    # delete them, so keeping the image would be collecting data with no owner
    # and no purpose.
    if user is not None:
        await run_in_threadpool(
            repository.save,
            result.response,
            user.id,
            user.access_token,
            result.image.phash,
            result.image.stored_bytes,
        )

    return result.response


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read the upload, aborting as soon as it exceeds the limit.

    Streaming rather than ``await file.read()`` so a 500 MB body is refused after a
    few hundred kilobytes instead of being buffered in full first.
    """
    chunks: list[bytes] = []
    total = 0

    while chunk := await file.read(_CHUNK_BYTES):
        total += len(chunk)
        if total > max_bytes:
            raise FileTooLargeError(f"Image exceeds the {max_bytes / 1_048_576:.0f} MB limit.")
        chunks.append(chunk)

    return b"".join(chunks)
