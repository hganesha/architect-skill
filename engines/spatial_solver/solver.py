"""Deterministic rectangular planning with scored adjacency and exact void subtraction."""

from __future__ import annotations
from collections import defaultdict
import hashlib
import math
from ..building_model.model import Rect, Wall, StairCalc, DISCLAIMER
from ..building_model.geometry import as_rect, rect, edge, subtract_all
from ..building_model.inputs import normalize, SpecError
from ..site_planner.planner import footprint, opposite
from ..building_model.materials import material_for_surface

VARIANTS = [
    {
        "name": "Central court, entrance-led public band",
        "aspect": 1.15,
        "dx": 0.0,
        "dy": 0.0,
    },
    {
        "name": "Quiet-side court, paired public rooms",
        "aspect": 0.85,
        "dx": 0.07,
        "dy": -0.06,
    },
    {"name": "Elongated court, service spine", "aspect": 1.45, "dx": -0.07, "dy": 0.06},
]


def _id(prefix, *parts):
    return (
        prefix + "-" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]
    )


def _zone(s):
    if s.get("zone"):
        return s["zone"]
    return {
        "courtyard": "outdoor",
        "terrace": "outdoor",
        "stair": "circulation",
        "circulation": "circulation",
        "bath": "service",
        "kitchen": "service",
    }.get(
        s.get("type"),
        "public"
        if any(
            k in s["id"]
            for k in ("living", "dining", "foyer", "family", "retail", "cafe")
        )
        else "private",
    )


def _bands(fp, court):
    return {
        "south": Rect(fp.x, fp.y, fp.w, court.y - fp.y),
        "north": Rect(fp.x, court.y2, fp.w, fp.y2 - court.y2),
        "west": Rect(fp.x, court.y, court.x - fp.x, court.d),
        "east": Rect(court.x2, court.y, fp.x2 - court.x2, court.d),
    }


def _subdivide(band, members, horizontal):
    total = sum(s["target_area"] for s in members)
    pos = band.x if horizontal else band.y
    result = []
    for i, s in enumerate(members):
        end = (
            (band.x2 if horizontal else band.y2)
            if i == len(members) - 1
            else pos + (band.w if horizontal else band.d) * s["target_area"] / total
        )
        r = (
            Rect(pos, band.y, end - pos, band.d)
            if horizontal
            else Rect(band.x, pos, band.w, end - pos)
        )
        result.append((s, r))
        pos = end
    return result


