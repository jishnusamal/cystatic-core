# ==============================================================================
# Builder Stage: Install Python dependencies using uv
# ==============================================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Enable byte-code compilation
ENV UV_COMPILE_BYTECODE=1

# Copy only dependency specification files to cache layer
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ==============================================================================
# Runner Stage: Lean execution environment with Infisical CLI
# ==============================================================================
FROM python:3.12-slim-bookworm AS runner

WORKDIR /app

# Ensure stdout/stderr are unbuffered and prevent writing .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Install system dependencies & Infisical CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && curl -1sLf 'https://artifacts-cli.infisical.com/setup.deb.sh' | bash \
    && apt-get update \
    && apt-get install -y --no-install-recommends infisical \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy the application source code
COPY . /app

# Setup non-root user for secure container execution
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

LABEL org.opencontainers.image.source="https://github.com/usefactorapp/cystatic-core" \
    org.opencontainers.image.title="cystatic-core" \
    org.opencontainers.image.description="Factor API Server" \
    org.opencontainers.image.url="https://github.com/usefactorapp/cystatic-core" \
    org.opencontainers.image.authors="Factor Team" \
    org.opencontainers.image.vendor="Factor" \
    org.opencontainers.image.version="1.0.0"

# Expose port 8000
EXPOSE 8000

# Run the FastAPI server using Infisical to inject secrets at startup
CMD ["infisical", "run", "--projectId=575f4f6e-86c7-43c0-8324-af00e2aa91a0", "--env=prod", "--", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "80"]