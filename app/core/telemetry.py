"""
OpenTelemetry instrumentation module for SigNoz integration.

Provides tracing, metrics, and logging with OTLP export to SigNoz.
"""
from typing import Optional
from functools import lru_cache

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

# Optional instrumentation packages
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    HAS_FASTAPI_INSTRUMENTOR = True
except ImportError:
    HAS_FASTAPI_INSTRUMENTOR = False

try:
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    HAS_LOGGING_INSTRUMENTOR = True
except ImportError:
    HAS_LOGGING_INSTRUMENTOR = False

from app.config import settings
from helpers.utils import get_logger

logger = get_logger(__name__)

_tracer_provider: Optional[TracerProvider] = None
_meter_provider: Optional[MeterProvider] = None
_initialized: bool = False


def init_telemetry(app) -> None:
    """
    Initialize OpenTelemetry with OTLP exporters for SigNoz.

    Args:
        app: FastAPI application instance
    """
    global _tracer_provider, _meter_provider, _initialized

    if _initialized:
        logger.warning("Telemetry already initialized, skipping")
        return

    if not settings.otel_enabled:
        logger.info("OpenTelemetry is disabled (OTEL_ENABLED=false)")
        _initialized = True
        return

    try:
        # Create resource with service name
        resource = Resource.create({
            SERVICE_NAME: settings.otel_service_name,
            "service.version": "1.0.0",
            "deployment.environment": settings.environment,
        })

        # Initialize TracerProvider
        _tracer_provider = TracerProvider(resource=resource)
        trace_endpoint = f"{settings.otel_exporter_otlp_endpoint}/v1/traces"
        span_exporter = OTLPSpanExporter(endpoint=trace_endpoint)
        _tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(_tracer_provider)

        # Initialize MeterProvider
        metrics_endpoint = f"{settings.otel_exporter_otlp_endpoint}/v1/metrics"
        metric_exporter = OTLPMetricExporter(endpoint=metrics_endpoint)
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=60000  # Export every 60 seconds
        )
        _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(_meter_provider)

        # Instrument FastAPI for automatic HTTP tracing (if available)
        if HAS_FASTAPI_INSTRUMENTOR:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI instrumentation enabled")
        else:
            logger.warning("FastAPI instrumentation not available - install opentelemetry-instrumentation-fastapi")

        # Instrument logging to include trace context (if available)
        if HAS_LOGGING_INSTRUMENTOR:
            LoggingInstrumentor().instrument(set_logging_format=True)
            logger.info("Logging instrumentation enabled")
        else:
            logger.warning("Logging instrumentation not available - install opentelemetry-instrumentation-logging")

        _initialized = True
        logger.info(f"OpenTelemetry initialized: service={settings.otel_service_name}, endpoint={settings.otel_exporter_otlp_endpoint}")

    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry: {e}")
        _initialized = True  # Prevent retry loops


def shutdown_telemetry() -> None:
    """Shutdown telemetry providers gracefully."""
    global _tracer_provider, _meter_provider

    if _tracer_provider:
        try:
            _tracer_provider.shutdown()
            logger.info("TracerProvider shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down TracerProvider: {e}")

    if _meter_provider:
        try:
            _meter_provider.shutdown()
            logger.info("MeterProvider shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down MeterProvider: {e}")


@lru_cache(maxsize=32)
def get_tracer(name: str) -> trace.Tracer:
    """
    Get a tracer instance for the given name.

    Args:
        name: Module or component name (typically __name__)

    Returns:
        Tracer instance (no-op if OTel disabled)
    """
    return trace.get_tracer(name)


@lru_cache(maxsize=32)
def get_meter(name: str) -> metrics.Meter:
    """
    Get a meter instance for the given name.

    Args:
        name: Module or component name (typically __name__)

    Returns:
        Meter instance (no-op if OTel disabled)
    """
    return metrics.get_meter(name)
