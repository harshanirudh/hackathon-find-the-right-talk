"""Bounded request-stage spans using the already configured OTel provider."""
from contextlib import contextmanager
from time import perf_counter
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


@contextmanager
def stage(name, **attributes):
    started = perf_counter()
    with trace.get_tracer('talk_search.stages').start_as_current_span(
            name, record_exception=False, set_status_on_exception=False) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        span.set_attribute('stage.outcome', 'ok')
        try:
            yield span
        except Exception as exc:
            span.set_attribute('stage.outcome', 'error')
            span.set_attribute('error.type', type(exc).__name__)
            span.set_status(Status(StatusCode.ERROR))
            raise
        finally:
            span.set_attribute('stage.duration_ms', round((perf_counter() - started) * 1000, 3))
