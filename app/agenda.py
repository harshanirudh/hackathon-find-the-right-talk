"""Scheduling uses half-open intervals: a session can start when another ends."""
from datetime import datetime
from itertools import combinations
import re
from .search import tokens

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_DAY_STOPWORDS = {"a", "an", "and", "for", "from", "in", "me", "my", "of", "on", "or", "the", "to", "with"}
_MAX_TALKS = re.compile(
    r"\b(?:(?:maximum|max)(?:\s+of)?|at\s+most|no\s+more\s+than|up\s+to|limit\s+to)\s+"
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:talks?|sessions?)?\b",
    re.IGNORECASE,
)


def parse_day_request(text):
    """Remove an explicit talk-count constraint from search interests."""
    match = _MAX_TALKS.search(text)
    if not match:
        return text.strip(), None
    value = match.group(1).lower()
    maximum = int(value) if value.isdigit() else _NUMBER_WORDS[value]
    interests = (text[:match.start()] + " " + text[match.end():]).strip(" ,;:-\t\n")
    return interests, maximum


def day_interest_terms(text):
    return " ".join(term for term in tokens(text) if term not in _DAY_STOPWORDS)


def overlaps(a, b):
    return datetime.fromisoformat(a["start"]) < datetime.fromisoformat(b["end"]) and datetime.fromisoformat(b["start"]) < datetime.fromisoformat(a["end"])


def analyze_agenda(talk_ids, talks):
    lookup = {talk["id"]: talk for talk in talks}
    unknown = sorted(set(talk_ids) - lookup.keys())
    if unknown:
        raise ValueError("Unknown talk IDs: " + ", ".join(unknown))
    selected = sorted([lookup[i] for i in dict.fromkeys(talk_ids)], key=lambda t: (t["start"], t["id"]))
    clashes = [{"talk_ids": [a["id"], b["id"]]} for a, b in combinations(selected, 2) if overlaps(a, b)]
    conflicted = {i for clash in clashes for i in clash["talk_ids"]}
    alternatives = {}
    for original in selected:
        if original["id"] not in conflicted:
            continue
        rest = [t for t in selected if t["id"] != original["id"]]
        candidates = [t for t in talks if t["id"] not in talk_ids
                      and (t["track"] == original["track"] or set(t["tags"]) & set(original["tags"]))
                      and not any(overlaps(t, other) for other in rest)]
        candidates.sort(key=lambda t: (t["track"] != original["track"], -len(set(t["tags"]) & set(original["tags"])), t["start"], t["id"]))
        alternatives[original["id"]] = candidates[:3]
    return {"talks": selected, "clashes": clashes, "alternatives": alternatives}


def build_day(ranked_talks, interests, semantic=False, max_talks=None):
    interests_tokens = set(tokens(day_interest_terms(interests)))
    if not interests_tokens:
        raise ValueError("Enter at least one interest, such as Kubernetes or security.")
    chosen = []
    for talk in ranked_talks:
        if max_talks is not None and len(chosen) >= max_talks:
            break
        text = " ".join([talk["title"], talk["speaker"], talk["description"], *talk["tags"]])
        matches = sorted(interests_tokens & set(tokens(text)))
        if (not matches and not semantic) or any(overlaps(talk, other) for other in chosen):
            continue
        reason = "Matches " + ", ".join(matches) + "; " if matches else "Retrieved by meaning for your interests; "
        if talk["accessibility"]["captioned"]:
            reason += "captioned; "
        chosen.append({**talk, "reason": reason + "fits your day without a clash."})
    return sorted(chosen, key=lambda t: (t["start"], t["id"]))
