"""Core acceptance checks; runnable with unittest as well as pytest."""
import unittest
from itertools import combinations

from app.agenda import analyze_agenda, build_day, day_interest_terms, overlaps, parse_day_request
from app.data import TALKS
from app.search import build_query, fallback_search


def talk(identifier, start="10:00", end="10:45", **changes):
    start = "2026-11-09T" + start + ":00-07:00"
    end = "2026-11-09T" + end + ":00-07:00"
    result = {
        "id": identifier, "title": "Kubernetes security", "speaker": "Ada",
        "track": "Security", "level": "beginner", "start": start, "end": end,
        "room": "A", "description": "Protect your cluster", "tags": ["security"],
        "accessibility": {"captioned": True, "step_free": True,
                          "plain_language_summary": True},
    }
    result.update(changes)
    return result


class SearchTests(unittest.TestCase):
    def test_seed_is_complete_and_identifiers_unique(self):
        self.assertEqual(len(TALKS), 28)
        self.assertEqual(len({t["id"] for t in TALKS}), 28)
        for item in TALKS:
            for field in ("title", "speaker", "track", "level", "start", "end",
                          "room", "description", "tags", "accessibility"):
                self.assertIn(field, item)

    def test_title_match_ranks_above_description_only_match(self):
        title = talk("title", title="Observability", tags=[], description="Tracing")
        description = talk("description", title="Tracing", tags=[],
                           description="Observability")
        results = fallback_search([description, title], "observability")
        self.assertEqual([t["id"] for t in results], ["title", "description"])

    def test_filters_are_combined(self):
        wanted = talk("wanted")
        wrong_track = talk("track", track="Platform")
        wrong_level = talk("level", level="advanced")
        no_captions = talk("captions", accessibility={"captioned": False})
        results = fallback_search([wanted, wrong_track, wrong_level, no_captions],
                                  "security", track="Security", level="beginner",
                                  captioned_only=True)
        self.assertEqual([t["id"] for t in results], ["wanted"])

    def test_unmatched_query_returns_no_results(self):
        self.assertEqual(fallback_search([talk("a")], "xyzzynonexistent"), [])

    def test_elasticsearch_query_has_boosts_and_exact_filters(self):
        query = build_query("security", "Security", "beginner", True)
        boolean = query["bool"]
        must = boolean["must"]
        if isinstance(must, dict):
            must = [must]
        multi = next(item["multi_match"] for item in must if "multi_match" in item)
        self.assertEqual(multi["query"], "security")
        self.assertTrue({"title^3", "tags^2", "speaker^2"}.issubset(multi["fields"]))
        filters = [item["term"] for item in boolean["filter"]]
        self.assertIn({"track": "Security"}, filters)
        self.assertIn({"level": "beginner"}, filters)
        self.assertIn({"accessibility.captioned": True}, filters)

    def test_day_filter_uses_half_open_local_calendar_interval(self):
        query = build_query("kubernetes", day="2026-11-10")
        self.assertIn({"range": {"start": {"gte": "2026-11-10T00:00:00-07:00",
                                            "lt": "2026-11-11T00:00:00-07:00"}}},
                      query["bool"]["filter"])


class AgendaTests(unittest.TestCase):
    def test_explicit_maximum_is_removed_from_interests_and_parsed(self):
        interests, maximum = parse_day_request("getting started with Kubernetes maximum 5 talks")
        self.assertEqual(interests, "getting started with Kubernetes")
        self.assertEqual(maximum, 5)
        interests, maximum = parse_day_request("cloud security, no more than three sessions")
        self.assertEqual(interests, "cloud security")
        self.assertEqual(maximum, 3)
        self.assertEqual(day_interest_terms("getting started with Kubernetes"), "getting started kubernetes")

    def test_generated_day_honors_explicit_talk_cap(self):
        interests, maximum = parse_day_request("Kubernetes, maximum 5 talks")
        day = build_day(fallback_search(TALKS, interests), interests, max_talks=maximum)
        self.assertEqual(len(day), 5)

    def test_back_to_back_is_compatible(self):
        a, b = talk("a", end="11:15"), talk("b", start="11:15", end="12:00")
        self.assertFalse(overlaps(a, b))
        self.assertFalse(overlaps(b, a))

    def test_partial_and_contained_overlap(self):
        a = talk("a", "10:00", "11:00")
        for b in (talk("b", "10:30", "11:30"), talk("c", "10:15", "10:45")):
            self.assertTrue(overlaps(a, b))
            self.assertTrue(overlaps(b, a))

    def test_alternatives_are_related_and_fit_entire_remaining_agenda(self):
        a, b = talk("a"), talk("b", "10:15", "11:00")
        later = talk("later", "12:00", "12:45")
        valid = talk("valid", "11:00", "11:45")
        blocked = talk("blocked", "12:15", "13:00")
        unrelated = talk("unrelated", "14:00", "14:45", track="Data", tags=["sql"])
        catalogue = [a, b, later, valid, blocked, unrelated]
        result = analyze_agenda(["a", "b", "later"], catalogue)
        self.assertEqual(len(result["clashes"]), 1)
        self.assertEqual(set(result["clashes"][0]["talk_ids"]), {"a", "b"})
        selected = {t["id"]: t for t in result["talks"]}
        for replaced, options in result["alternatives"].items():
            self.assertLessEqual(len(options), 3)
            for candidate in options:
                self.assertNotIn(candidate["id"], selected)
                self.assertTrue(candidate["track"] == selected[replaced]["track"]
                                or set(candidate["tags"]) & set(selected[replaced]["tags"]))
                self.assertTrue(all(not overlaps(candidate, item)
                                    for identifier, item in selected.items()
                                    if identifier != replaced))
        self.assertIn("valid", [t["id"] for t in result["alternatives"]["a"]])

    def test_unknown_id_is_rejected(self):
        with self.assertRaises(ValueError):
            analyze_agenda(["missing"], [talk("a")])

    def test_empty_agenda_has_no_clashes(self):
        result = analyze_agenda([], TALKS)
        self.assertEqual(result["talks"], [])
        self.assertEqual(result["clashes"], [])

    def test_generated_day_is_relevant_ordered_and_clash_free(self):
        interests = "kubernetes, security, beginner"
        ranked = fallback_search(TALKS, interests)
        day = build_day(ranked, interests)
        self.assertTrue(day)
        self.assertEqual([t["start"] for t in day], sorted(t["start"] for t in day))
        self.assertEqual(len({t["id"] for t in day}), len(day))
        for a, b in combinations(day, 2):
            self.assertFalse(overlaps(a, b))
        for item in day:
            searchable = " ".join(str(item.get(key, "")) for key in
                                  ("title", "description", "tags", "speaker", "level")).lower()
            self.assertTrue(any(term in searchable for term in
                                ("kubernetes", "security", "beginner")))
            self.assertTrue(item["reason"].strip())

    def test_empty_interests_are_rejected(self):
        for interests in ("", "   ", ", ,"):
            with self.subTest(interests=interests), self.assertRaises(ValueError):
                build_day(TALKS, interests)


if __name__ == "__main__":
    unittest.main()
