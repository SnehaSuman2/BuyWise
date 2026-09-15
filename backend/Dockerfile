FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN mkdir -p app && pip install -e ".[dev]"
COPY . .
RUN useradd -m buywise && chown -R buywise:buywise /app
USER buywise
# Some hosts (Render, etc.) inject PORT at runtime and expect the container to bind
# to it; others (docker-compose, Hugging Face) expect the EXPOSEd port. Support both.
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD sh -c "curl -fs http://localhost:${PORT}/health || exit 1"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 2"]
