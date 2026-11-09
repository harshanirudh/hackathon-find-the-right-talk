"""Fetch a dated OSM snapshot around The Shop; never called by the demo app."""
import json
from pathlib import Path

import httpx

VENUE = {"name": "The Shop Workspace", "lat": 40.76032, "lon": -111.88099,
         "address": "350 E 400 S, Salt Lake City, UT"}
ENDPOINT = "https://overpass-api.de/api/interpreter"
OUT = Path(__file__).resolve().parents[1] / "data" / "places.json"
QUERY = """[out:json][timeout:25];
(
  node["tourism"="hotel"](around:1000,40.76032,-111.88099);
  way["tourism"="hotel"](around:1000,40.76032,-111.88099);
  node["amenity"~"restaurant|cafe|bar|pub"](around:1000,40.76032,-111.88099);
  way["amenity"~"restaurant|cafe|bar|pub"](around:1000,40.76032,-111.88099);
);
out center;"""

# Curated fallback verified against Photon (OSM-backed search) on 2026-11-09.
# Each OSM object ID is recorded in the ID; names/addresses/coordinates are
# copied from those map features. The primary Overpass service returned 502.
FALLBACK_PLACES = [
    {"id": "osm-node-13776749561", "name": "Hallowed Grounds", "category": "cafe", "address": "370 South 300 East, Salt Lake City, UT 84111", "website": "", "lat": 40.7609148, "lon": -111.882989},
    {"id": "osm-node-2328421316", "name": "Stoneground Kitchen", "category": "restaurant", "address": "249 East 400 South, Salt Lake City, UT 84111", "website": "", "lat": 40.7609919, "lon": -111.883684},
    {"id": "osm-node-12094299354", "name": "Millcrepes", "category": "restaurant", "address": "330 East 400 South, Salt Lake City, UT 84111", "website": "", "lat": 40.760176, "lon": -111.8821783},
    {"id": "osm-node-13331225512", "name": "JJ Coffee Co", "category": "cafe", "address": "330 East 400 South, Salt Lake City, UT 84111", "website": "", "lat": 40.760446, "lon": -111.8813858},
    {"id": "osm-node-9335676372", "name": "Les Banh Mi", "category": "restaurant", "address": "249 East 400 South, Salt Lake City, UT 84111", "website": "", "lat": 40.7608832, "lon": -111.8837131},
    {"id": "osm-node-2327642665", "name": "Cafe Rio", "category": "restaurant", "address": "532 East 400 South, Salt Lake City, UT 84111", "website": "", "lat": 40.7602663, "lon": -111.875525},
    {"id": "osm-relation-6144703", "name": "Grand America Hotel", "category": "hotel", "address": "555 South Main Street, Salt Lake City, UT 84111", "website": "", "lat": 40.7573462, "lon": -111.8889902},
    {"id": "osm-way-223923170", "name": "Salt Lake City Marriott City Center", "category": "hotel", "address": "220 South State Street, Salt Lake City, UT 84111", "website": "", "lat": 40.7643327, "lon": -111.8885995},
]


def category(tags):
    if tags.get("tourism") == "hotel":
        return "hotel"
    return {"restaurant": "restaurant", "cafe": "cafe", "bar": "bar", "pub": "bar"}.get(tags.get("amenity"))


def address(tags):
    street = " ".join(part for part in [tags.get("addr:housenumber"), tags.get("addr:street")] if part)
    locality = ", ".join(part for part in [tags.get("addr:city"), tags.get("addr:state")] if part)
    return ", ".join(part for part in [street, locality, tags.get("addr:postcode")] if part)


def main():
    rows = []
    fallback_reason = None
    try:
        response = httpx.post(ENDPOINT, data={"data": QUERY},
                              headers={"User-Agent": "find-the-right-talk-hackathon/1.0"}, timeout=45)
        response.raise_for_status()
        for element in response.json().get("elements", []):
            tags = element.get("tags", {})
            point = element if element["type"] == "node" else element.get("center", {})
            kind = category(tags)
            if not tags.get("name") or not kind or "lat" not in point or "lon" not in point:
                continue
            rows.append({"id": f"osm-{element['type']}-{element['id']}", "name": tags["name"],
                         "category": kind, "address": address(tags),
                         "website": tags.get("website") or tags.get("contact:website") or "",
                         "lat": point["lat"], "lon": point["lon"]})
        if len(rows) < 5:
            fallback_reason = f"Overpass returned fewer than five named places ({len(rows)})."
    except (httpx.HTTPError, ValueError) as exc:
        fallback_reason = f"Overpass unavailable ({type(exc).__name__})."
    if fallback_reason:
        rows = [dict(place) for place in FALLBACK_PLACES]
    rows.sort(key=lambda item: (item["category"], item["name"].casefold(), item["id"]))
    OUT.write_text(json.dumps({"venue": VENUE, "radius_m": 1000, "source": ENDPOINT,
                               "attribution": "© OpenStreetMap contributors", "fetched_from_overpass": not bool(fallback_reason),
                               "curated_fallback_reason": fallback_reason,
                               "places": rows}, ensure_ascii=False, indent=2) + "\n")
    label = "curated OSM fallback" if fallback_reason else "Overpass snapshot"
    print(f"Saved {len(rows)} places ({label}) to {OUT.relative_to(OUT.parents[1])}")


if __name__ == "__main__":
    main()
