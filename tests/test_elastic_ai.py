"""Cloud semantic retrieval uses mocked transport; no keys or live requests."""
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.data import TALKS
from app.main import app
from app.store import Store, public_talk


@pytest.fixture
def cloud_store():
    store = Store.__new__(Store)
    store.client = Mock()
    store.ai = Mock()
    store.semantic_provider = "elastic"
    store.inference_id = ".jina-embeddings-v5-text-small"
    return store


def test_cloud_evidence_is_extractive_and_never_calls_a_generative_model():
    with patch("app.main.store") as store, TestClient(app) as client:
        store.semantic_provider = "elastic"
        store.get_talk.return_value = TALKS[0]
        response = client.post("/api/explain", json={"talk_id": TALKS[0]["id"],
                                                    "query": "understand workloads"})
        result = response.json()
        assert response.status_code == 200
        assert result["available"] is True and result["source"] == "elasticsearch"
        assert result["model"] is None
        assert result["evidence"]
        for evidence in result["evidence"]:
            assert evidence["quote"] in TALKS[0][evidence["field"]]
        store.ai.explain.assert_not_called()


def test_cloud_evidence_still_requires_a_verified_indexed_session():
    with patch("app.main.store") as store, TestClient(app) as client:
        store.semantic_provider = "elastic"
        store.get_talk.return_value = None
        assert client.post("/api/explain", json={"talk_id": "unknown", "query": "security"}).status_code == 404
        store.ai.explain.assert_not_called()


def test_semantic_fields_never_leak_in_public_talks():
    talk = {**TALKS[0], "embedding": [0.1], "embedding_model": "local-model",
            "semantic_content": {"text": "abstract", "inference": {"embeddings": [1, 2]}}}
    public = public_talk(talk)
    assert public == TALKS[0]


def test_native_hybrid_uses_rrf_with_identical_filters_and_hidden_semantic_fields(cloud_store):
    cloud_store.client.search.return_value = {"hits": {"hits": []}}
    cloud_store.client.count.return_value = {"count": 28}
    source = {**TALKS[4], "semantic_content": "internal model payload", "_inference_fields": {"secret": [1]}}
    with patch("app.store.raw_request", return_value={"hits": {"hits": [
        {"_source": source, "_score": 0.1}]}}) as request:
        result = cloud_store.hybrid_search("protect workloads", "Security", "beginner", True)
    assert result["mode"] == "hybrid" and result["source"] == "elasticsearch"
    assert result["semantic_provider"] == "elastic" and result["fusion"] == "elasticsearch_rrf"
    assert result["talks"][0]["id"] == TALKS[4]["id"]
    assert "semantic_content" not in result["talks"][0]
    assert "_inference_fields" not in result["talks"][0]
    client, method, path, body = request.call_args.args
    assert client is cloud_store.client and method == "POST" and path == "/talks/_search"
    lexical, semantic = body["retriever"]["rrf"]["retrievers"]
    required = [{"term": {"track": "Security"}}, {"term": {"level": "beginner"}},
                {"term": {"accessibility.captioned": True}}]
    assert lexical["standard"]["query"]["bool"]["filter"] == required
    assert semantic["standard"]["query"]["bool"]["filter"] == required
    assert semantic["standard"]["query"]["bool"]["must"] == [
        {"match": {"semantic_content": {"query": "protect workloads"}}}]
    assert set(body["_source"]["excludes"]) >= {"embedding", "semantic_content", "_inference_fields"}
    cloud_store.ai.query_embedding.assert_not_called()


def test_incomplete_cloud_backfill_explicitly_degrades_to_keyword(cloud_store):
    cloud_store.client.search.return_value = {"hits": {"hits": [{"_source": TALKS[0]}]}}
    cloud_store.client.count.side_effect = [{"count": 3}, {"count": 28}]
    with patch("app.store.raw_request") as request:
        result = cloud_store.hybrid_search("kubernetes")
    assert result["mode"] == "keyword" and result["requested_mode"] == "hybrid"
    assert result["source"] == "elasticsearch" and result["degraded_reason"]
    assert result["talks"] == [TALKS[0]]
    request.assert_not_called()


def test_cloud_semantic_failure_does_not_claim_hybrid_or_leak_error_messages(cloud_store):
    from app.elastic_ai import CloudSemanticError
    cloud_store.client.search.return_value = {"hits": {"hits": [{"_source": TALKS[0]}]}}
    cloud_store.client.count.return_value = {"count": 28}
    with patch("app.store.raw_request", side_effect=CloudSemanticError(503, "inference_unavailable")):
        result = cloud_store.hybrid_search("kubernetes")
    assert result["source"] == "elasticsearch" and result["mode"] == "keyword"
    assert result["degraded_reason"] and result["talks"] == [TALKS[0]]


