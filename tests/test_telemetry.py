import logging

from app import telemetry


class Span:
    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


def test_search_telemetry_omits_attendee_text(monkeypatch, caplog):
    span = Span()
    monkeypatch.setattr(telemetry, "duration", None)
    monkeypatch.setattr(telemetry.trace, "get_current_span", lambda: span)
    with caplog.at_level(logging.INFO, logger="talk_search"):
        telemetry.record_search("private attendee request", "elasticsearch", 12, 3)
    assert "private attendee request" not in caplog.text
    assert "private attendee request" not in str(span.attributes)
    assert span.attributes["search.result_count"] == 3


def test_http_span_omits_query_parameters():
    span = Span()
    telemetry._sanitize_request(span, {
        "scheme": "https", "server": ("example.test", 443),
        "path": "/api/search", "query_string": b"q=private-request",
    })
    assert "private-request" not in str(span.attributes)
    assert span.attributes["http.target"] == "/api/search"
    assert span.attributes["url.query"] == ""
