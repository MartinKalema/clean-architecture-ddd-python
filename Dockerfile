FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system -e .

COPY src/ src/
COPY scripts/ scripts/
COPY migrations/ migrations/
# Index mappings are needed at runtime by scripts/reindex_read_models.py
COPY deploy/elasticsearch/mappings/ deploy/elasticsearch/mappings/
COPY alembic.ini .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# One worker per container: scaling is horizontal via API container
# replicas. A single process keeps circuit breaker state and
# /health/circuits coherent per container.
CMD ["uvicorn", "--factory", "src.presentation.api.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
