"""Local structured search logs; optional OTLP traces, metrics and logs."""
import logging
import os
from opentelemetry import metrics, trace

logger = logging.getLogger("talk_search")
duration = None
requests = None
fallbacks = None


def _sanitize_request(span, scope):
    """Keep attendee prompts and private query parameters out of HTTP spans."""
    path = scope.get("path", "/")
    server = scope.get("server") or ("localhost", 80)
    span.set_attribute("http.url", f"{scope.get('scheme', 'http')}://{server[0]}:{server[1]}{path}")
    span.set_attribute("http.target", path)
    span.set_attribute("url.query", "")


def configure(app):
    global duration, requests, fallbacks
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.metrics import MeterProvider
    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "find-the-right-talk")})
    tracing = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracing)
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
    enabled = bool(endpoint)
    readers = []
    if enabled:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        headers = {}
        if os.getenv("DASH0_AUTH_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["DASH0_AUTH_TOKEN"]
        if os.getenv("DASH0_DATASET"):
            headers["Dash0-Dataset"] = os.environ["DASH0_DATASET"]
        tracing.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint + "/v1/traces", headers=headers)))
        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint + "/v1/metrics", headers=headers)))
        log_provider = LoggerProvider(resource=resource)
        log_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint + "/v1/logs", headers=headers)))
        logger.addHandler(LoggingHandler(logger_provider=log_provider))
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=readers))
    meter = metrics.get_meter("talk_search")
    duration = meter.create_histogram("search.duration", unit="ms")
    requests = meter.create_counter("search.requests")
    fallbacks = meter.create_counter("search.fallbacks")
    FastAPIInstrumentor.instrument_app(app, server_request_hook=_sanitize_request)
    return enabled


def record_search(q, source, took_ms, count):
    import json
    logger.info(json.dumps({"event": "search", "source": source,
                            "latency_ms": round(took_ms, 2), "result_count": count}))
    if duration is not None:
        duration.record(took_ms, {"source": source})
        requests.add(1, {"source": source})
        fallbacks.add(int(source == "fallback"))
    span = trace.get_current_span()
    span.set_attribute("search.source", source)
    span.set_attribute("search.result_count", count)