def test_unlicensed_native_rrf_only_uses_app_fusion_after_real_semantic_success(cloud_store):
    from app.elastic_ai import CloudSemanticError
    cloud_store.client.search.return_value = {"hits": {"hits": [{"_source": TALKS[0]}]}}
    cloud_store.client.count.return_value = {"count": 28}
    with patch("app.store.raw_request", side_effect=[CloudSemanticError(403, "license_exception"),
               {"hits": {"hits": [{"_source": TALKS[4]}]}}]) as request:
        result = cloud_store.hybrid_search("secure workloads", captioned_only=True)
    assert result["mode"] == "hybrid" and result["fusion"] == "application_rrf"
    assert len(result["talks"]) == 2
    assert request.call_count == 2
    assert request.call_args.args[3]["query"]["bool"]["filter"] == [
        {"term": {"accessibility.captioned": True}}]


def test_rrf_and_semantic_failure_degrade_instead_of_fabricating_semantic_hits(cloud_store):
    from app.elastic_ai import CloudSemanticError
    cloud_store.client.search.return_value = {"hits": {"hits": []}}
    cloud_store.client.count.return_value = {"count": 28}
    with patch("app.store.raw_request", side_effect=CloudSemanticError(403, "not_allowed")):
        result = cloud_store.hybrid_search("protect workloads")
    assert result["mode"] == "keyword" and result["degraded_reason"]
    assert result["talks"] == []


def test_cloud_backfill_adds_mapping_and_updates_without_deleting_catalogue(cloud_store):
    cloud_store.client.search.return_value = {"hits": {"hits": [{"_source": TALKS[0]}, {"_source": TALKS[1]}]}}
    with patch("app.store.raw_request", return_value={}) as request:
        assert cloud_store.embed_catalogue() == 2
    calls = request.call_args_list
    assert calls[0].args[1:3] == ("PUT", "/talks/_mapping")
    mapping = calls[0].args[3]["properties"]["semantic_content"]
    assert mapping == {"type": "semantic_text", "inference_id": cloud_store.inference_id}
    assert all(call.args[1] == "POST" for call in calls[1:])
    assert all("/_update/" in call.args[2] for call in calls[1:])
    assert all(set(call.args[3]["doc"]) == {"semantic_content"} for call in calls[1:])
    cloud_store.ai.embed_texts.assert_not_called()
    cloud_store.client.indices.delete.assert_not_called()


def test_cloud_transport_preserves_timeout_and_sanitizes_server_errors():
    from app.elastic_ai import CloudSemanticError, raw_request
    client = Mock()
    client.options.return_value.perform_request.return_value = Mock(
        body={"error": {"type": "inference_error", "reason": "sensitive endpoint and credential text"}},
        meta=Mock(status=503))
    with pytest.raises(CloudSemanticError) as error:
        raw_request(client, "POST", "/talks/_search", {"query": {}}, timeout=17)
    assert "sensitive" not in str(error.value) and "credential" not in str(error.value)
    client.options.assert_called_once_with(request_timeout=17)
    client.transport.perform_request.assert_not_called()
    kwargs = client.options.return_value.perform_request.call_args.kwargs
    assert kwargs["headers"]["content-type"] == "application/json"



def response_meta(status):
    from elastic_transport import ApiResponseMeta, HttpHeaders, NodeConfig
    return ApiResponseMeta(status=status, http_version="1.1", duration=0.01,
                           headers=HttpHeaders({"x-elastic-product": "Elasticsearch"}),
                           node=NodeConfig("http", "unit-test.invalid", 9200))


def test_custom_cloud_request_inherits_api_client_authentication():
    # Exercise the actual SDK options()/perform_request() boundary with a
    # synthetic API key. Only its transport is mocked; no network is used.
    from elastic_transport import TransportApiResponse
    from elasticsearch import Elasticsearch
    from app.elastic_ai import raw_request
    client = Elasticsearch("http://unit-test.invalid:9200", api_key="synthetic-test-key")
    with patch.object(client.transport, "perform_request", return_value=TransportApiResponse(
            response_meta(200), {"hits": {"hits": []}})) as transport:
        result = raw_request(client, "POST", "/talks/_search", {"size": 1}, timeout=19)
    assert result == {"hits": {"hits": []}}
    kwargs = transport.call_args.kwargs
    assert kwargs["headers"]["authorization"] == "ApiKey synthetic-test-key"
    assert "json" in kwargs["headers"]["content-type"]
    assert kwargs["request_timeout"] == 19
    client.close()


def test_sdk_api_error_is_sanitized_without_exposing_server_reason():
    from elasticsearch import ApiError
    from app.elastic_ai import CloudSemanticError, raw_request
    client = Mock()
    client.options.return_value.perform_request.side_effect = ApiError(
        "upstream private diagnostic", response_meta(401), {
            "error": {"type": "security_exception", "reason": "private-key-and-endpoint-detail"}})
    with pytest.raises(CloudSemanticError) as error:
        raw_request(client, "POST", "/talks/_search", {"query": {}})
    assert error.value.status == 401
    assert "security_exception" in str(error.value)
    assert "private" not in str(error.value) and "endpoint" not in str(error.value)
    assert error.value.__cause__ is None
