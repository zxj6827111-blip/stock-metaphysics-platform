# ---- 后端 API 镜像 ----
# 使用 Python 3.12：AKShare 与 numpy/pandas 在该版本上轮子最齐全
FROM python:3.12-slim AS api

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 系统依赖：akshare 的间接依赖与 sqlite 需要
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖，利用 Docker layer cache
COPY pyproject.toml README.md ./
COPY src ./src
COPY apps ./apps
RUN python -m pip install --upgrade pip \
    && python -m pip install -e ".[dev]"

COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
COPY knowledge ./knowledge
COPY tests ./tests

# 数据目录（可挂载卷持久化）
RUN mkdir -p /app/data
ENV SMP_DATA_DIR=/app/data \
    SMP_DATABASE_URL=sqlite:////app/data/smp.sqlite3

EXPOSE 8000

# 启动前自动执行 migration，保证 schema 与代码一致
CMD ["sh", "-c", "python -m alembic upgrade head && python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000"]
