"""Cloud semantic_text requests without requiring a newer Python SDK."""
import re
from elasticsearch import ApiError

SOURCE_EXCLUDES = ["embedding", "embedding_model", "semantic_content", "_inference_fields"]


class CloudSemanticError(Exception):
    def __init__(self, status, error_type="request_failed"):
        self.status = status
        # Only expose the error category, never server messages, URLs or credentials.
        safe_type = re.sub(r"[^a-zA-Z0-9_]", "", str(error_type))[:80]
        super().__init__(f"Elastic semantic service returned HTTP {status} ({safe_type}).")


def raw_request(client, method, path, body=None, timeout=30):
    try:
        # Use the API client's request path so Authorization headers are retained.
        # Raw transport requests do not inherit client-level API-key headers.
        response = client.options(request_timeout=timeout).perform_request(method, path, body=body,
            headers={"content-type": "application/json", "accept": "application/json"})
    except ApiError as exc:
        error = exc.body.get("error", {}) if isinstance(exc.body, dict) else {}
        category = error.get("type", "request_failed") if isinstance(error, dict) else "request_failed"
        raise CloudSemanticError(exc.status_code, category) from None
    data = response.body
    if response.meta.status >= 400:
        error = data.get("error", {}) if isinstance(data, dict) else {}
        category = error.get("type", "request_failed") if isinstance(error, dict) else "request_failed"
        raise CloudSemanticError(response.meta.status, category)
    if not isinstance(data, dict):
        raise CloudSemanticError(response.meta.status, "invalid_response")
    return data


def semantic_query(q, filters):
    return {"bool": {"must": [{"match": {"semantic_content": {"query": q}}}],
                     "filter": filters}}


def hybrid_body(q, lexical_query, filters):
    return {"size": 12, "_source": {"excludes": SOURCE_EXCLUDES}, "retriever": {
        "rrf": {"retrievers": [
            {"standard": {"query": lexical_query}},
            {"standard": {"query": semantic_query(q, filters)}}],
            "rank_window_size": 28, "rank_constant": 60}}}
