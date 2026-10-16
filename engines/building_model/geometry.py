"""Shared geometric operations. Coordinates are metres, X east/Y north/Z up."""

from .model import Rect

TOL = 0.002


def rect(data):
    return Rect(**{k: data[k] for k in ("x", "y", "w", "d")})


def as_rect(r):
    # Keep sufficient precision that adjacent rectangles retain common edges.
    return {k: round(getattr(r, k), 6) for k in ("x", "y", "w", "d")}


def subtract(source, cut):
    """Disjoint rectangular partition of source minus cut; never fills a void."""
    x0, y0 = max(source.x, cut.x), max(source.y, cut.y)
    x1, y1 = min(source.x2, cut.x2), min(source.y2, cut.y2)
    if x1 <= x0 + 1e-8 or y1 <= y0 + 1e-8:
        return [source]
    candidates = [
        Rect(source.x, source.y, source.w, y0 - source.y),
        Rect(source.x, y1, source.w, source.y2 - y1),
        Rect(source.x, y0, x0 - source.x, y1 - y0),
        Rect(x1, y0, source.x2 - x1, y1 - y0),
    ]
    return [r for r in candidates if r.w > 1e-7 and r.d > 1e-7]


def subtract_all(source, cuts):
    pieces = [source]
    for cut in cuts:
        pieces = [part for piece in pieces for part in subtract(piece, cut)]
    return pieces


def edge(a, b, tolerance=TOL):
    for c, d in ((a, b), (b, a)):
        if abs(c.x2 - d.x) <= tolerance:
            lo, hi = max(c.y, d.y), min(c.y2, d.y2)
            if hi - lo > tolerance:
                return "v", (c.x2 + d.x) / 2, lo, hi
        if abs(c.y2 - d.y) <= tolerance:
            lo, hi = max(c.x, d.x), min(c.x2, d.x2)
            if hi - lo > tolerance:
                return "h", (c.y2 + d.y) / 2, lo, hi
    return None


def level_bases(model):
    return {level["id"]: level["elevation"] for level in model["levels"]}


def surface_parts(model, space, surface):
    """Exact slab/roof rectangles, including stair shafts and skylight apertures."""
    cuts = [
        rect(v["rect"])
        for v in model.get("voids", [])
        if v["level"] == space["level"] and surface == "floor"
    ]
    if surface == "roof":
        cuts += [
            rect(o["rect"])
            for o in model["openings"]
            if o["kind"] == "skylight" and o["space_id"] == space["id"]
        ]
    return subtract_all(rect(space["rect"]), cuts)


def door_points(model, opening):
    """Hinge, closed jamb and open leaf endpoint in plan coordinates."""
    from .model import Wall

    wall = next(w for w in model["walls"] if w["id"] == opening["wall_id"])
    host = Wall(
        wall["id"], wall["level"], wall["x1"], wall["y1"], wall["x2"], wall["y2"]
    )
    hinge = host.point_at(opening["offset"] - opening["width"] / 2)
    closed = host.point_at(opening["offset"] + opening["width"] / 2)
    room = rect(
        next(s for s in model["spaces"] if s["id"] == opening["space_id"])["rect"]
    )
    sign = (
        1 if (room.cx > wall["x1"] if host.vertical else room.cy > wall["y1"]) else -1
    )
    leaf = (
        (hinge[0] + sign * opening["width"], hinge[1])
        if host.vertical
        else (hinge[0], hinge[1] + sign * opening["width"])
    )
    return hinge, closed, leaf
