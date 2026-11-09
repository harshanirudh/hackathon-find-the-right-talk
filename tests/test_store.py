"""Verify primary search and labelled failover without a live cluster."""
import importlib.util
import unittest
from unittest.mock import Mock

DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("elasticsearch", "dotenv"))
if DEPENDENCIES:
    from app.store import Store


@unittest.skipUnless(DEPENDENCIES, "Install requirements.txt for Elasticsearch adapter tests")
class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store.__new__(Store)
        self.store.client = Mock()

    def test_elasticsearch_is_queried_and_success_is_labelled(self):
        item = {"id": "from-es", "title": "Real indexed result"}
        self.store.client.search.return_value = {"hits": {"hits": [{"_source": item}]}}
        results, source = self.store.search("security", captioned_only=True)
        self.assertEqual(source, "elasticsearch")
        self.assertEqual(results, [item])
        self.store.client.search.assert_called_once()
        self.assertEqual(self.store.client.search.call_args.kwargs["index"], "talks")

    def test_cluster_failure_returns_explicit_filtered_fallback(self):
        self.store.client.search.side_effect = ConnectionError("cluster unavailable")
        results, source = self.store.search("kubernetes", captioned_only=True)
        self.assertEqual(source, "fallback")
        self.assertTrue(results)
        self.assertTrue(all(t["accessibility"]["captioned"] for t in results))
        self.store.client.search.assert_called_once()

    def test_empty_success_is_not_replaced_by_fallback(self):
        self.store.client.search.return_value = {"hits": {"hits": []}}
        self.assertEqual(self.store.search("no results"), ([], "elasticsearch"))

    def test_search_page_returns_live_facets_and_elasticsearch_highlights(self):
        item = {"id": "facet-talk", "title": "Observability at scale"}
        self.store.client.search.return_value = {"hits": {"total": {"value": 3}, "hits": [
            {"_source": item, "highlight": {"title": ["<mark>Observability</mark> at scale"]}}]},
            "aggregations": {"track": {"buckets": [{"key": "Observability", "doc_count": 2}]},
                             "level": {"buckets": []}, "captioned": {"buckets": []}}}
        talks, source, total, facets = self.store.search_page("observability")
        self.assertEqual((source, total), ("elasticsearch", 3))
        self.assertEqual(talks[0]["highlights"]["title"], ["<mark>Observability</mark> at scale"])
        self.assertEqual(facets["track"], [{"key": "Observability", "doc_count": 2}])
        self.assertIn("highlight", self.store.client.search.call_args.kwargs)
        self.assertIn("aggs", self.store.client.search.call_args.kwargs)

    def test_nearby_places_use_geo_filter_sort_and_compute_walk_time(self):
        places = [
            {"_source": {"id": "near", "name": "Near Cafe", "category": "cafe", "lat": 40.76, "lon": -111.88}, "sort": [121.0]},
            {"_source": {"id": "far", "name": "Far Cafe", "category": "cafe", "lat": 40.76, "lon": -111.88}, "sort": [402.0]},
        ]
        self.store.client.search.return_value = {"hits": {"hits": places}}
        results = self.store.nearby_places("coffee", 1000)
        self.assertEqual([p["distance_m"] for p in results], [121, 402])
        self.assertEqual([p["walking_minutes"] for p in results], [2, 6])
        kwargs = self.store.client.search.call_args.kwargs
        self.assertEqual(kwargs["index"], "places")
        self.assertEqual(kwargs["sort"][0]["_geo_distance"]["order"], "asc")
        self.assertEqual(kwargs["query"]["bool"]["filter"][1]["terms"]["category"], ["cafe"])

    def test_seed_uses_partial_updates_to_preserve_semantic_content(self):
        from unittest.mock import patch
        self.store.client.indices.exists.return_value = True
        self.store.client.count.return_value = {"count": 506}
        captured = []
        with patch("app.store.helpers.bulk", side_effect=lambda client, actions: captured.extend(actions)):
            self.store.seed()
        self.assertTrue(captured)
        self.assertTrue(all(action["_op_type"] == "update" and action["doc_as_upsert"] for action in captured))
        self.assertNotIn("_source", captured[0])

    def test_health_reports_actual_indexed_count(self):
        self.store.client.indices.exists.return_value = True
        self.store.client.count.return_value = {"count": 17}
        self.assertEqual(self.store.health(), {"elasticsearch": "up", "talks_indexed": 17})

    def test_failed_health_never_claims_seed_is_indexed(self):
        self.store.client.info.side_effect = ConnectionError("cluster unavailable")
        self.assertEqual(self.store.health(), {"elasticsearch": "down", "talks_indexed": 0})
