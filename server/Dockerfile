# bbz-api container. Multi-stage, non-root (SECURITY.md: containers not as root).
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# --- dependency layer ---
FROM base AS deps
COPY packages/integration-sdk /src/packages/integration-sdk
COPY packages/rule-dsl /src/packages/rule-dsl
COPY packages/event-schemas /src/packages/event-schemas
COPY server /src/server
RUN pip install /src/packages/integration-sdk /src/packages/rule-dsl \
        /src/packages/event-schemas /src/server

# --- runtime ---
FROM base AS runtime
RUN useradd --system --uid 10001 --home /app bbz
# Copy the whole lib tree so the Python minor version is not hardcoded here
# (base image bumps must not silently break this multi-stage copy).
COPY --from=deps /usr/local/lib/ /usr/local/lib/
COPY --from=deps /usr/local/bin /usr/local/bin
COPY server/alembic.ini /app/alembic.ini
COPY server/alembic /app/alembic
USER bbz
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/live').status==200 else 1)"
CMD ["python", "-m", "bbz_core.main"]
