import logging
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers
from .data import TALKS
from .search import build_query, fallback_search
from .local_ai import LocalAI, LocalAIUnavailable, EMBEDDING_DIMS
from .hybrid import reciprocal_rank_fusion
from .elastic_ai import raw_request, semantic_query, hybrid_body, CloudSemanticError, SOURCE_EXCLUDES
from opentelemetry import trace

tracer = trace.get_tracer("talk_search.store")

load_dotenv()
logger = logging.getLogger(__name__)
INDEX = "talks"
_SCHEDULE_PATH = Path(__file__).resolve().parents[1] / "data" / "kubecon-na-2026.json"
KUBECON_TALKS = json.loads(_SCHEDULE_PATH.read_text())["talks"] if _SCHEDULE_PATH.exists() else []
_PLACES_PATH = Path(__file__).resolve().parents[1] / "data" / "places.json"
PLACES_DATA = json.loads(_PLACES_PATH.read_text()) if _PLACES_PATH.exists() else {"places": []}
MAPPING = {"properties": {
    "embedding": {"type": "dense_vector", "dims": EMBEDDING_DIMS, "index": True, "similarity": "cosine"},
    "embedding_model": {"type": "keyword"},
    "id": {"type": "keyword"}, "title": {"type": "text"},
    "speaker": {"type": "text"}, "description": {"type": "text"},
    "tags": {"type": "text"}, "track": {"type": "keyword"},
    "level": {"type": "keyword"}, "start": {"type": "date"}, "end": {"type": "date"},
    "room": {"type": "keyword"}, "accessibility": {"properties": {
        "captioned": {"type": "boolean"}, "step_free": {"type": "boolean"},
        "plain_language_summary": {"type": "boolean"}}}}}


