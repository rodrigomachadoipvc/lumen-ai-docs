"""Optional observability. Both parts are off unless configured.

- LLM traces in Langfuse: one trace per chat turn, with retrieval, model calls (prompt, output,
  tokens, latency) and agent tool calls. Uses its own OpenTelemetry tracer provider.
- API traces and metrics with OpenTelemetry, exported over OTLP/HTTP (any collector or backend).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal, Protocol

import structlog
from fastapi import FastAPI

from lumen.config import Settings

log = structlog.get_logger(__name__)

ObservationType = Literal["span", "agent", "tool", "retriever", "generation", "chain"]


class Observation(Protocol):
    def update(self, **fields: Any) -> Any: ...


class _NoObservation:
    def update(self, **fields: Any) -> None:
        return None


class LLMTracer:
    """Facade over Langfuse. When disabled, every method is a cheap no-op."""

    def __init__(self, client: Any = None) -> None:
        self._client = client

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @contextmanager
    def observe(
        self,
        name: str,
        *,
        as_type: ObservationType = "span",
        input: Any = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Observation]:
        if self._client is None:
            yield _NoObservation()
            return
        extra: dict[str, Any] = {"model": model} if as_type == "generation" and model else {}
        with self._client.start_as_current_observation(
            name=name, as_type=as_type, input=input, metadata=metadata, **extra
        ) as observation:
            yield observation

    @contextmanager
    def trace(
        self, name: str, *, session_id: str, tags: list[str], input: Any
    ) -> Iterator[Observation]:
        """The root observation of a chat turn; the chat id groups turns into a session."""
        if self._client is None:
            yield _NoObservation()
            return
        from langfuse import propagate_attributes

        with (
            self._client.start_as_current_observation(
                name=name, as_type="agent" if "agent" in tags else "chain", input=input
            ) as root,
            propagate_attributes(session_id=session_id, tags=tags, trace_name=name),
        ):
            yield root

    def flush(self) -> None:
        if self._client is not None:
            self._client.flush()


def build_llm_tracer(settings: Settings) -> LLMTracer:
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return LLMTracer()
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider

    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
        environment=settings.environment,
        # A private provider keeps LLM traces separate from the API's OpenTelemetry traces.
        tracer_provider=TracerProvider(),
    )
    log.info("langfuse_enabled", base_url=settings.langfuse_base_url)
    return LLMTracer(client)


def usage_details(usage: dict[str, int]) -> dict[str, int] | None:
    if not usage:
        return None
    return {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)}


def setup_opentelemetry(app: FastAPI, settings: Settings) -> None:
    """Export request traces and HTTP metrics over OTLP when an endpoint is configured."""
    if not settings.otel_exporter_endpoint:
        return
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = settings.otel_exporter_endpoint.rstrip("/")
    resource = Resource.create(
        {"service.name": "lumen-api", "deployment.environment": settings.environment}
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"))
        ],
    )
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        excluded_urls="health",
    )
    log.info("opentelemetry_enabled", endpoint=endpoint)
