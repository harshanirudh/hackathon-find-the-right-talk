"""Fetch the public KubeCon NA 2026 schedule from its linked Sessionize API."""
import json
from pathlib import Path

import httpx

API = "https://sessionize.com/api/v2/svi82w6c/view/All"
OUT = Path(__file__).resolve().parents[1] / "data" / "kubecon-na-2026.json"
MAIN_DAYS = {"2026-11-10", "2026-11-11", "2026-11-12"}


def main():
    response = httpx.get(API, timeout=45)
    response.raise_for_status()
    payload = response.json()
    category_names = {item["id"]: item["name"]
                      for category in payload["categories"] for item in category["items"]}
    levels = {item["id"]: item["name"] for category in payload["categories"]
              if category["title"] == "Audience Level" for item in category["items"]}
    rooms = {room["id"]: room["name"] for room in payload["rooms"]}
    speakers = {speaker["id"]: speaker.get("fullName", "") for speaker in payload["speakers"]}
    track_names = {"AI Inference + Agentic", "Application Development + Delivery", "Cloud Native Experience",
                   "Cloud Native Novice", "Connectivity", "Data Processing + Storage", "Emerging + Advanced",
                   "Observability", "Operations + Performance", "Platform Engineering", "Security",
                   "Maintainer Track", "Inclusion + Accessibility"}
    rows = []
    for session in payload["sessions"]:
        start, end = session.get("startsAt"), session.get("endsAt")
        description = (session.get("description") or "").strip()
        if (not start or start[:10] not in MAIN_DAYS or not end or end <= start
                or session.get("isServiceSession") or not description):
            continue
        categories = [category_names.get(item_id, "") for item_id in session.get("categoryItems", [])]
        track = next((name for name in categories if name in track_names), "Conference Sessions")
        audience = next((levels[item_id].lower() for item_id in session.get("categoryItems", []) if item_id in levels), "any level")
        speaker = ", ".join(speakers.get(sid, "") for sid in session.get("speakers", []) if speakers.get(sid)) or "Speaker details unavailable"
        tags = list(dict.fromkeys([track.lower(), audience, *[name.lower() for name in categories if name and name != track]]))
        rows.append({"id": f"kubecon-na-2026-{session['id']}", "title": session["title"], "speaker": speaker,
                     "track": track, "level": audience, "start": start + "-07:00", "end": end + "-07:00",
                     "room": rooms.get(session.get("roomId"), "Room not listed"), "description": description,
                     "tags": tags, "accessibility": {"captioned": None, "step_free": None, "plain_language_summary": None},
                     "source_url": f"https://events.linuxfoundation.org/kubecon-cloudnativecon-north-america/program/schedule/?id={session['id']}",
                     "dataset": "KubeCon NA 2026 official schedule"})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": API, "verified_via": "https://endusers.cncf.io/events/2026/kubecon-na/",
                               "retrieved_on": "2026-11-09", "notice": "Schedule snapshot; verify changes on the official live schedule.",
                               "talks": rows}, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(rows)} main-conference sessions to {OUT.relative_to(OUT.parents[1])}")


if __name__ == "__main__":
    main()
