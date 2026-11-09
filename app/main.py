import logging
import hashlib
import re
from datetime import date
from typing import Literal
from pathlib import Path
from time import perf_counter
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .agenda import analyze_agenda, build_day, validate_plan_day
from .search import tokens
from .store import PLACES_DATA, Store
from .smart_search import compatible_levels, interpret_request
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
    day: date | None = None


class DayRequest(BaseModel):
    interests: str = Field(min_length=1, max_length=500)
    mode: Literal["keyword", "hybrid", "auto"] = "keyword"
    track: str | None = None
    level: str | None = None
    captioned_only: bool = False
    day: date = date(2026, 11, 10)
    smart: bool = False


class SavedPlanRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    talk_ids: list[str] = Field(min_length=1, max_length=100)
    day: date | None = None


def plan_owner_hash(planner_key: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", planner_key):
        raise HTTPException(422, "Invalid private plan key.")
    return hashlib.sha256(planner_key.encode("utf-8")).hexdigest()


def validate_plan_talks(talk_ids, day=None):
    unique_ids = list(dict.fromkeys(talk_ids))
    try:
        talks = store.get_talks_by_ids(unique_ids)
    except Exception as exc:
        logging.warning("saved_plan_talk_lookup_failed error_type=%s", type(exc).__name__)
        raise HTTPException(503, "Elasticsearch is unavailable; the plan could not be saved.") from None
    if len(talks) != len(unique_ids):
        raise HTTPException(422, "One or more selected talks are no longer in the Elasticsearch catalogue.")
    try:
        plan_day = validate_plan_day(talks, day)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return unique_ids, talks, plan_day


def safe_plan_call(operation, *args):
    try:
        return operation(*args)
    except Exception as exc:
        logging.warning("saved_plan_operation_failed error_type=%s", type(exc).__name__)
        raise HTTPException(503, "Saved plans require Elasticsearch, which is unavailable right now.") from None


def search_result(q="", track=None, level=None, captioned_only=False, mode="keyword", limit=1000, offset=0, day=None):
    started = perf_counter()
    facets = {}
    strategy_reason = None
    use_hybrid = mode == 'hybrid'
    if mode != 'hybrid':
        talks, source, total, facets = store.search_page(q=q, track=track, level=level,
                                                       captioned_only=captioned_only, offset=offset, size=limit, day=day)
        result = {"mode": "keyword", "requested_mode": mode, "degraded_reason": None}
        keyword_page = (talks, source, total)
        if mode == 'auto':
            if not tokens(q):
                strategy_reason = 'Browsing by filters; keyword retrieval is sufficient.'
            elif source != 'elasticsearch':
                strategy_reason = 'Elasticsearch unavailable; using labelled keyword fallback.'
            elif total < 5:
                use_hybrid = True
                strategy_reason = 'Few literal matches; trying meaning and keyword retrieval together.'
            elif set(tokens(q)) & {'how', 'why', 'diagnose', 'troubleshoot', 'debug', 'understand', 'learn', 'find'}:
                use_hybrid = True
                strategy_reason = 'Natural-language request; combining meaning and keyword retrieval.'
            elif len(tokens(q)) >= 4:
                use_hybrid = True
                strategy_reason = 'Broader query; combining meaning and keyword retrieval.'
            else:
                strategy_reason = 'Strong literal matches; using keyword retrieval.'
    if use_hybrid:
        result = store.hybrid_search(q=q, track=track, level=level, captioned_only=captioned_only, day=day)
        strategy_reason = result.get('strategy_reason') or strategy_reason
        if mode == 'auto' and result['mode'] == 'keyword':
            talks, source, total = keyword_page
        else:
            source = result['source']
            total = len(result['talks'])
            talks = result['talks'][offset:offset + limit]
    took_ms = (perf_counter() - started) * 1000
    record_search(q, source, took_ms, len(talks))
    span = trace.get_current_span()
    span.set_attribute("search.requested_mode", mode)
    span.set_attribute("search.mode", result["mode"])
    return {**result, "talks": talks, "source": source, "took_ms": round(took_ms, 2), "total": total,
            "facets": result.get("facets", facets), 'requested_mode': mode, 'strategy_reason': strategy_reason}


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


@app.get('/health/live')
def liveness():
    return {'status': 'alive'}


@app.get("/api/search")
def search(q: str = "", track: str | None = None, level: str | None = None, captioned_only: bool = False, mode: Literal["keyword", "hybrid", "auto"] = "keyword", limit: int = 24, offset: int = 0, smart: bool = False):
    if len(q) > 500:
        raise HTTPException(422, "Search text must be 500 characters or fewer.")
    if not 1 <= limit <= 100 or not 0 <= offset <= 5000:
        raise HTTPException(422, "Search page must contain 1–100 talks and use an offset from 0 to 5000.")
    if not smart or not tokens(q):
        return search_result(q, track, level, captioned_only, mode, limit, offset)
    intent = interpret_request(q, smart=True)
    if not intent['query'] and not (level or intent['level'] or captioned_only or intent['captioned_only'] or track):
        raise HTTPException(422, 'Enter a topic, such as Kubernetes or security.')
    effective_level = level or compatible_levels(intent['level'])
    captions = captioned_only or intent['captioned_only']
    cap = intent['max_talks']
    page_size = min(limit, max(1, cap - offset)) if cap is not None else limit
    result = search_result(intent['query'], track, effective_level, captions, mode, page_size, offset, day=intent['day'])
    if cap is not None:
        result['total'] = min(result['total'], cap)
        result['talks'] = result['talks'][:max(0, cap - offset)]
    return {**result, 'interpretation': {**intent, 'level': effective_level, 'captioned_only': captions}}


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
        return {**analyze_agenda(request.talk_ids, result["talks"], request.day), "source": result["source"]}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.get("/api/plans")
def list_saved_plans(x_planner_key: str = Header(alias="X-Planner-Key", min_length=40, max_length=128)):
    owner_hash = plan_owner_hash(x_planner_key)
    return {"plans": safe_plan_call(store.list_plans, owner_hash), "source": "elasticsearch"}


@app.post("/api/plans")
def save_plan(request: SavedPlanRequest, x_planner_key: str = Header(alias="X-Planner-Key", min_length=40, max_length=128)):
    owner_hash = plan_owner_hash(x_planner_key)
    name = request.name.strip()
    if not name:
        raise HTTPException(422, "Give this plan a name.")
    talk_ids, talks, plan_day = validate_plan_talks(request.talk_ids, request.day)
    plan = safe_plan_call(store.create_plan, owner_hash, name, talk_ids, plan_day)
    return {**plan, "talks": talks, "source": "elasticsearch"}


@app.get("/api/plans/{plan_id}")
def get_saved_plan(plan_id: str, x_planner_key: str = Header(alias="X-Planner-Key", min_length=40, max_length=128)):
    plan = safe_plan_call(store.get_plan, plan_owner_hash(x_planner_key), plan_id)
    if plan is None:
        raise HTTPException(404, "Saved plan not found.")
    try:
        plan_day = validate_plan_day(plan.get('talks', []), plan.get('day'))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {**plan, 'day': plan_day, "source": "elasticsearch"}


@app.put("/api/plans/{plan_id}")
def update_saved_plan(plan_id: str, request: SavedPlanRequest,
                      x_planner_key: str = Header(alias="X-Planner-Key", min_length=40, max_length=128)):
    owner_hash = plan_owner_hash(x_planner_key)
    name = request.name.strip()
    if not name:
        raise HTTPException(422, "Give this plan a name.")
    talk_ids, talks, plan_day = validate_plan_talks(request.talk_ids, request.day)
    existing = safe_plan_call(store.get_plan, owner_hash, plan_id)
    if existing is None:
        raise HTTPException(404, 'Saved plan not found.')
    try:
        existing_day = validate_plan_day(existing.get('talks', []), existing.get('day'))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if existing_day and existing_day != plan_day:
        raise HTTPException(422, f'This saved plan is for {existing_day}. Save a new plan for {plan_day}.')
    plan = safe_plan_call(store.update_plan, owner_hash, plan_id, name, talk_ids, plan_day)
    if plan is None:
        raise HTTPException(404, "Saved plan not found.")
    return {**plan, "talks": talks, "source": "elasticsearch"}


@app.delete("/api/plans/{plan_id}")
def delete_saved_plan(plan_id: str, x_planner_key: str = Header(alias="X-Planner-Key", min_length=40, max_length=128)):
    deleted = safe_plan_call(store.delete_plan, plan_owner_hash(x_planner_key), plan_id)
    if not deleted:
        raise HTTPException(404, "Saved plan not found.")
    return {"deleted": True, "id": plan_id, "source": "elasticsearch"}


@app.post("/api/build-my-day")
def build_my_day(request: DayRequest):
    if not tokens(request.interests):
        raise HTTPException(422, 'Enter a topic or experience level, such as beginner sessions.')
    if request.day not in {date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)}:
        raise HTTPException(422, "Choose a day from November 9 through November 12, 2026.")
    intent = interpret_request(request.interests, request.smart)
    interests, max_talks = intent['query'], intent['max_talks']
    effective_level = request.level or compatible_levels(intent['level'])
    captions = request.captioned_only or intent['captioned_only']
    browse = not tokens(interests) and bool(effective_level or request.track or captions)
    if not tokens(interests) and not browse:
        raise HTTPException(422, "Enter a topic or experience level, such as beginner sessions.")
    # A relevance-ranked top-100 candidate set is enough for a day plan and
    # avoids transferring the whole conference catalogue for one request.
    result = search_result(interests, request.track, effective_level, captions, 'keyword' if browse else request.mode,
                           limit=100, day=request.day)
    if browse and request.mode == 'hybrid':
        result['requested_mode'] = 'hybrid'
        result['degraded_reason'] = 'No topic supplied; browsing filtered sessions without semantic retrieval.'
    elif browse and request.mode == 'auto':
        result['requested_mode'] = 'auto'
        result['strategy_reason'] = 'No topic supplied; browsing sessions by filters.'
    picked = build_day(result["talks"], interests, semantic=result["mode"] == "hybrid", max_talks=max_talks, browse=browse)
    candidate_count = len(result['talks'])
    selection_note = ''
    if max_talks is not None and len(picked) < max_talks:
        selection_note = (f"Found {len(picked)} compatible sessions from {candidate_count} retrieved candidates "
                          f"for {request.day.isoformat()} under these filters. Maximum {max_talks} is an upper limit; "
                          "matching sessions can overlap. Try another date or relax the experience/topic filters for more options.")
    return {**result, "talks": picked, "total": len(picked), "max_talks": max_talks, "day": request.day.isoformat(),
            "interests": interests, "effective_level": effective_level, "clashes": [],
            'candidate_count': candidate_count, 'selection_note': selection_note,
            "interpretation": {**intent, 'level': effective_level, 'captioned_only': captions, 'day': request.day.isoformat()}}


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
