"""Site planning: setbacks -> buildable footprint, orientation helpers."""

from ..building_model.model import Rect

DEFAULT_SETBACK = 1.5


def footprint(site: dict) -> Rect:
    sb = site.get("setbacks", {}) or {}
    w = sb.get("west", DEFAULT_SETBACK)
    e = sb.get("east", DEFAULT_SETBACK)
    s = sb.get("south", DEFAULT_SETBACK)
    n = sb.get("north", DEFAULT_SETBACK)
    if site["width"] <= w + e or site["depth"] <= s + n:
        raise ValueError("setbacks leave no buildable site")
    return Rect(w, s, site["width"] - w - e, site["depth"] - s - n)


def entrance_band(entrance: str) -> str:
    return {"east": "east", "west": "west", "north": "north", "south": "south"}.get(
        entrance, "south"
    )


def opposite(band: str) -> str:
    return {"east": "west", "west": "east", "north": "south", "south": "north"}[band]
