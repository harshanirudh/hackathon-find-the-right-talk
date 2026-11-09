"""Exercise real hybrid retrieval and optional provider-aware supporting evidence."""
import json
import os
from pathlib import Path
from time import perf_counter
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = os.getenv("APP_URL", "http://127.0.0.1:8000").rstrip("/")


def request(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=90) as response:
        return json.load(response)


def main():
    query = "diagnose sluggish microservices"
    keyword = request("/api/search?" + urlencode({"q": query, "mode": "keyword"}))
    timings = []
    for _ in range(2):
        started = perf_counter()
        hybrid = request("/api/search?" + urlencode({"q": query, "mode": "hybrid"}))
        timings.append(round((perf_counter() - started) * 1000, 2))
        assert hybrid["mode"] == "hybrid", hybrid.get("degraded_reason")
        assert hybrid["source"] == "elasticsearch"
        assert hybrid["talks"], "No actual semantic results"
        assert all("embedding" not in talk for talk in hybrid["talks"])
    filtered = request("/api/search?" + urlencode({"q": query, "mode": "hybrid", "captioned_only": "true"}))
    assert filtered["mode"] == "hybrid", filtered.get("degraded_reason")
    assert all(t["accessibility"]["captioned"] for t in filtered["talks"])
    day = request("/api/build-my-day", {"interests": query, "mode": "hybrid"})
    assert day["mode"] == "hybrid" and day["talks"]
    agenda = request("/api/agenda", {"talk_ids": [t["id"] for t in day["talks"]]})
    assert not agenda["clashes"]
    report = {"query": query, "keyword_results": keyword["total"],
              "hybrid_results": hybrid["total"], "search_wall_ms": timings,
              "top_titles": [t["title"] for t in hybrid["talks"][:3]],
              "day_talks": len(day["talks"])}
    if os.getenv("CHECK_GENERATION", "1") == "1":
        started = perf_counter()
        talk = hybrid["talks"][0]
        explanation = request("/api/explain", {"talk_id": talk["id"], "query": query})
        assert explanation["available"], explanation.get("degraded_reason")
        assert explanation["source"] in ("ollama", "elasticsearch")
        assert explanation["explanation"] and explanation["evidence"]
        for evidence in explanation["evidence"]:
            assert evidence["quote"] in talk[evidence["field"]]
        report["generation_wall_ms"] = round((perf_counter() - started) * 1000, 2)
        report["explanation"] = explanation
    output = Path(__file__).resolve().parent.parent / "artifacts"
    output.mkdir(exist_ok=True)
    (output / "ai-verification.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("PASS: real Elasticsearch hybrid retrieval, filters, semantic day" +
          (", and verified supporting evidence" if "explanation" in report else ""))


if __name__ == "__main__":
    main()