class Store:
    def __init__(self):
        self.semantic_provider = os.getenv("ELASTICSEARCH_SEMANTIC_PROVIDER", "ollama")
        self.inference_id = os.getenv("ELASTICSEARCH_INFERENCE_ID", ".jina-embeddings-v5-text-small")
        options = {"request_timeout": 15 if self.semantic_provider == "elastic" else 2, "max_retries": 0, "retry_on_timeout": False}
        if os.getenv("ELASTICSEARCH_API_KEY"):
            options["api_key"] = os.environ["ELASTICSEARCH_API_KEY"]
        self.ai = LocalAI()
        self.client = Elasticsearch(os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"), **options)

    def search(self, q="", track=None, level=None, captioned_only=False, day=None):
        talks, source, _, _ = self.search_page(q, track, level, captioned_only, size=1000, day=day)
        return talks, source

    def search_page(self, q="", track=None, level=None, captioned_only=False, offset=0, size=24, day=None):
        try:
            response = self.client.search(index=INDEX, query=build_query(q, track, level, captioned_only, day),
                                          size=size, from_=offset, track_total_hits=True,
                                          source_excludes=SOURCE_EXCLUDES,
                                          aggs={"track": {"terms": {"field": "track", "size": 30}},
                                                "level": {"terms": {"field": "level", "size": 10}},
                                                "captioned": {"terms": {"field": "accessibility.captioned", "size": 2}}},
                                          highlight={"fields": {"title": {}, "description": {}, "tags": {}},
                                                     "pre_tags": ["<mark>"], "post_tags": ["</mark>"]})
            hits = response["hits"]["hits"]
            total_info = response["hits"].get("total", len(hits))
            total = total_info["value"] if isinstance(total_info, dict) else total_info
            talks = []
            for hit in hits:
                talk = public_talk(hit["_source"])
                if hit.get("highlight"):
                    talk["highlights"] = hit["highlight"]
                talks.append(talk)
            aggregations = response.get("aggregations", {})
            facets = {name: [{"key": bucket["key"], "doc_count": bucket["doc_count"]}
                             for bucket in aggregations.get(name, {}).get("buckets", [])]
                      for name in ("track", "level", "captioned")}
            return talks, "elasticsearch", total, facets
        except Exception as exc:
            # Log only exception type, avoiding endpoint/key leakage from SDK messages.
            logger.warning("elasticsearch_unavailable error_type=%s", type(exc).__name__)
            talks = fallback_search(TALKS, q, track, level, captioned_only)
            if day:
                talks = [talk for talk in talks if talk["start"][:10] == str(day)]
            selected = talks[offset:offset + size]
            facets = {name: [] for name in ("track", "level", "captioned")}
            for field, name in (("track", "track"), ("level", "level")):
                counts = {}
                for talk in talks:
                    counts[talk[field]] = counts.get(talk[field], 0) + 1
                facets[name] = [{"key": key, "doc_count": value} for key, value in sorted(counts.items())]
            counts = {value: sum(t["accessibility"].get("captioned") is value for t in talks) for value in (False, True)}
            facets["captioned"] = [{"key": key, "doc_count": value} for key, value in counts.items() if value]
            return selected, "fallback", len(talks), facets

    def health(self):
        try:
            self.client.info()
            count = self.client.count(index=INDEX)["count"] if self.client.indices.exists(index=INDEX) else 0
            return {"elasticsearch": "up", "talks_indexed": count}
        except Exception:
            return {"elasticsearch": "down", "talks_indexed": 0}

    def seed(self):
        if not self.client.indices.exists(index=INDEX):
            mapping = MAPPING
            if getattr(self, "semantic_provider", "ollama") == "elastic":
                mapping = {"properties": {key: value for key, value in MAPPING["properties"].items()
                                          if key not in ("embedding", "embedding_model", "semantic_content", "_inference_fields")}}
            self.client.indices.create(index=INDEX, mappings=mapping)
        # Partial updates preserve semantic_text and other fields created by
        # later backfills when the base catalogue is reseeded.
        helpers.bulk(self.client, ({"_op_type": "update", "_index": INDEX, "_id": t["id"],
                      "doc": t, "doc_as_upsert": True} for t in [*TALKS, *KUBECON_TALKS]))
        self.client.indices.refresh(index=INDEX)
        return self.client.count(index=INDEX)["count"]

    def seed_places(self):
        mapping = {"properties": {"id": {"type": "keyword"}, "name": {"type": "text"},
                    "category": {"type": "keyword"}, "address": {"type": "text"},
                    "website": {"type": "keyword"}, "lat": {"type": "float"}, "lon": {"type": "float"},
                    "location": {"type": "geo_point"}}}
        if not self.client.indices.exists(index="places"):
            self.client.indices.create(index="places", mappings=mapping)
        places = PLACES_DATA["places"]
        helpers.bulk(self.client, ({"_index": "places", "_id": place["id"],
                      "_source": {**place, "location": {"lat": place["lat"], "lon": place["lon"]}}}
                     for place in places))
        self.client.indices.refresh(index="places")
        return self.client.count(index="places")["count"]

    def nearby_places(self, category=None, radius_m=1000, size=50):
        filters = [{"geo_distance": {"distance": f"{radius_m}m",
                    "location": {"lat": PLACES_DATA["venue"]["lat"], "lon": PLACES_DATA["venue"]["lon"]}}}]
        if category:
            categories = ["hotel"] if category == "stay" else ["restaurant", "bar"] if category == "eat" else ["cafe"] if category == "coffee" else [category]
            filters.append({"terms": {"category": categories}})
        response = self.client.search(index="places", query={"bool": {"filter": filters}}, size=size,
            sort=[{"_geo_distance": {"location": {"lat": PLACES_DATA["venue"]["lat"],
                    "lon": PLACES_DATA["venue"]["lon"]}, "order": "asc", "unit": "m", "distance_type": "arc"}}])
        rows = []
        for hit in response["hits"]["hits"]:
            place = {key: value for key, value in hit["_source"].items() if key != "location"}
            distance = max(0, round(hit["sort"][0]))
            place["distance_m"] = distance
            place["walking_minutes"] = (distance + 79) // 80
            rows.append(place)
        return rows


    def get_talk(self, talk_id):
        """Explanation evidence must come from Elasticsearch, never sample fallback."""
        from elasticsearch import NotFoundError
        try:
            return public_talk(self.client.get(index=INDEX, id=talk_id)["_source"])
        except NotFoundError:
            return None

    def hybrid_search(self, q, track=None, level=None, captioned_only=False, day=None):
        keyword_talks, source, total, facets = self.search_page(q, track, level, captioned_only, size=24, day=day)
        result = {"talks": keyword_talks, "source": source, "mode": "keyword",
                  "requested_mode": "hybrid", "degraded_reason": None, "total": total, "facets": facets}
        if not q.strip():
            result["degraded_reason"] = "Enter a query to use hybrid search. Showing all matching talks."
            return result
        if source != "elasticsearch":
            result["degraded_reason"] = "Elasticsearch unavailable; showing labelled keyword fallback."
            return result
        try:
            filters = build_query(q, track, level, captioned_only, day)["bool"]["filter"]
            if getattr(self, "semantic_provider", "ollama") == "elastic":
                return self._elastic_hybrid_search(q, keyword_talks, filters, track, level, captioned_only, day) | {"facets": facets}
            vector_filters = filters + [{"term": {"embedding_model": self.ai.embedding_model}},
                                       {"exists": {"field": "embedding"}}]
            vector_count = self.client.count(index=INDEX, query={"bool": {"filter": vector_filters}})["count"]
            if not vector_count:
                raise LocalAIUnavailable("No indexed embeddings for these filters. Run python -m app.embed first.")
            total_count = self.client.count(index=INDEX, query={"bool": {"filter": filters}})["count"]
            if vector_count != total_count:
                raise LocalAIUnavailable("Some sessions lack current embeddings. Run python -m app.embed to finish indexing.")
            vector = list(self.ai.query_embedding(q))
            with tracer.start_as_current_span("search.vector"):
                response = self.client.search(index=INDEX, knn={
                    "field": "embedding", "query_vector": vector, "k": 8,
                    "num_candidates": 100, "similarity": 0.25,
                    "filter": {"bool": {"filter": vector_filters}}},
                    source_excludes=SOURCE_EXCLUDES, size=8)
            semantic_talks = [public_talk(hit["_source"]) for hit in response["hits"]["hits"]]
            with tracer.start_as_current_span("search.fusion"):
                fused = reciprocal_rank_fusion(keyword_talks, semantic_talks)
            return {"talks": fused, "source": "elasticsearch", "mode": "hybrid",
                    "requested_mode": "hybrid", "degraded_reason": None,
                    "embedding_model": self.ai.embedding_model, "facets": facets}
        except (LocalAIUnavailable, CloudSemanticError) as exc:
            result["degraded_reason"] = str(exc)
        except Exception as exc:
            logger.warning("hybrid_unavailable error_type=%s", type(exc).__name__)
            result["degraded_reason"] = "Vector retrieval unavailable; showing Elasticsearch keyword results."
        return result

    def embed_catalogue(self):
        """Add a vector mapping and update documents without replacing/deleting talks."""
        if getattr(self, "semantic_provider", "ollama") == "elastic":
            return self._embed_elastic_catalogue()
        from .local_ai import document_text
        self.client.indices.put_mapping(index=INDEX, properties={key: MAPPING["properties"][key]
                                       for key in ("embedding", "embedding_model")})
        response = self.client.search(index=INDEX, query={"match_all": {}}, size=1000,
                                      source_excludes=SOURCE_EXCLUDES)
        talks = [hit["_source"] for hit in response["hits"]["hits"]]
        for offset in range(0, len(talks), 4):
            batch = talks[offset:offset + 4]
            vectors = self.ai.embed_texts([document_text(talk) for talk in batch])
            helpers.bulk(self.client, ({"_op_type": "update", "_index": INDEX,
                         "_id": talk["id"], "doc": {"embedding": vector,
                         "embedding_model": self.ai.embedding_model}}
                         for talk, vector in zip(batch, vectors)))
        self.client.indices.refresh(index=INDEX)
        return len(talks)


    def _elastic_hybrid_search(self, q, keyword_talks, filters, track=None, level=None, captioned_only=False, day=None):
        complete_filters = filters + [{"exists": {"field": "semantic_content"}}]
        embedded = self.client.count(index=INDEX, query={"bool": {"filter": complete_filters}})["count"]
        total = self.client.count(index=INDEX, query={"bool": {"filter": filters}})["count"]
        if not embedded or embedded != total:
            raise LocalAIUnavailable("Cloud semantic content is not fully indexed. Run python -m app.embed.")
        fusion = "elasticsearch_rrf"
        with tracer.start_as_current_span("search.elastic_semantic") as span:
            span.set_attribute("ai.model", self.inference_id)
            body = hybrid_body(q, build_query(q, track, level, captioned_only, day), filters)
            try:
                response = raw_request(self.client, "POST", f"/{INDEX}/_search", body)
                talks = [{**public_talk(hit["_source"]), "match_type": "hybrid",
                          "retrieval_score": hit.get("_score")} for hit in response["hits"]["hits"]]
            except CloudSemanticError as exc:
                # Some hosted licenses lack native RRF; both searches still run in ES.
                if exc.status not in (400, 403):
                    raise
                semantic = raw_request(self.client, "POST", f"/{INDEX}/_search", {
                    "query": semantic_query(q, filters), "size": 8,
                    "_source": {"excludes": SOURCE_EXCLUDES}})
                talks = reciprocal_rank_fusion(keyword_talks,
                    [public_talk(hit["_source"]) for hit in semantic["hits"]["hits"]])
                fusion = "application_rrf"
        return {"talks": talks, "source": "elasticsearch", "mode": "hybrid",
                "requested_mode": "hybrid", "degraded_reason": None,
                "embedding_model": self.inference_id, "semantic_provider": "elastic", "fusion": fusion}

    def _embed_elastic_catalogue(self):
        from .local_ai import document_text
        raw_request(self.client, "PUT", f"/{INDEX}/_mapping", {"properties": {
            "semantic_content": {"type": "semantic_text", "inference_id": self.inference_id}}})
        response = self.client.search(index=INDEX, query={"match_all": {}}, size=1000,
                                      source_excludes=SOURCE_EXCLUDES)
        talks = [public_talk(hit["_source"]) for hit in response["hits"]["hits"]]
        from urllib.parse import quote
        for talk in talks:
            raw_request(self.client, "POST", f"/{INDEX}/_update/{quote(talk['id'], safe='')}",
                        {"doc": {"semantic_content": document_text(talk)}}, timeout=120)
        self.client.indices.refresh(index=INDEX)
        return len(talks)


def public_talk(talk):
    return {key: value for key, value in talk.items() if key not in ("embedding", "embedding_model", "semantic_content", "_inference_fields")}
