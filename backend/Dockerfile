# syntax=docker/dockerfile:1
#
# Two stages: dependencies are resolved once and the result is copied into a clean
# runtime image, so a code-only change does not re-resolve the environment.
#
# Phase 3 adds torch from the CPU-only wheel index (configured in pyproject.toml).
# The production server has no GPU; the default PyPI wheels would pull in roughly
# 2.5 GB of CUDA libraries that could never execute.

FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, without the project itself: this layer is cached until
# pyproject.toml or uv.lock actually change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.12-slim-bookworm AS runtime

# Runs as a non-root user: the process only ever needs to read its own code and
# write to a temporary directory.
RUN useradd --create-home --uid 1000 biovision

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder --chown=biovision:biovision /app/.venv /app/.venv
COPY --chown=biovision:biovision src ./src
COPY --chown=biovision:biovision pyproject.toml ./

# Populated at deploy time from a mounted volume rather than baked in: checkpoints
# are large, change independently of the code, and are AGPL-encumbered artifacts we
# do not want inside a distributable image.
RUN mkdir -p /app/weights && chown biovision:biovision /app/weights

USER biovision
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# ---------------------------------------------------------------------------
#  TWO WORKERS. NOT FOUR.
#  Each uvicorn worker loads its own full copy of CLIP and YOLO into RAM. On the
#  8 GB production box, two fit; four exhaust memory and take the machine down.
#  Raising this number is a hardware decision, not a throughput knob.
# ---------------------------------------------------------------------------
CMD ["uvicorn", "biovision.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