def _room_and_gallery(s, r, side, width, court_faces):
    """Keep direct court frontage when requested; otherwise reserve a gallery."""
    if s.get("type") == "stair":
        run = (max(4, round(s.get("_rise", 3.4) / 0.175 / 2) * 2) // 2 - 1) * 0.28 + 2.0
        target_w, target_d = (2.4, run) if r.d >= r.w else (run, 2.4)
        w = target_w if r.w - target_w >= 1.1 else r.w
        d = target_d if r.d - target_d >= 1.1 else r.d
        stair = Rect(r.x, r.y, w, d)
        return [(s, stair)] + [
            (
                {
                    "id": f"gallery-{s['id']}-{i}",
                    "name": "Stair approach",
                    "level": s["level"],
                    "type": "circulation",
                    "zone": "circulation",
                    "target_area": part.area,
                    "_auto": True,
                },
                part,
            )
            for i, part in enumerate(subtract_all(r, [stair]))
        ]
    if s["id"] in court_faces or s.get("type") == "circulation":
        return [(s, r)]
    # Width is an explicit plan allocation, never just a label.
    w = width
    if side == "south":
        room = Rect(r.x, r.y, r.w, r.d - w)
        hall = Rect(r.x, r.y2 - w, r.w, w)
    elif side == "north":
        room = Rect(r.x, r.y + w, r.w, r.d - w)
        hall = Rect(r.x, r.y, r.w, w)
    elif side == "west":
        room = Rect(r.x, r.y, r.w - w, r.d)
        hall = Rect(r.x2 - w, r.y, w, r.d)
    else:
        room = Rect(r.x + w, r.y, r.w - w, r.d)
        hall = Rect(r.x, r.y, w, r.d)
    gallery = {
        "id": f"gallery-{s['id']}",
        "name": f"Gallery · {s['name']}",
        "level": s["level"],
        "type": "circulation",
        "zone": "circulation",
        "target_area": hall.area,
        "_auto": True,
    }
    return [(s, room), (gallery, hall)]


def _layout(
    blocks, spaces, level_id, entrance, variant, constraints, width, court=None
):
    """Greedy start followed by deterministic pair swaps/insertion local search.

    Hard adjacency dominates soft objectives. Infeasibility is returned by the
    validator; optimization never changes a required constraint to a preference.
    """
    usable = {
        k: r for k, r in blocks.items() if min(r.w, r.d) >= 2.4 and max(r.w, r.d) >= 3.0
    }
    thin = {k: r for k, r in blocks.items() if k not in usable and r.area > 1e-5}
    if spaces and not usable:
        raise SpecError(f"{level_id}: no usable room region after subtracting voids")
    # Thin regions remain explicit circulation, not rooms silently squeezed into gaps.
    assigned = {k: [] for k in usable}
    load = {k: 0.0 for k in usable}
    ent = entrance
    for s in sorted(spaces, key=lambda x: (-x["target_area"], x["id"])):
        z = _zone(s)

        def score(k):
            p = (
                0.0
                if (z == "public" and k == ent)
                or (z == "private" and k == opposite(ent))
                else 0.15
            )
            return (load[k] + s["target_area"]) / usable[k].area + p

        k = min(usable, key=score)
        assigned[k].append(s)
        load[k] += s["target_area"]
    court_faces = set()
    if court:
        cid = court[0]["id"]
        court_faces = {
            s["id"]
            for s in spaces
            if cid in s.get("adjacent_to", []) or s.get("near") == cid
        }
        for c in constraints:
            if c["type"] == "adjacency" and cid in c.get("spaces", []):
                court_faces.update(x for x in c["spaces"] if x != cid)
    direct_groups = {
        s.get("open_plan_group")
        for s in spaces
        if s["id"] in court_faces and s.get("open_plan_group")
    }
    court_faces.update(
        s["id"] for s in spaces if s.get("open_plan_group") in direct_groups
    )

    def materialize(groups):
        result = []
        for k, block in usable.items():
            side = (
                k
                if k in ("north", "south", "east", "west")
                else ("north" if block.w >= block.d else "east")
            )
            horizontal = side in ("north", "south")
            if not groups[k]:
                result.append(
                    (
                        {
                            "id": f"gallery-{level_id}-{k}",
                            "name": "Connecting gallery",
                            "type": "circulation",
                            "zone": "circulation",
                            "level": level_id,
                            "target_area": block.area,
                            "_auto": True,
                        },
                        block,
                    )
                )
                continue
            for s, r in _subdivide(block, groups[k], horizontal):
                result += _room_and_gallery(s, r, side, width, court_faces)
        for k, r in thin.items():
            result.append(
                (
                    {
                        "id": f"gallery-{level_id}-{k}",
                        "name": "Void-side gallery",
                        "type": "circulation",
                        "zone": "circulation",
                        "level": level_id,
                        "target_area": r.area,
                        "_auto": True,
                    },
                    r,
                )
            )
        return result

    by_id = {s["id"]: s for s in spaces}
    pairs = {
        tuple(sorted((s["id"], a))): 10.0
        for s in spaces
        for a in s.get("adjacent_to", [])
    }
    for s in spaces:
        if s.get("near"):
            pairs[tuple(sorted((s["id"], s["near"])))] = 15.0
        for other in spaces:
            if (
                s.get("open_plan_group")
                and s.get("open_plan_group") == other.get("open_plan_group")
                and s != other
            ):
                pairs.setdefault(tuple(sorted((s["id"], other["id"]))), 12.0)
    for c in constraints:
        if c["type"] == "adjacency":
            pairs[tuple(sorted(c["spaces"]))] = (
                10000.0
                if c.get("required")
                else {"high": 30, "medium": 15, "low": 5}.get(c.get("priority"), 15)
            )

    def cost(groups):
        placed = materialize(groups)
        rs = {s["id"]: r for s, r in placed}
        if court:
            rs[court[0]["id"]] = court[1]
        value = 0.0
        for sid, s in by_id.items():
            r = rs[sid]
            mw = s.get(
                "min_width",
                2.1
                if s.get("type") == "stair"
                else 1.4
                if _zone(s) == "service"
                else 2.4,
            )
            value += max(0, mw - min(r.w, r.d)) * (10000 if "min_width" in s else 150)
            value += max(0, s.get("min_depth", 0) - max(r.w, r.d)) * 10000
            if "max_area_deviation" in s:
                value += (
                    max(
                        0,
                        abs(r.area - s["target_area"]) / s["target_area"]
                        - s["max_area_deviation"],
                    )
                    * 10000
                )
            value += abs(r.area - s["target_area"]) / s["target_area"]
            if s.get("type") == "stair":
                risers = max(4, round(s.get("_rise", 3.4) / 0.175 / 2) * 2)
                run = (risers // 2 - 1) * 0.28 + 2.0
                value += (
                    max(0, 2.1 - min(r.w, r.d)) * 10000
                    + max(0, run - max(r.w, r.d)) * 10000
                )
            # Keep wet-room groups close; this is a preference, not a plumbing claim.
            if _zone(s) == "service":
                for tid, t in by_id.items():
                    if tid > sid and _zone(t) == "service":
                        value += (
                            math.hypot(r.cx - rs[tid].cx, r.cy - rs[tid].cy) * 0.015
                        )
        for (a, b), weight in pairs.items():
            if a in rs and b in rs:
                e = edge(rs[a], rs[b])
                value += 0 if e and e[3] - e[2] >= 0.95 else weight
        return value

    best = cost(assigned)
    # Coordinate descent across ordering and assignment, with a strict improvement guard.
    for iteration in range(5):
        winner = None
        score = best
        slots = [(k, i) for k, g in assigned.items() for i in range(len(g))]
        for ai, (ka, ia) in enumerate(slots):
            for kb, ib in slots[ai + 1 :]:
                candidate = {k: list(v) for k, v in assigned.items()}
                candidate[ka][ia], candidate[kb][ib] = (
                    candidate[kb][ib],
                    candidate[ka][ia],
                )
                n = cost(candidate)
                if n < score - 1e-8:
                    score = n
                    winner = candidate
            for kb in assigned:
                if ka == kb or len(assigned[ka]) <= 1:
                    continue
                for ib in range(len(assigned[kb]) + 1):
                    candidate = {k: list(v) for k, v in assigned.items()}
                    s = candidate[ka].pop(ia)
                    candidate[kb].insert(ib, s)
                    n = cost(candidate)
                    if n < score - 1e-8:
                        score = n
                        winner = candidate
        if winner is None:
            break
        assigned = winner
        best = score
    return materialize(assigned)


def _stairs(space, levels, spaces, fp):
    idx = next(i for i, l in enumerate(levels) if l["id"] == space["level"])
    if idx == len(levels) - 1:
        raise SpecError(f"{space['id']}: stair has no destination level")
    a, b = levels[idx : idx + 2]
    r = rect(space["rect"])
    along = "y" if r.d >= r.w else "x"
    length = max(r.w, r.d)
    short = min(r.w, r.d)
    landing = 1.0
    calc = vars(
        StairCalc.design(space["id"], a["id"], b["id"], b["elevation"] - a["elevation"])
    )
    half = calc["risers"] // 2 - 1
    calc.update(
        {
            "form": "u",
            "axis": along,
            "width": short,
            "landing_depth": landing,
            "flight_run": half * calc["going_mm"] / 1000,
            "rect": as_rect(r),
        }
    )

    def end_score(high):
        lr = (
            Rect(r.x, r.y2 - landing if high else r.y, r.w, landing)
            if along == "y"
            else Rect(r.x2 - landing if high else r.x, r.y, landing, r.d)
        )
        shaft = (
            Rect(r.x, r.y if high else r.y + landing, r.w, r.d - landing)
            if along == "y"
            else Rect(r.x if high else r.x + landing, r.y, r.w - landing, r.d)
        )
        blocked = [
            rect(other["rect"])
            for other in spaces
            if other["level"] == space["level"]
            and (other["open_to_sky"] or other["double_height"])
        ]
        regions = subtract_all(fp, blocked + [shaft])
        seen = {
            i
            for i, region in enumerate(regions)
            if region.overlaps(lr) or (e := edge(region, lr)) and e[3] - e[2] >= 0.95
        }
        todo = list(seen)
        while todo:
            current = todo.pop()
            for j, region in enumerate(regions):
                if (
                    j not in seen
                    and (e := edge(regions[current], region))
                    and e[3] - e[2] >= 0.95
                ):
                    seen.add(j)
                    todo.append(j)
        access_area = sum(regions[i].area for i in seen)
        lower_access = sum(
            e[3] - e[2]
            for other in spaces
            if other["level"] == space["level"]
            and other["id"] != space["id"]
            and not other["open_to_sky"]
            and not other["double_height"]
            if (e := edge(lr, rect(other["rect"])))
        )
        return access_area * 100 + lower_access

    high = end_score(True) > end_score(False)
    landing_rect = (
        Rect(r.x, r.y2 - landing if high else r.y, r.w, landing)
        if along == "y"
        else Rect(r.x2 - landing if high else r.x, r.y, landing, r.d)
    )
    shaft = (
        Rect(r.x, r.y if high else r.y + landing, r.w, r.d - landing)
        if along == "y"
        else Rect(r.x if high else r.x + landing, r.y, r.w - landing, r.d)
    )
    calc["landing_at"] = "high" if high else "low"
    calc.update(
        {
            "landing_rect": as_rect(landing_rect),
            "shaft_rect": as_rect(shaft),
            "fits": short >= 2.1 and length >= calc["flight_run"] + 2 * landing,
        }
    )
    return calc


def resolve(raw, variant=0):
    if variant not in range(len(VARIANTS)):
        raise SpecError("variant must be 1, 2, or 3 (CLI)")
    spec = normalize(raw)
    v = VARIANTS[variant]
    site = spec["site"]
    buildable = footprint(site)
    levels = spec["levels"]
    ground = levels[0]["id"]
    width = spec.get("planning", {}).get("circulation_width", 1.1)
    source = [dict(s, zone=_zone(s)) for s in spec["spaces"]]
    court_specs = [s for s in source if s.get("open_to_sky") and s["level"] == ground]
    if len(court_specs) > 1:
        raise SpecError(
            "this solver supports one ground courtyard; multiple courts need a different layout engine"
        )
    courts = court_specs[0] if court_specs else None
    g = [s for s in source if s["level"] == ground and s is not courts]
    # Circulation is budgeted rather than stretched into target room areas.
    needed = sum(s["target_area"] for s in g) * 1.30 + (
        courts["target_area"] if courts else 0
    )
    if len(levels) > 1:
        upper_need = max(
            sum(s["target_area"] for s in source if s["level"] == lv["id"]) * 1.3
            for lv in levels[1:]
        )
        ground_void = sum(s["target_area"] for s in g if s.get("double_height")) + (
            courts["target_area"] if courts else 0
        )
        needed = max(needed, upper_need + ground_void + 14.0)
    for s in source:
        if s.get("type") == "stair":
            idx = next(i for i, lv in enumerate(levels) if lv["id"] == s["level"])
            if idx + 1 < len(levels):
                s["_rise"] = levels[idx + 1]["elevation"] - levels[idx]["elevation"]
    aspect = max(0.8, min(1.25, buildable.w / buildable.d)) * (
        1 + variant * 0.04 if not courts else 1
    )
    bw = min(buildable.w, math.sqrt(needed * aspect))
    bd = min(buildable.d, needed / bw)
    if bd >= buildable.d:
        bw = min(buildable.w, needed / bd)
    fp = Rect(buildable.cx - bw / 2, buildable.cy - bd / 2, bw, bd)
    if courts:
        cw = math.sqrt(courts["target_area"] * courts.get("aspect_ratio", v["aspect"]))
        cd = courts["target_area"] / cw
        if cw + 6 > fp.w or cd + 6 > fp.d:
            raise SpecError(
                "courtyard and usable perimeter rooms do not fit inside buildable site"
            )
        court = Rect(
            min(max(fp.cx - cw / 2 + v["dx"] * fp.w, fp.x + 3), fp.x2 - 3 - cw),
            min(max(fp.cy - cd / 2 + v["dy"] * fp.d, fp.y + 3), fp.y2 - 3 - cd),
            cw,
            cd,
        )
        blocks = _bands(fp, court)
        placed = _layout(
            blocks,
            g,
            ground,
            site.get("entrance", "south"),
            variant,
            spec.get("constraints", []),
            width,
            (courts, court),
        )
        placed.append((courts, court))
    else:
        # Two banks along a central circulation spine.
        if fp.w >= fp.d:
            blocks = {
                "south": Rect(fp.x, fp.y, fp.w, fp.d / 2),
                "north": Rect(fp.x, fp.cy, fp.w, fp.d / 2),
            }
        else:
            blocks = {
                "west": Rect(fp.x, fp.y, fp.w / 2, fp.d),
                "east": Rect(fp.cx, fp.y, fp.w / 2, fp.d),
            }
        placed = _layout(
            blocks,
            g,
            ground,
            site.get("entrance", "south"),
            variant,
            spec.get("constraints", []),
            width,
        )
    spaces = []
    voids = []
    stairs = []

    def materialize(items):
        out = []
        for s, r in items:
            lv = next(l for l in levels if l["id"] == s["level"])
            idx = levels.index(lv)
            height = (
                (
                    levels[idx + 1]["elevation"]
                    + levels[idx + 1]["height"]
                    - lv["elevation"]
                )
                if s.get("double_height") and idx + 1 < len(levels)
                else lv["height"]
            )
            if s.get("double_height") and idx + 1 == len(levels):
                raise SpecError(f"{s['id']}: double_height needs a level above")
            height = s.get("ceiling_height", height)
            out.append(
                {
                    **{k: val for k, val in s.items() if not k.startswith("_")},
                    "rect": as_rect(r),
                    "polygon": r.polygon(),
                    "area": round(r.area, 4),
                    "ceiling_height": height,
                    "type": s.get("type", "room"),
                    "zone": _zone(s),
                    "double_height": s.get("double_height", False),
                    "open_to_sky": s.get("open_to_sky", False),
                    "skylight": s.get("skylight", False),
                    "auto_generated": s.get("_auto", False),
                }
            )
        return out

    spaces += materialize(placed)
    for li, lv in enumerate(levels):
        if li:
            blocked = [rect(v["rect"]) for v in voids if v["level"] == lv["id"]]
            landings = []
            for st in stairs:
                if st["to_level"] == lv["id"]:
                    lr = rect(st["landing_rect"])
                    blocked.append(lr)
                    landings.append(
                        (
                            {
                                "id": f"landing-{st['space_id']}",
                                "name": "Stair landing",
                                "type": "circulation",
                                "zone": "circulation",
                                "level": lv["id"],
                                "target_area": lr.area,
                                "_auto": True,
                            },
                            lr,
                        )
                    )
            regions = subtract_all(fp, blocked)
            up = [s for s in source if s["level"] == lv["id"]]
            placed = _layout(
                {f"region-{i}": r for i, r in enumerate(regions)},
                up,
                lv["id"],
                site.get("entrance", "south"),
                variant,
                spec.get("constraints", []),
                width,
            )
            spaces += materialize(placed + landings)
        for s in [s for s in spaces if s["level"] == lv["id"]]:
            if s["type"] == "stair":
                st = _stairs(s, levels, spaces, fp)
                stairs.append(st)
                voids.append(
                    {
                        "id": f"shaft-{s['id']}",
                        "kind": "stair",
                        "space_id": s["id"],
                        "level": st["to_level"],
                        "rect": st["shaft_rect"],
                    }
                )
            if s["open_to_sky"] or s["double_height"]:
                for above in levels[li + 1 :]:
                    if (
                        s["open_to_sky"]
                        or above["elevation"]
                        < lv["elevation"] + s["ceiling_height"] - 0.002
                    ):
                        voids.append(
                            {
                                "id": f"void-{s['id']}-{above['id']}",
                                "kind": "courtyard"
                                if s["open_to_sky"]
                                else "double_height",
                                "space_id": s["id"],
                                "level": above["id"],
                                "rect": s["rect"],
                            }
                        )
    walls = _derive_walls(spaces, levels, fp, voids)
    openings = _derive_openings(spaces, walls, site, fp, levels)
    model = {
        "meta": {
            "name": spec["building"]["name"],
            "variant": variant,
            "variant_name": v["name"],
            "style": spec["building"].get("style", ""),
            "disclaimer": DISCLAIMER,
            "units": "meters",
            "input_units": spec["building"].get("input_units", "meters"),
            "schema_version": "2.0",
        },
        "site": {**site, "footprint": as_rect(fp), "buildable": as_rect(buildable)},
        "levels": levels,
        "spaces": spaces,
        "walls": walls,
        "openings": openings,
        "stairs": stairs,
        "voids": voids,
        "constraints": spec.get("constraints", []),
        "materials": spec.get("materials", {}),
        "planning": spec.get("planning", {}),
        "drawing": spec.get("drawing", {}),
        "render": spec.get("render", {}),
        "roof": {"form": spec.get("roof", {}).get("form", "flat with parapet")},
    }
    model["materials_resolved"] = {
        k: material_for_surface(model, k).to_dict()
        for k in ("exterior_wall", "interior_wall", "floor", "roof", "courtyard")
    }
    from .furnishing import furnish

    model["furniture"], model["landscape"] = furnish(model)
    return model


def _derive_walls(spaces, levels, fp, voids):
    by_id = {s["id"]: s for s in spaces}
    lvmap = {l["id"]: l for l in levels}
    lines = defaultdict(list)
    for s in spaces:
        r = rect(s["rect"])
        for orient, c, lo, hi in [
            ("h", r.y, r.x, r.x2),
            ("h", r.y2, r.x, r.x2),
            ("v", r.x, r.y, r.y2),
            ("v", r.x2, r.y, r.y2),
        ]:
            lines[(s["level"], orient, round(c, 6))].append(
                (round(lo, 6), round(hi, 6), s["id"])
            )
    # A serialized x + width can differ from its neighbour's x by one micron.
    # Cluster near-coincident edges before topology, rather than create false walls.
    axes = defaultdict(list)
    for level, o, c in lines:
        axes[(level, o)].append(c)
        for lo, hi, _ in lines[(level, o, c)]:
            axes[(level, "v" if o == "h" else "h")] += [lo, hi]
    maps = {}
    for key, values in axes.items():
        mapping = {}
        anchor = None
        for value in sorted(set(values)):
            if anchor is None or value - anchor > 0.002:
                anchor = value
            mapping[value] = anchor
        maps[key] = mapping
    snapped = defaultdict(list)
    for (level, o, c), intervals in lines.items():
        perpendicular = maps[(level, "v" if o == "h" else "h")]
        snapped[(level, o, maps[(level, o)][c])] += [
            (perpendicular[a], perpendicular[b], sid) for a, b, sid in intervals
        ]
    result = []
    counts = defaultdict(int)
    for (level, o, c), intervals in sorted(snapped.items()):
        points = sorted({v for lo, hi, _ in intervals for v in (lo, hi)})
        merged = []
        for lo, hi in zip(points, points[1:]):
            if hi - lo < 0.005:
                continue
            mid = (lo + hi) / 2
            ids = sorted({sid for a, b, sid in intervals if a - 1e-6 < mid < b + 1e-6})
            if not ids or all(by_id[i]["open_to_sky"] for i in ids):
                continue
            pair = ids[:2] + [None] * (2 - len(ids[:2]))
            is_court = any(by_id[i]["open_to_sky"] for i in ids)
            exterior = (
                abs(c - (fp.x if o == "v" else fp.y)) < 0.002
                or abs(c - (fp.x2 if o == "v" else fp.y2)) < 0.002
            )
            kind = (
                "courtyard"
                if is_court or (len(ids) == 1 and not exterior)
                else "exterior"
                if len(ids) == 1
                else "interior"
            )
            if merged and merged[-1][1] == lo and merged[-1][2:] == (kind, pair):
                merged[-1] = (merged[-1][0], hi, kind, pair)
            else:
                merged.append((lo, hi, kind, pair))
        for lo, hi, kind, pair in merged:
            semantic = (level, o, tuple(pair))
            n = counts[semantic]
            counts[semantic] += 1
            wid = _id("W", level, o, *pair, n)
            coords = (lo, c, hi, c) if o == "h" else (c, lo, c, hi)
            heights = [
                by_id[i]["ceiling_height"]
                for i in pair
                if i and not by_id[i]["open_to_sky"]
            ]
            # Only a one-sided courtyard/exterior wall can span the full tall space;
            # interior height differences are resolved to the higher adjacent ceiling.
            ht = max(heights) if heights else lvmap[level]["height"]
            w = vars(
                Wall(
                    wid,
                    level,
                    *coords,
                    0.30
                    if kind == "exterior"
                    else 0.20
                    if kind == "courtyard"
                    else 0.15,
                    ht,
                    kind,
                    pair,
                )
            )
            w["base_elevation"] = lvmap[level]["elevation"]
            result.append(w)
    return result


def _derive_openings(spaces, walls, site, fp, levels):
    result = []
    by_id = {s["id"]: s for s in spaces}
    ground = levels[0]["id"]
    ent = site.get("entrance", "south")

    def wallobj(w):
        return Wall(w["id"], w["level"], w["x1"], w["y1"], w["x2"], w["y2"])

    def add(w, kind, width, height, sill, sid, offset=None):
        wo = wallobj(w)
        offset = wo.length / 2 if offset is None else offset
        result.append(
            {
                "id": _id(
                    {"door": "D", "passage": "P", "entrance": "ENT", "window": "WIN"}[
                        kind
                    ],
                    w["id"],
                    kind,
                    sum(o["wall_id"] == w["id"] and o["kind"] == kind for o in result),
                ),
                "kind": kind,
                "glazed": w["kind"] == "courtyard" and kind == "door",
                "wall_id": w["id"],
                "offset": offset,
                "width": width,
                "height": height,
                "sill": sill,
                "space_id": sid,
            }
        )

    def on_side(w):
        return (
            (ent == "south" and abs(w["y1"] - fp.y) < 0.002 and w["y1"] == w["y2"])
            or (ent == "north" and abs(w["y1"] - fp.y2) < 0.002 and w["y1"] == w["y2"])
            or (ent == "west" and abs(w["x1"] - fp.x) < 0.002 and w["x1"] == w["x2"])
            or (ent == "east" and abs(w["x1"] - fp.x2) < 0.002 and w["x1"] == w["x2"])
        )

    entrance = [
        w
        for w in walls
        if w["kind"] == "exterior"
        and w["level"] == ground
        and on_side(w)
        and wallobj(w).length >= 1.3
    ]
    if entrance:

        def preference(w):
            s = by_id[next(i for i in w["spaces"] if i)]
            return (
                0
                if "foyer" in s["id"]
                else 1
                if s["zone"] == "circulation"
                else 2
                if s["zone"] == "public"
                else 3,
                -wallobj(w).length,
            )

        w = min(entrance, key=preference)
        add(
            w,
            "entrance",
            1.1,
            min(2.4, w["height"]),
            0,
            next(i for i in w["spaces"] if i),
        )
    # All traversable shared boundaries get doors; galleries provide the primary route.
    for w in walls:
        a, b = w["spaces"]
        wo = wallobj(w)
        if a and b and wo.length >= 0.95:
            sa, sb = by_id[a], by_id[b]
            grouped = sa.get("open_plan_group") and sa.get("open_plan_group") == sb.get(
                "open_plan_group"
            )
            galleries = sa["zone"] == sb["zone"] == "circulation"
            kind = "passage" if grouped or galleries else "door"
            width = max(0.9, wo.length - 0.12) if kind == "passage" else 0.9
            add(
                w,
                kind,
                width,
                min(w["height"], 2.4 if kind == "door" else w["height"]),
                0,
                b,
            )
        if w["kind"] in ("exterior", "courtyard"):
            hab = next(
                (by_id[i] for i in (a, b) if i and not by_id[i]["open_to_sky"]), None
            )
            if not hab:
                continue
            winwidth = 0.75 if hab["type"] == "bath" else 1.2
            sill = 1.4 if hab["type"] == "bath" else 0.9
            height = min(
                0.8 if hab["type"] == "bath" else 1.3, w["height"] - sill - 0.15
            )
            if height <= 0:
                continue
            for i in range(max(1, int(wo.length // 3))):
                off = wo.length * (i + 1) / (max(1, int(wo.length // 3)) + 1)
                if off - winwidth / 2 < 0.12 or off + winwidth / 2 > wo.length - 0.12:
                    continue
                if any(
                    x["wall_id"] == w["id"]
                    and abs(off - x["offset"]) < (winwidth + x["width"]) / 2 + 0.15
                    for x in result
                ):
                    continue
                add(w, "window", winwidth, height, sill, hab["id"], off)
    for s in spaces:
        if s["skylight"]:
            r = rect(s["rect"])
            w = min(1.8, r.w - 0.6)
            d = min(1.2, r.d - 0.6)
            if min(w, d) <= 0:
                raise SpecError(f"{s['id']}: space too small for skylight")
            result.append(
                {
                    "id": f"SKY-{s['id']}",
                    "kind": "skylight",
                    "wall_id": None,
                    "roof_id": f"roof-{s['id']}",
                    "offset": 0,
                    "width": w,
                    "depth": d,
                    "height": 0.08,
                    "sill": 0,
                    "space_id": s["id"],
                    "rect": as_rect(Rect(r.cx - w / 2, r.cy - d / 2, w, d)),
                }
            )
    return result
