from __future__ import annotations

import logging
import sys
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import make_asgi_app
from prometheus_client import Counter, Gauge, Histogram
from pythonjsonlogger.json import JsonFormatter

from .config import AetherSettings


REQUEST_COUNTER = Counter(
    "aether_service_requests_total",
    "Total requests served by an AETHER service",
    ["service", "endpoint"],
)
LATENCY_HISTOGRAM = Histogram(
    "aether_service_request_latency_seconds",
    "Request latency distribution",
    ["service", "endpoint"],
)
ACTIVE_STREAMS_GAUGE = Gauge(
    "aether_streams_active_total",
    "Active streams by modality",
    ["modality"],
)


def configure_logging(service_name: str, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(service_name)
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def configure_tracing(settings: AetherSettings) -> None:
    resource = Resource.create({"service.name": settings.service_name, "deployment.environment": settings.env})
    tracer_provider = TracerProvider(resource=resource)
    span_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)


def instrument_fastapi(app: Any, settings: AetherSettings) -> None:
    try:
        configure_tracing(settings)
    except Exception:
        # Local development should not fail if the exporter is unavailable.
        pass
    FastAPIInstrumentor.instrument_app(app)


def mount_metrics(app: Any) -> None:
    app.mount("/metrics", make_asgi_app())
