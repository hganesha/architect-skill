"""Optional concept furniture and landscape stored in the canonical model."""

from ..building_model.geometry import rect, as_rect
from ..building_model.model import Rect


def furnish(model):
    furniture = []
    landscape = []
    for s in model["spaces"]:
        r = rect(s["rect"])
        items = s.get("furniture", [])
        automatic = not bool(items)
        if (
            not items
            and model.get("planning", {}).get("furnish")
            and s["zone"] != "circulation"
            and not s["open_to_sky"]
        ):
            if "bed" in s["id"] or "primary" in s["id"] or "guest" in s["id"]:
                items = [
                    {
                        "id": "bed",
                        "name": "Bed",
                        "width": 1.5,
                        "depth": 2.0,
                        "height": 0.55,
                        "clearance": 0.45,
                    }
                ]
            elif s["type"] == "kitchen":
                items = [
                    {
                        "id": "counter",
                        "name": "Kitchen counter",
                        "width": 1.8,
                        "depth": 0.6,
                        "height": 0.9,
                        "clearance": 0.45,
                    }
                ]
            elif "living" in s["id"] or "family" in s["id"]:
                items = [
                    {
                        "id": "sofa",
                        "name": "Sofa",
                        "width": 2.1,
                        "depth": 0.9,
                        "height": 0.8,
                        "clearance": 0.6,
                    }
                ]
        for item in items:
            w, d = item["width"], item["depth"]
            clearance = item.get("clearance", 0.4)
            if automatic and (w + 2 * clearance > r.w or d + 2 * clearance > r.d):
                if d + 2 * clearance <= r.w and w + 2 * clearance <= r.d:
                    w, d = d, w
                else:
                    continue
            x = r.x + item.get("x", max(clearance, (r.w - w) / 2))
            y = r.y + item.get("y", max(clearance, (r.d - d) / 2))
            furniture.append(
                {
                    "id": f"furniture-{s['id']}-{item['id']}",
                    "name": item.get("name", item["id"]),
                    "space_id": s["id"],
                    "level": s["level"],
                    "rect": as_rect(Rect(x, y, w, d)),
                    "height": item.get("height", 0.75),
                    "clearance": clearance,
                    "required": item.get("required", False),
                }
            )
        if s["open_to_sky"] and model.get("planning", {}).get("landscape", True):
            landscape.append(
                {
                    "id": f"tree-{s['id']}",
                    "kind": "tree",
                    "center": [r.cx, r.cy, 0.0],
                    "radius": min(1.1, r.w * 0.2, r.d * 0.2),
                    "height": 3.0,
                }
            )
    return furniture, landscape
