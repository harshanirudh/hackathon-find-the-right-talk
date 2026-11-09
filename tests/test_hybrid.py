"""Exercise hybrid retrieval boundaries without Elasticsearch or Ollama."""
from datetime import date
from itertools import combinations
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.agenda import overlaps
from app.data import TALKS
from app.local_ai import LocalAIUnavailable
from app.main import app
from app.store import Store


def es_hits(*talks):
    return {"hits": {"hits": [{"_source": talk} for talk in talks]}}


@pytest.fixture
def store():
    instance = Store.__new__(Store)
    instance.client = Mock()
    instance.client.count.return_value = {"count": 28}
    instance.ai = Mock(embedding_model="embeddinggemma", generation_model="llama3.2:3b")
    instance.ai.query_embedding.return_value = tuple([0.1] * 768)
    return instance


def test_hybrid_retrieves_from_es_with_filters_on_both_paths_and_no_vectors(store):
    lexical = {**TALKS[0], "embedding": [0.1], "embedding_model": "embeddinggemma"}
    semantic = {**TALKS[4], "embedding": [0.2], "embedding_model": "embeddinggemma"}
    store.client.search.side_effect = [es_hits(lexical), es_hits(semantic)]
    result = store.hybrid_search("protect workloads", "Security", "beginner", True)
    assert result["mode"] == "hybrid"
    assert result["source"] == "elasticsearch"
    assert result["degraded_reason"] is None
    assert len(result["talks"]) == 2
    assert all("embedding" not in talk and "embedding_model" not in talk for talk in result["talks"])
    lexical_call, vector_call = [call.kwargs for call in store.client.search.call_args_list]
    required = [{"term": {"track": "Security"}}, {"term": {"level": "beginner"}},
                {"term": {"accessibility.captioned": True}}]
    assert lexical_call["query"]["bool"]["filter"] == required
    filters = vector_call["knn"]["filter"]["bool"]["filter"]
    assert all(condition in filters for condition in required)
    assert {"term": {"embedding_model": "embeddinggemma"}} in filters
    assert len(vector_call["knn"]["query_vector"]) == 768
    assert vector_call["knn"]["k"] <= 12


def test_missing_model_degrades_to_real_keyword_results_without_claiming_hybrid(store):
    store.client.search.return_value = es_hits(TALKS[0])
    store.ai.query_embedding.side_effect = LocalAIUnavailable("Model not downloaded")
    result = store.hybrid_search("kubernetes")
    assert result["source"] == "elasticsearch"
    assert result["mode"] == "keyword"
    assert result["requested_mode"] == "hybrid"
    assert "Model not downloaded" in result["degraded_reason"]
    store.client.search.assert_called_once()


def test_no_backfilled_vectors_does_not_call_ollama(store):
    store.client.search.return_value = es_hits(TALKS[0])
    store.client.count.return_value = {"count": 0}
    result = store.hybrid_search("kubernetes")
    assert result["mode"] == "keyword" and result["degraded_reason"]
    store.ai.query_embedding.assert_not_called()


def test_es_failure_is_labelled_fallback_and_does_not_call_ollama(store):
    store.client.search.side_effect = ConnectionError("cluster down")
    result = store.hybrid_search("kubernetes", captioned_only=True)
    assert result["source"] == "fallback"
    assert result["mode"] == "keyword"
    assert result["degraded_reason"]
    assert all(talk["accessibility"]["captioned"] for talk in result["talks"])
    store.ai.query_embedding.assert_not_called()


def test_partial_vector_backfill_is_not_misrepresented_as_complete_hybrid(store):
    store.client.search.return_value = es_hits(TALKS[0])
    store.client.count.side_effect = [{"count": 1}, {"count": 28}]
    result = store.hybrid_search("kubernetes")
    assert result["mode"] == "keyword"
    assert result["degraded_reason"]
    store.ai.query_embedding.assert_not_called()


@pytest.fixture
def api_store():
    with patch("app.main.store") as service:
        with TestClient(app) as client:
            yield client, service


def test_semantic_day_accepts_nonliteral_matches_but_never_overlaps(api_store):
    client, service = api_store
    candidates = [{**talk, "match_type": "semantic"} for talk in TALKS[:8]]
    service.hybrid_search.return_value = {
        "talks": candidates, "source": "elasticsearch", "mode": "hybrid",
        "requested_mode": "hybrid", "degraded_reason": None,
    }
    response = client.post("/api/build-my-day", json={
        "interests": "unexplained sluggishness", "mode": "hybrid", "captioned_only": True})
    assert response.status_code == 200
    result = response.json()
    assert result["talks"]
    assert result["mode"] == "hybrid" and result["source"] == "elasticsearch"
    for a, b in combinations(result["talks"], 2):
        assert not overlaps(a, b)
    service.hybrid_search.assert_called_once_with(
        q="unexplained sluggishness", track=None, level=None, captioned_only=True,
        day=date(2026, 11, 10))


@pytest.mark.parametrize("body", [{"talk_id": "talk-01", "query": ", ,"},
                                  {"talk_id": "", "query": "security"},
                                  {"talk_id": "talk-01", "query": "x" * 501}])
def test_invalid_explanation_request_never_runs_models(api_store, body):
    client, service = api_store
    assert client.post("/api/explain", json=body).status_code == 422
    service.ai.explain.assert_not_called()


def test_explanations_require_a_known_es_document(api_store):
    client, service = api_store
    service.get_talk.return_value = None
    assert client.post("/api/explain", json={"talk_id": "missing", "query": "security"}).status_code == 404
    service.ai.explain.assert_not_called()
    service.get_talk.side_effect = ConnectionError("cluster down")
    assert client.post("/api/explain", json={"talk_id": "talk-01", "query": "security"}).status_code == 503
    service.ai.explain.assert_not_called()


def test_unavailable_generation_returns_no_fabricated_explanation(api_store):
    client, service = api_store
    service.get_talk.return_value = TALKS[0]
    service.ai.generation_model = "llama3.2:3b"
    service.ai.explain.side_effect = LocalAIUnavailable("Model timed out")
    response = client.post("/api/explain", json={"talk_id": "talk-01", "query": "security"})
    assert response.status_code == 200
    result = response.json()
    assert result["available"] is False and result["source"] == "unavailable"
    assert result["explanation"] is None and result["evidence"] == []
    assert result["degraded_reason"] == "Model timed out"


def test_successful_explanation_uses_the_retrieved_session_and_labels_model(api_store):
    client, service = api_store
    service.get_talk.return_value = TALKS[0]
    service.ai.generation_model = "llama3.2:3b"
    evidence = [{"field": "title", "quote": TALKS[0]["title"]}]
    service.ai.explain.return_value = {"explanation": "An introduction to the topic.", "evidence": evidence}
    response = client.post("/api/explain", json={"talk_id": "talk-01", "query": "starting Kubernetes"})
    result = response.json()
    assert response.status_code == 200
    assert result["available"] is True and result["source"] == "ollama"
    assert result["model"] == "llama3.2:3b" and result["evidence"] == evidence
    service.ai.explain.assert_called_once_with(TALKS[0], "starting Kubernetes")


def test_unknown_search_mode_is_rejected(api_store):
    client, service = api_store
    assert client.get("/api/search?q=security&mode=fake-ai").status_code == 422
    service.search.assert_not_called()
    service.hybrid_search.assert_not_called()
