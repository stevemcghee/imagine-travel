import os
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.google_genai import GoogleGenAIInstrumentor

logger = logging.getLogger(__name__)

def init_telemetry(app, service_name="travel-agent-adk"):
    """
    Initializes OpenTelemetry for the application.
    
    Args:
        app: The FastAPI application instance.
        service_name: The name of the service to appear in traces.
    """
    # 1. Check if Telemetry is enabled via env var (default to True)
    if os.getenv("ENABLE_TELEMETRY", "true").lower() != "true":
        logger.info("Telemetry disabled via ENABLE_TELEMETRY env var.")
        return

    logger.info(f"Initializing OpenTelemetry for service: {service_name}")

    # 2. Configure Resource (Metadata)
    resource = Resource.create(attributes={
        "service.name": service_name,
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("ENV", "development")
    })

    # 3. Set up Tracer Provider
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # 4. Configure Exporter
    # Default to OTLP (Collector) unless USE_GCP_EXPORTER is set to true
    if os.getenv("USE_GCP_EXPORTER", "false").lower() == "true":
        try:
            from opentelemetry.exporter.google_cloud import GoogleCloudSpanExporter
            gcp_exporter = GoogleCloudSpanExporter()
            span_processor = BatchSpanProcessor(gcp_exporter)
            provider.add_span_processor(span_processor)
            logger.info("Google Cloud Trace Exporter configured.")
        except Exception as e:
            logger.error(f"Failed to configure Google Cloud Trace exporter: {e}")
    else:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            span_processor = BatchSpanProcessor(otlp_exporter)
            provider.add_span_processor(span_processor)
            logger.info(f"OTLP Exporter configured to {otlp_endpoint}")
        except Exception as e:
            logger.error(f"Failed to configure OTLP exporter: {e}")

    # Optional: Console Exporter for debugging (enable with env var)
    if os.getenv("OTEL_CONSOLE_EXPORTER", "false").lower() == "true":
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))
        logger.info("Console Exporter enabled.")

    # 5. Instrument Libraries
    
    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    
    # Instrument Requests (used by many libraries internally)
    RequestsInstrumentor().instrument(tracer_provider=provider)
    
    # Instrument Google GenAI (for LLM calls)
    # This captures prompt/response content if configured
    try:
        GoogleGenAIInstrumentor().instrument(tracer_provider=provider)
        logger.info("Google GenAI Instrumentation enabled.")
    except Exception as e:
        logger.warning(f"Could not instrument Google GenAI: {e}")

    logger.info("OpenTelemetry initialization complete.")
