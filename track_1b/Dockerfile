FROM python:3.12.7-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /opt/scrutineer
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

WORKDIR /work
ENTRYPOINT ["scripts/make_run.sh"]
