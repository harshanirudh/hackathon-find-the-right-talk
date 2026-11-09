import logging
from datetime import date
from typing import Literal
from pathlib import Path
from time import perf_counter
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .agenda import analyze_agenda, build_day, day_interest_terms, parse_day_request
from .search import tokens
from .store import PLACES_DATA, Store
from .telemetry import configure, record_search
from .local_ai import LocalAIUnavailable
from opentelemetry import trace

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Find the Right Talk", description="Sample cloud-native sessions, searchable through Elasticsearch.")
store = Store()
telemetry_enabled = configure(app)
STATIC = Path(__file__).resolve().parent.parent / "static"
if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


class AgendaRequest(BaseModel):
    talk_ids: list[str] = Field(default_factory=list, max_length=100)


class DayRequest(BaseModel):
    interests: str = Field(min_length=1, max_length=500)
    mode: Literal["keyword", "hybrid"] = "keyword"
    track: str | None = None
    level: str | None = None
    captioned_only: bool = False
    day: date = date(2026, 11, 10)


def search_result(q="", track=None, level=None, captioned_only=False, mode="keyword", limit=1000, offset=0, day=None):
    started = perf_counter()
    facets = {}
    if mode == "hybrid":
        result = store.hybrid_search(q=q, track=track, level=level, captioned_only=captioned_only, day=day)
        talks, source = result["talks"], result["source"]
        total = len(talks)
    else:
        talks, source, total, facets = store.search_page(q=q, track=track, level=level,
                                                       captioned_only=captioned_only, offset=offset, size=limit, day=day)
        result = {"mode": "keyword", "requested_mode": "keyword", "degraded_reason": None}
    took_ms = (perf_counter() - started) * 1000
    record_search(q, source, took_ms, len(talks))
    span = trace.get_current_span()
    span.set_attribute("search.requested_mode", mode)
    span.set_attribute("search.mode", result["mode"])
    return {**result, "talks": talks, "source": source, "took_ms": round(took_ms, 2), "total": total,
            "facets": result.get("facets", facets)}


@app.get("/")
def index():
    if not (STATIC / "index.html").exists():
        return {"message": "Find the Right Talk API", "docs": "/docs"}
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    state = store.health()
    return {**state, "status": "ok" if state["elasticsearch"] == "up" and state["talks_indexed"] else "degraded",
            "telemetry_export_enabled": telemetry_enabled, "sample_data": True}


@app.get("/api/search")
def search(q: str = "", track: str | None = None, level: str | None = None, captioned_only: bool = False, mode: Literal["keyword", "hybrid"] = "keyword", limit: int = 24, offset: int = 0):
    if len(q) > 500:
        raise HTTPException(422, "Search text must be 500 characters or fewer.")
    if not 1 <= limit <= 100 or not 0 <= offset <= 5000:
        raise HTTPException(422, "Search page must contain 1–100 talks and use an offset from 0 to 5000.")
    return search_result(q, track, level, captioned_only, mode, limit, offset)


@app.get("/api/talks")
def talks(track: str | None = None, level: str | None = None, captioned_only: bool = False):
    return search_result("", track, level, captioned_only)


@app.get("/api/places")
def places(category: str | None = None, radius_m: int = 1000):
    if category and category not in {"stay", "eat", "coffee", "hotel", "restaurant", "cafe", "bar"}:
        raise HTTPException(422, "Choose stay, eat, coffee, hotel, restaurant, cafe, or bar.")
    if not 1 <= radius_m <= 5000:
        raise HTTPException(422, "Radius must be between 1 and 5000 metres.")
    try:
        found = store.nearby_places(category, radius_m, size=50)
    except Exception as exc:
        logging.warning("places_search_unavailable error_type=%s", type(exc).__name__)
        raise HTTPException(503, "Elasticsearch venue search is unavailable.") from None
    return {"places": found, "source": "elasticsearch", "total": len(found),
            "venue": PLACES_DATA["venue"], "radius_m": radius_m,
            "data_note": "curated OSM fallback" if not PLACES_DATA.get("fetched_from_overpass") else "Overpass snapshot"}


@app.post("/api/agenda")
def agenda(request: AgendaRequest):
    result = search_result()
    try:
        return {**analyze_agenda(request.talk_ids, result["talks"]), "source": result["source"]}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.post("/api/build-my-day")
def build_my_day(request: DayRequest):
    if request.day not in {date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)}:
        raise HTTPException(422, "Choose a day from November 9 through November 12, 2026.")
    interests, max_talks = parse_day_request(request.interests)
    interests = day_interest_terms(interests)
    if not tokens(interests):
        raise HTTPException(422, "Enter at least one interest, such as Kubernetes or security.")
    # A relevance-ranked top-100 candidate set is enough for a day plan and
    # avoids transferring the whole conference catalogue for one request.
    result = search_result(interests, request.track, request.level, request.captioned_only, request.mode,
                           limit=100, day=request.day)
    picked = build_day(result["talks"], interests, semantic=result["mode"] == "hybrid", max_talks=max_talks)
    return {**result, "talks": picked, "total": len(picked), "max_talks": max_talks, "day": request.day.isoformat(),
            "interests": interests, "clashes": []}


class ExplainRequest(BaseModel):
    talk_id: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=500)


@app.post("/api/explain")
def explain(request: ExplainRequest):
    if not tokens(request.query):
        raise HTTPException(422, "Enter an interest or problem to explain the match.")
    try:
        talk = store.get_talk(request.talk_id)
    except Exception:
        raise HTTPException(503, "Elasticsearch unavailable; verified session evidence is required.") from None
    if talk is None:
        raise HTTPException(404, "Talk not found.")
    if getattr(store, "semantic_provider", "ollama") == "elastic":
        return {"available": True, "source": "elasticsearch", "model": None,
                "explanation": "Supporting passage from this session's description. This is source evidence, not an AI-generated explanation.",
                "evidence": [{"field": "description", "quote": talk["description"]}],
                "degraded_reason": None}
    model = store.ai.generation_model
    try:
        explanation = store.ai.explain(talk, request.query)
        return {"available": True, "source": "ollama", "model": model,
                **explanation, "degraded_reason": None}
    except LocalAIUnavailable as exc:
        return {"available": False, "source": "unavailable", "model": model,
                "explanation": None, "evidence": [], "degraded_reason": str(exc)}
