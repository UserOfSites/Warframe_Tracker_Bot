FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH

COPY pyproject.toml ./
COPY titania ./titania
RUN pip install .


FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/venv/bin:$PATH \
    DB_PATH=/data/titania.db

RUN useradd --create-home --uid 1000 titania \
 && mkdir -p /data \
 && chown titania:titania /data

COPY --from=builder /venv /venv

USER titania
WORKDIR /app

VOLUME ["/data"]

CMD ["python", "-m", "titania"]
