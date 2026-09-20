# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""NAVI venue directory: answer "where is X?" for the whole building.

  uv run venue.py judging          # look up a place
  uv run venue.py --list           # every place, grouped by floor
  uv run venue.py --floor 3        # what is on floor 3

venue.yaml is transcribed from the official floor maps. It only carries
semantic knowledge (floor, room, how to get there) — the planner never reads
it. Physical driving goes through places.yaml, which holds SLAM poses.
"""
import re
import sys
from pathlib import Path

import yaml

VENUE_FILE = Path(__file__).with_name("venue.yaml")

# Words that carry no meaning in "where is the nearest washroom please"
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "where", "how", "do", "i", "me", "my",
    "to", "at", "in", "on", "of", "for", "get", "go", "going", "take", "find",
    "nearest", "closest", "near", "please", "can", "you", "we", "room", "rooms",
    "place", "any", "some", "there", "here", "it", "this", "that", "what", "s",
}


def _normalize(text):
    return re.sub(r"[^a-z0-9 ]+", " ", str(text).lower()).strip()


def _tokens(text):
    return {t for t in _normalize(text).split() if t and t not in _STOPWORDS}


def load_venue():
    """Parsed venue.yaml, or an empty skeleton if the file is missing."""
    if not VENUE_FILE.exists():
        return {"venue": {}, "floors": {}, "places": []}
    data = yaml.safe_load(VENUE_FILE.read_text()) or {}
    data.setdefault("venue", {})
    data.setdefault("floors", {})
    data.setdefault("places", [])
    return data


def floors_of(place):
    """Every floor a place appears on, as a list (handles `floor` and `floors`)."""
    if place.get("floors"):
        return list(place["floors"])
    if place.get("floor") is not None:
        return [place["floor"]]
    return []


def _searchable(place):
    """All the strings a query could reasonably match against."""
    parts = [place.get("name", "")]
    parts += list(place.get("aliases") or [])
    for key in ("nickname", "room", "kind"):
        if place.get(key):
            parts.append(place[key])
    return parts


def _score(query, place):
    """0-100 relevance. Exact name/alias beats substring, which beats token overlap."""
    q_norm = _normalize(query)
    q_tokens = _tokens(query)
    if not q_norm:
        return 0.0

    best = 0.0
    for candidate in _searchable(place):
        c_norm = _normalize(candidate)
        if not c_norm:
            continue
        if q_norm == c_norm:
            return 100.0
        # "judging hq" for query "judging", or a spoken room number like "7363"
        if q_norm in c_norm or c_norm in q_norm:
            longer = max(len(q_norm), len(c_norm))
            best = max(best, 90.0 * (min(len(q_norm), len(c_norm)) / longer) + 5.0)
        overlap = q_tokens & _tokens(candidate)
        if overlap:
            best = max(best, 70.0 * len(overlap) / max(1, len(q_tokens)))
    return best


def search(query, limit=3, min_score=25.0):
    """Best-matching places for a free-text query, highest score first."""
    scored = []
    for place in load_venue()["places"]:
        score = _score(query, place)
        if score >= min_score:
            scored.append((score, place))
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("name", "")))
    return [place for _, place in scored[:limit]]


_ACRONYMS = {"hq", "qnx", "mlh", "crt", "pse", "e5", "e6", "e7", "nfc", "rbc",
             "3a", "3b", "4a", "4b", "4c", "5a", "5b"}


def _title(name):
    """Title-case a place name without mangling acronyms and room codes."""
    return " ".join(w.upper() if w in _ACRONYMS else w.capitalize() for w in str(name).split())


def describe(place):
    """One or two spoken sentences: what it is, where it is, how to get there."""
    name = _title(place.get("name", "somewhere"))
    if place.get("nickname"):
        name = f"{name} ({place['nickname']})"

    floors = floors_of(place)
    if len(floors) > 2:
        where = "on every floor"
    elif len(floors) == 2:
        where = f"on floors {floors[0]} and {floors[1]}"
    elif floors:
        where = f"on floor {floors[0]}"
    else:
        where = ""

    building = place.get("building")
    if building and building != "outside":
        where = f"{where} of {building}".strip()
    elif building == "outside":
        where = "outside the building"

    room = place.get("room")
    if not room:
        room = ""
    elif str(room).lower().startswith("room"):
        room = f", {room}"            # already reads as "rooms A through L"
    else:
        room = f", room {room}"
    head = f"{name} is {where}{room}." if where else f"{name}{room}."

    detail = " ".join(str(place.get("directions", "")).split())
    schedule = place.get("schedule")
    if schedule:
        detail = f"{detail} Open {schedule}.".strip()

    # Most `directions` already state the floor, so leading with `head` too would
    # say it twice. Keep head only when it adds something.
    states_floor = len(floors) != 1 or f"floor {floors[0]}" in detail.lower()
    return detail if (detail and states_floor) else f"{head} {detail}".strip()


def as_dict(place, navigable=False):
    """Compact JSON-able record for the Gemini tool response."""
    return {
        "name": place.get("name"),
        "floor": floors_of(place),
        "building": place.get("building"),
        "room": place.get("room"),
        "kind": place.get("kind"),
        "schedule": place.get("schedule"),
        "spoken_answer": describe(place),
        "robot_can_drive_there": navigable,
    }


def index_for_prompt():
    """Compact 'name (floor N)' index, small enough to inline in a system prompt."""
    by_floor = {}
    everywhere = []
    for place in load_venue()["places"]:
        floors = floors_of(place)
        if len(floors) > 2:
            everywhere.append(place.get("name", ""))
            continue
        for floor in floors:
            by_floor.setdefault(floor, []).append(place.get("name", ""))

    lines = []
    for floor in sorted(by_floor):
        names = ", ".join(sorted(set(by_floor[floor])))
        lines.append(f"Floor {floor}: {names}")
    if everywhere:
        lines.append(f"Every floor: {', '.join(sorted(set(everywhere)))}")
    return "\n".join(lines)


def main(argv):
    data = load_venue()
    if len(argv) > 1 and argv[1] == "--list":
        print(index_for_prompt())
        return
    if len(argv) > 2 and argv[1] == "--floor":
        wanted = int(argv[2])
        theme = data["floors"].get(wanted, "")
        print(f"Floor {wanted}: {theme}\n")
        for place in data["places"]:
            if wanted in floors_of(place):
                print(f"  - {describe(place)}")
        return

    query = " ".join(argv[1:]).strip()
    if not query:
        print(__doc__)
        sys.exit(2)

    hits = search(query)
    if not hits:
        print(f"No match for {query!r}. Try `--list` to see every place.")
        sys.exit(1)
    for place in hits:
        print(describe(place))
        print()


if __name__ == "__main__":
    main(sys.argv)
