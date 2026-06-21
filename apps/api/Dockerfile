FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev curl && rm -rf /var/lib/apt/lists/*

# 先复制元数据 + 源码（pyproject 引用 README，需一并复制）
COPY pyproject.toml README.md ./
COPY xagent ./xagent
COPY migrations ./migrations
COPY alembic.ini ./

# 装构建后端再装包（非 editable，避免 hatchling editable 元数据问题）
RUN pip install --upgrade pip hatchling && pip install ".[dev]" && \
    pip install "bcrypt==4.0.1" --force-reinstall --no-deps

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "xagent.main:app", "--host", "0.0.0.0", "--port", "8000"]
