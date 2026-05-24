# backend/Dockerfile
# Uses official uv image — no pip, no requirements.txt, no venv activation
FROM ghcr.io/astral-sh/uv:python3.12-alpine AS base

WORKDIR /app
# Compile bytecode + use copy mode (better for containers)
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── Development ───────────────────────────────────────────────────────────────
FROM base AS development

# Install deps first (Docker layer cache — only re-runs on pyproject.toml change)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --all-groups

COPY . .
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production ────────────────────────────────────────────────────────────────
FROM base AS production

# No dev deps in production
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev

COPY . .
ENV PATH="/app/.venv/bin:$PATH"

# Non-root user
RUN adduser -D appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--no-access-log"]