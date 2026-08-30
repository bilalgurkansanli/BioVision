"""Mapping domain exceptions onto HTTP responses.

One place, one table. The status codes documented in the README are the ones
produced here, and a contract test walks every ``BioVisionError`` subclass to make
sure none of them can escape as an untyped 500.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from biovision.errors import BioVisionError
from biovision.schemas.enums import ErrorCode
from biovision.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _envelope(status_code: int, detail: ErrorDetail) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=detail).model_dump(mode="json"),
    )


async def biovision_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BioVisionError)
    logger.info("%s -> %d: %s", exc.code.value, exc.status_code, exc.message)
    return _envelope(exc.status_code, ErrorDetail(code=exc.code, message=exc.message))


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """FastAPI request-validation failures.

    **A body failure is 415; anything else is 422.**

    The upload endpoint reports 415 rather than the framework default, because
    there the only way to fail validation is to omit the file or send something
    that is not a multipart upload -- and keeping 422 exclusively for "the gate
    rejected your photograph" makes that status unambiguous.

    That reasoning was written when `/v1/analyze` was the only endpoint taking
    input, and it was baked into a handler registered for the whole app. Adding
    `/v1/claims`, whose inputs are query parameters, made it wrong: a missing
    `vehicle_value_try` came back as "send a multipart body with an image file".
    The discriminator is now the error's own location rather than an assumption
    about which endpoint is being called.
    """
    assert isinstance(exc, RequestValidationError)
    logger.info("request validation failed: %s", exc.errors())

    from_body = any(
        error.get("loc", (None,))[0] == "body" for error in exc.errors()
    )

    if from_body:
        return _envelope(
            415,
            ErrorDetail(
                code=ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                message="Malformed request. Send a multipart/form-data body with an 'image' file.",
            ),
        )

    fields = ", ".join(
        ".".join(str(part) for part in error.get("loc", ())[1:]) or "?"
        for error in exc.errors()
    )
    return _envelope(
        422,
        ErrorDetail(
            code=ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            message=f"Invalid or missing parameter: {fields}",
        ),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort.

    The traceback goes to the logs with a correlation id; the client gets the id and
    nothing else. Leaking internals into an error body is how stack traces end up in
    a screenshot.
    """
    incident = uuid4()
    logger.exception("unhandled error incident=%s path=%s", incident, request.url.path)
    return _envelope(
        500,
        ErrorDetail(
            code=ErrorCode.SERVICE_DEGRADED,
            message="Internal error. Quote the request_id when reporting this.",
            request_id=incident,
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BioVisionError, biovision_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
