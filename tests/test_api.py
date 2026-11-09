"""HTTP acceptance tests use a fake store, never a hidden fallback cluster."""
import importlib.util
import unittest
from unittest.mock import patch
from itertools import combinations

DEPENDENCIES = all(importlib.util.find_spec(name) for name in
                   ("fastapi", "httpx", "elasticsearch", "dotenv", "opentelemetry"))
if DEPENDENCIES:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.data import TALKS
    from app.search import fallback_search
    from app.agenda import overlaps


@unittest.skipUnless(DEPENDENCIES, "Install requirements.txt for HTTP acceptance tests")
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.store = patch("app.main.store").start()
        self.addCleanup(patch.stopall)
        self.store.search.side_effect = lambda q="", track=None, level=None, captioned_only=False: (
            fallback_search(TALKS, q, track, level, captioned_only), "fallback")
        def fake_search_page(q="", track=None, level=None, captioned_only=False, offset=0, size=24, day=None):
            items = fallback_search(TALKS, q, track, level, captioned_only)
            if day:
                items = [talk for talk in items if talk["start"][:10] == str(day)]
            return items[offset:offset + size], "fallback", len(items), {"track": [], "level": [], "captioned": []}
        self.store.search_page.side_effect = fake_search_page
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_search_exposes_source_and_combines_accessibility_filter(self):
        response = self.client.get("/api/search", params={"q": "kubernetes", "captioned_only": True})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "fallback")
        self.assertGreater(payload["total"], 0)
        self.assertTrue(all(t["accessibility"]["captioned"] for t in payload["talks"]))
        self.assertGreaterEqual(payload["took_ms"], 0)

    def test_empty_and_punctuation_interests_have_clear_validation_error(self):
        for interests in ("", "   ", ", ,"):
            with self.subTest(interests=interests):
                response = self.client.post("/api/build-my-day", json={"interests": interests})
                self.assertEqual(response.status_code, 422)
                self.assertTrue(response.json()["detail"])

    def test_generated_day_respects_filters_and_has_no_overlaps(self):
        response = self.client.post("/api/build-my-day", json={
            "interests": "kubernetes security beginner", "captioned_only": True, "day": "2026-11-09"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["talks"])
        self.assertEqual(payload["source"], "fallback")
        self.assertEqual(payload["clashes"], [])
        for a, b in combinations(payload["talks"], 2):
            self.assertFalse(overlaps(a, b))
        self.assertTrue(all(t["accessibility"]["captioned"] and t["reason"]
                            for t in payload["talks"]))

    def test_build_my_day_treats_maximum_as_a_cap_not_a_search_term(self):
        response = self.client.post("/api/build-my-day", json={
            "interests": "getting started with kubernetes maximum 5 talks", "day": "2026-11-09"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["max_talks"], 5)
        self.assertEqual(payload["interests"], "kubernetes")
        self.assertLessEqual(payload["total"], 5)
        self.assertEqual(payload["total"], len(payload["talks"]))

    def test_unknown_agenda_id_is_a_client_error(self):
        response = self.client.post("/api/agenda", json={"talk_ids": ["missing"]})
        self.assertEqual(response.status_code, 422)
        self.assertIn("Unknown", response.json()["detail"])

    def test_beginner_intent_filters_candidates_before_scheduling(self):
        for phrase in ("getting started with", "new to", "first steps in", "introductory", "beginner"):
            with self.subTest(phrase=phrase):
                response = self.client.post("/api/build-my-day", json={
                    "interests": phrase + " kubernetes maximum 5 talks", "day": "2026-11-09"})
                payload = response.json()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(payload["interests"], "kubernetes")
                self.assertEqual(payload["effective_level"], "beginner")
                self.assertTrue(payload["talks"])
                self.assertTrue(all(t["level"] == "beginner" for t in payload["talks"]))
                self.assertTrue(all("listed as beginner" in t["reason"] for t in payload["talks"]))
                self.assertEqual(self.store.search_page.call_args.kwargs["level"], "beginner")

    def test_explicit_level_overrides_inferred_beginner_level(self):
        payload = self.client.post("/api/build-my-day", json={
            "interests": "getting started with kubernetes", "level": "advanced",
            "day": "2026-11-09"}).json()
        self.assertEqual(payload["effective_level"], "advanced")
        self.assertEqual(self.store.search_page.call_args.kwargs["level"], "advanced")
        self.assertTrue(all(t["level"] == "advanced" for t in payload["talks"]))

    def test_exact_misspelled_request_enforces_three_session_cap(self):
        response = self.client.post('/api/build-my-day', json={
            'interests': 'beginer kubernets atmost 3 sessions', 'day': '2026-11-09'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['interests'], 'kubernetes')
        self.assertEqual(data['effective_level'], 'beginner')
        self.assertEqual(data['max_talks'], 3)
        self.assertTrue(data['talks'])
        self.assertLessEqual(len(data['talks']), 3)
        self.assertTrue(all(t['level'] == 'beginner' for t in data['talks']))
        self.assertEqual(data['clashes'], [])
        self.assertEqual(self.store.search_page.call_args.kwargs['q'], 'kubernetes')

    def test_introductory_intent_without_topic_browses_beginner_sessions(self):
        response = self.client.post("/api/build-my-day", json={"interests": "getting started", 'day': '2026-11-09'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['talks'])
        self.assertEqual(self.store.search_page.call_args.kwargs['q'], '')
        self.assertEqual(self.store.search_page.call_args.kwargs['level'], 'beginner')

    def test_health_is_degraded_when_cluster_is_down(self):
        self.store.health.return_value = {"elasticsearch": "down", "talks_indexed": 0}
        payload = self.client.get("/health").json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["talks_indexed"], 0)

    def test_venue_places_are_labelled_as_elasticsearch_results(self):
        self.store.nearby_places.return_value = [{"id": "osm-1", "name": "A Cafe", "distance_m": 120,
                                                  "walking_minutes": 2}]
        response = self.client.get("/api/places", params={"category": "coffee"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "elasticsearch")
        self.assertEqual(response.json()["total"], 1)
        self.store.nearby_places.assert_called_once_with("coffee", 1000, size=50)

    def test_excessive_search_text_is_rejected_before_store_call(self):
        response = self.client.get("/api/search", params={"q": "x" * 501})
        self.assertEqual(response.status_code, 422)
        self.store.search_page.assert_not_called()
