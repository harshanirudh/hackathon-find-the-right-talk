"""Elasticsearch query construction and explicitly labelled outage fallback."""
import re
from datetime import date, timedelta

FIELDS = {"title": 3, "tags": 2, "speaker": 2, "description": 1}


def tokens(text):
    return re.findall(r"[\w]+", text.lower())


def build_query(q="", track=None, level=None, captioned_only=False, day=None):
    filters = []
    if track:
        filters.append({"term": {"track": track}})
    if level:
        filters.append({"terms": {"level": level}} if isinstance(level, list) else {"term": {"level": level}})
    if captioned_only:
        filters.append({"term": {"accessibility.captioned": True}})
    if day:
        day_start = date.fromisoformat(str(day))
        next_day = day_start + timedelta(days=1)
        filters.append({"range": {"start": {"gte": f"{day_start.isoformat()}T00:00:00-07:00",
                                              "lt": f"{next_day.isoformat()}T00:00:00-07:00"}}})
    match = {"multi_match": {"query": q, "fields": ["title^3", "tags^2", "speaker^2", "description"], "operator": "or"}} if q.strip() else {"match_all": {}}
    return {"bool": {"must": [match], "filter": filters}}


def fallback_search(talks, q="", track=None, level=None, captioned_only=False):
    terms = set(tokens(q))
    ranked = []
    for talk in talks:
        if track and talk["track"] != track:
            continue
        if level and talk["level"] not in (level if isinstance(level, list) else [level]):
            continue
        if captioned_only and not talk["accessibility"]["captioned"]:
            continue
        score = 0
        for field, weight in FIELDS.items():
            value = talk[field]
            words = set(tokens(" ".join(value) if isinstance(value, list) else value))
            score += weight * len(terms & words)
        if not terms or score:
            ranked.append((score, talk))
    return [dict(talk) for _, talk in sorted(ranked, key=lambda pair: (-pair[0], pair[1]["start"], pair[1]["id"]))]
