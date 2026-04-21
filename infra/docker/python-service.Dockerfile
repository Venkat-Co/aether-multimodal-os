FROM python:3.12-slim AS builder

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY packages ./packages
COPY services ./services

RUN pip install --upgrade pip && pip install .

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG SERVICE_MODULE
ARG SERVICE_PORT=8000
ENV SERVICE_MODULE=${SERVICE_MODULE}
ENV SERVICE_PORT=${SERVICE_PORT}

COPY --from=builder /usr/local /usr/local
COPY packages ./packages
COPY services ./services
COPY infra/docker/start-python-service.sh /start-python-service.sh

RUN chmod +x /start-python-service.sh

EXPOSE ${SERVICE_PORT}
ENTRYPOINT ["/start-python-service.sh"]

