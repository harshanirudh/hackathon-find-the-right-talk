"""Verify the running demo against real Elasticsearch, not the fallback."""
import json
import os
from datetime import datetime
from urllib.request import Request, urlopen


BASE = os.getenv("APP_URL", "http://127.0.0.1:8000").rstrip("/")


def request(path, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(BASE + path, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def check(condition, message):
    if not condition:
        raise SystemExit(message)


def main():
    health = request("/health")
    check(health["elasticsearch"] == "up", "Elasticsearch is not up")
    check(health["talks_indexed"] >= 500, "Expected the official KubeCon schedule plus demo samples")
    search = request("/api/search?q=kubernetes")
    check(search["source"] == "elasticsearch", "Search used fallback")
    check(bool(search["talks"]), "Search returned no results")
    official = request("/api/search?q=Tracing+at+Scale")
    check(any(t["title"].startswith("Tracing at Scale") and t.get("source_url") for t in official["talks"]),
          "Official KubeCon session or its source link is missing")
    observability = request("/api/search?q=observability&limit=24")
    check(sum(item["doc_count"] for item in observability["facets"]["track"]) == observability["total"],
          "Track facets do not sum to the live result count")
    check(sum(item["doc_count"] for item in observability["facets"]["level"]) == observability["total"],
          "Level facets do not sum to the live result count")
    check(any("<mark>" in fragment for talk in observability["talks"]
              for fragments in talk.get("highlights", {}).values() for fragment in fragments),
          "Elasticsearch did not return highlight markup")
    venue_hotels = request("/api/places?category=hotel")
    check(venue_hotels["source"] == "elasticsearch" and venue_hotels["total"] > 0,
          "Nearby hotel lookup did not query Elasticsearch")
    venue = request("/api/places")
    check(venue["source"] == "elasticsearch" and len(venue["places"]) >= 5,
          "Expected at least five Elasticsearch-indexed places")
    distances = [place["distance_m"] for place in venue["places"]]
    check(distances == sorted(distances), "Nearby places are not sorted by distance")
    check(not any(any(forbidden in place for forbidden in ("rating", "price", "photo", "availability"))
                   for place in venue["places"]), "Place records contain fields not present in OSM source data")
    filtered = request("/api/search?q=kubernetes&captioned_only=true")
    check(filtered["source"] == "elasticsearch", "Filtered search used fallback")
    check(bool(filtered["talks"]), "Captioned search returned no results")
    check(all(t["accessibility"]["captioned"] for t in filtered["talks"]),
          "Captioned-only filter leaked an uncaptioned talk")
    day = request("/api/build-my-day", {"interests": "kubernetes, security, beginner"})
    check(day["source"] == "elasticsearch", "Day builder used fallback")
    check(bool(day["talks"]), "Day builder returned no talks")
    for previous, current in zip(day["talks"], day["talks"][1:]):
        check(datetime.fromisoformat(previous["end"]) <= datetime.fromisoformat(current["start"]),
              "Generated day contains overlapping sessions")
    agenda = request("/api/agenda", {"talk_ids": [t["id"] for t in day["talks"]]})
    check(agenda["source"] == "elasticsearch", "Agenda used fallback")
    check(not agenda["clashes"], "Generated agenda reports clashes")
    print(f"PASS: Elasticsearch, {health['talks_indexed']} sessions, OSM geo search, facets, highlights, captions, and clash-free day")


if __name__ == "__main__":
    main()
