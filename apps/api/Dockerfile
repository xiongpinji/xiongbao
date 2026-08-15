FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1
WORKDIR /build

COPY requirements.lock build-requirements.lock ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.lock \
    && python -m venv /opt/build-venv \
    && /opt/build-venv/bin/pip install --no-cache-dir --require-hashes -r build-requirements.lock

COPY pyproject.toml README.md ./
COPY xagent ./xagent
RUN /opt/build-venv/bin/pip wheel --no-build-isolation --no-deps --wheel-dir /tmp/wheels . \
    && /opt/venv/bin/pip install --no-cache-dir --no-deps /tmp/wheels/xagent-*.whl


FROM python:3.11-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    XAGENT_DATA_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 xagent \
    && useradd --uid 10001 --gid 10001 --no-create-home xagent

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY scripts/post_deploy_summary.py ./scripts/post_deploy_summary.py
COPY scripts/collect_ops_evidence.py ./scripts/collect_ops_evidence.py
COPY scripts/auto_archive_evidence.py ./scripts/auto_archive_evidence.py

RUN mkdir -p /data \
    && chown 10001:10001 /data

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["uvicorn", "xagent.main:app", "--host", "0.0.0.0", "--port", "8000"]
