"""Concept geometry and program checks. This does not certify code compliance."""

from collections import defaultdict, deque
import math
from ..building_model.model import DISCLAIMER, Rect
from ..building_model.geometry import rect, TOL, level_bases, subtract_all, door_points
from ..building_model.inputs import check_schema, SpecError


def access_graph(model):
    graph = defaultdict(set)
    walls = {w["id"]: w for w in model["walls"]}
    roots = set()
    for o in model["openings"]:
        if o["kind"] not in ("door", "entrance", "passage"):
            continue
        w = walls.get(o["wall_id"])
        if not w:
            continue
        ids = [i for i in w["spaces"] if i]
        if o["kind"] == "entrance" and w["kind"] == "exterior" and len(ids) == 1:
            roots.add(ids[0])
        if len(ids) == 2:
            a, b = ids
            graph[a].add(b)
            graph[b].add(a)
    for st in model.get("stairs", []):
        a, b = st["space_id"], f"landing-{st['space_id']}"
        graph[a].add(b)
        graph[b].add(a)
    return graph, roots


def reachable(graph, roots, blocked=()):
    seen = set(roots) - set(blocked)
    todo = deque(seen)
    while todo:
        for b in graph[todo.popleft()]:
            if b not in seen and b not in blocked:
                seen.add(b)
                todo.append(b)
    return seen


def validate(model):
    fails = []
    warns = []
    oks = []
    try:
        check_schema(model, "geometry-spec")
    except SpecError as e:
        return {
            "status": "FAIL",
            "fail": [str(e)],
            "warn": [],
            "ok": [],
            "metrics": {},
            "disclaimer": DISCLAIMER,
        }
    spaces = model["spaces"]
    by_id = {s["id"]: s for s in spaces}
    walls = {w["id"]: w for w in model["walls"]}
    levels = {l["id"]: l for l in model["levels"]}
    bases = level_bases(model)
    fp = rect(model["site"]["footprint"])
    rs = {s["id"]: rect(s["rect"]) for s in spaces}
    for collection in ("spaces", "levels", "walls", "openings", "voids", "furniture"):
        ids = [x["id"] for x in model.get(collection, [])]
        if len(ids) != len(set(ids)):
            fails.append(f"duplicate {collection} IDs")
    # Resolve references before geometry checks so malformed external models return
    # diagnostics instead of exceptions from later spatial or door operations.
    for s in spaces:
        if s["level"] not in levels:
            fails.append(f"{s['id']}: unknown level")
    for w in model["walls"]:
        if w["level"] not in levels or any(i and i not in by_id for i in w["spaces"]):
            fails.append(f"{w['id']}: invalid level/space reference")
    for o in model["openings"]:
        if o["space_id"] not in by_id or (
            o["kind"] != "skylight" and o["wall_id"] not in walls
        ):
            fails.append(f"{o['id']}: invalid host/space reference")
    for v in model["voids"]:
        if v["level"] not in levels or v["space_id"] not in by_id:
            fails.append(f"{v['id']}: invalid void reference")
    for st in model["stairs"]:
        if (
            st["from_level"] not in levels
            or st["to_level"] not in levels
            or st["space_id"] not in by_id
        ):
            fails.append("invalid stair references")
    for f in model["furniture"]:
        if f["space_id"] not in by_id or f["level"] not in levels:
            fails.append(f"{f['id']}: invalid furniture reference")
    if fails:
        return {
            "status": "FAIL",
            "fail": fails,
            "warn": [],
            "ok": [],
            "metrics": {},
            "constraints": [],
            "disclaimer": DISCLAIMER,
        }
    for s in spaces:
        r = rs[s["id"]]
        if min(r.w, r.d) <= 0:
            fails.append(f"{s['id']}: non-positive dimensions")
        if s["level"] not in levels:
            fails.append(f"{s['id']}: unknown level")
            continue
        if not r.inside(fp, eps=TOL):
            fails.append(f"{s['id']}: outside footprint")
        if abs(r.area - s["area"]) > 0.02:
            fails.append(f"{s['id']}: stored area differs from geometry")
        for key, actual in [("min_width", min(r.w, r.d)), ("min_depth", max(r.w, r.d))]:
            if key in s and actual < s[key] - TOL:
                fails.append(f"{s['id']}: {key} {s[key]} m not met ({actual:.2f} m)")
        short = min(r.w, r.d)
        suggest = (
            1.4
            if s["zone"] == "service"
            else 0.9
            if s["zone"] == "circulation"
            else 2.4
        )
        if short < suggest - TOL and not s["open_to_sky"]:
            warns.append(
                f"{s['id']}: narrow dimension {short:.2f} m (< {suggest} m concept target)"
            )
        deviation = abs(r.area - s["target_area"]) / s["target_area"]
        if "max_area_deviation" in s and deviation > s["max_area_deviation"] + 0.002:
            fails.append(f"{s['id']}: hard area tolerance exceeded")
        elif deviation > 0.25 and not s["auto_generated"]:
            warns.append(
                f"{s['id']}: area {r.area:.1f} m² vs target {s['target_area']} m² ({deviation:.0%} deviation)"
            )
    for i, a in enumerate(spaces):
        for b in spaces[i + 1 :]:
            if a["level"] == b["level"] and rs[a["id"]].overlaps(rs[b["id"]], eps=TOL):
                fails.append(f"{a['id']} overlaps {b['id']}")
            if (
                a["level"] != b["level"]
                and not a["open_to_sky"]
                and not b["open_to_sky"]
            ):
                low, high = (
                    (a, b)
                    if bases.get(a["level"], 0) < bases.get(b["level"], 0)
                    else (b, a)
                )
                if bases[low["level"]] + low["ceiling_height"] > bases[
                    high["level"]
                ] + TOL and rs[low["id"]].overlaps(rs[high["id"]], eps=TOL):
                    fails.append(
                        f"{high['id']}: occupies vertical volume of {low['id']}"
                    )
    for v in model.get("voids", []):
        if v["level"] not in levels:
            fails.append(f"{v['id']}: unknown void level")
            continue
        for s in spaces:
            if s["level"] == v["level"] and rect(v["rect"]).overlaps(
                rs[s["id"]], eps=TOL
            ):
                fails.append(f"{s['id']}: intersects {v['kind']} void {v['id']}")
    for lv in levels:
        area = sum(s["area"] for s in spaces if s["level"] == lv)
        voidarea = sum(
            r.area
            for r in subtract_all(
                fp,
                [rect(v["rect"]) for v in model.get("voids", []) if v["level"] == lv],
            )
        )
        if abs(area - voidarea) > 0.05:
            fails.append(
                f"{lv}: spaces do not tile footprint minus voids ({area:.2f} vs {voidarea:.2f} m²)"
            )
    graph, roots = access_graph(model)
    seen = reachable(graph, roots)
    if not roots:
        fails.append("building has no exterior entrance")
    for s in spaces:
        if s["id"] not in seen:
            fails.append(f"{s['id']}: unreachable from exterior entrance")
    by_wall = defaultdict(list)
    glazed = set()
    for w in model["walls"]:
        if w["level"] not in levels:
            fails.append(f"{w['id']}: unknown level")
        if any(i and i not in by_id for i in w["spaces"]):
            fails.append(f"{w['id']}: invalid space references")
        if min(w["height"], w["thickness"]) <= 0:
            fails.append(f"{w['id']}: non-positive wall dimensions")
    for o in model["openings"]:
        if o["space_id"] not in by_id:
            fails.append(f"{o['id']}: invalid space reference")
            continue
        if o["kind"] == "skylight":
            s = by_id[o["space_id"]]
            if (
                o.get("roof_id") != f"roof-{s['id']}"
                or s["open_to_sky"]
                or "rect" not in o
            ):
                fails.append(f"{o['id']}: missing roof host/aperture")
                continue
            if not rect(o["rect"]).inside(rs[s["id"]], eps=TOL):
                fails.append(f"{o['id']}: aperture outside roof")
            for upper in spaces:
                if bases[upper["level"]] > bases[s["level"]] + TOL and rect(
                    o["rect"]
                ).overlaps(rs[upper["id"]], eps=TOL):
                    fails.append(f"{o['id']}: blocked by upper floor {upper['id']}")
            glazed.add(s["id"])
            continue
        w = walls.get(o["wall_id"])
        if not w:
            fails.append(f"{o['id']}: missing host wall")
            continue
        L = math.hypot(w["x2"] - w["x1"], w["y2"] - w["y1"])
        if (
            o["offset"] - o["width"] / 2 < -TOL
            or o["offset"] + o["width"] / 2 > L + TOL
        ):
            fails.append(f"{o['id']}: opening outside wall length")
        if o["sill"] < 0 or o["sill"] + o["height"] > w["height"] + TOL:
            fails.append(f"{o['id']}: opening outside wall height")
        for other in by_wall[o["wall_id"]]:
            if (
                min(o["offset"] + o["width"] / 2, other["offset"] + other["width"] / 2)
                > max(
                    o["offset"] - o["width"] / 2, other["offset"] - other["width"] / 2
                )
                + TOL
                and min(o["sill"] + o["height"], other["sill"] + other["height"])
                > max(o["sill"], other["sill"]) + TOL
            ):
                fails.append(f"{o['id']}: overlaps opening {other['id']}")
        by_wall[o["wall_id"]].append(o)
        if (o["kind"] == "window" or o.get("glazed")) and w["kind"] in (
            "exterior",
            "courtyard",
        ):
            glazed.update(i for i in w["spaces"] if i)
    adjacency = set()
    for w in model["walls"]:
        ids = [i for i in w["spaces"] if i]
        if len(ids) == 2 and math.hypot(w["x2"] - w["x1"], w["y2"] - w["y1"]) >= 0.9:
            adjacency.add(tuple(sorted(ids)))
    requested = {
        tuple(sorted((s["id"], a))) for s in spaces for a in s.get("adjacent_to", [])
    }
    for pair in requested - adjacency:
        warns.append(f"{pair[0]} ↔ {pair[1]}: preferred adjacency not realized")
    for s in spaces:
        if (
            s["type"] in ("room", "kitchen")
            and not s["open_to_sky"]
            and s["id"] not in glazed
        ):
            warns.append(
                f"{s['id']}: no exterior/courtyard glazing or skylight (daylight proxy)"
            )
        if s.get("requires_exterior_wall") and not any(
            s["id"] in w["spaces"] and w["kind"] in ("exterior", "courtyard")
            for w in model["walls"]
        ):
            fails.append(f"{s['id']}: requires exterior/courtyard wall")
        if s["zone"] == "private":
            blocked = [
                x["id"] for x in spaces if x["zone"] == "private" and x["id"] != s["id"]
            ]
            if s["id"] not in reachable(graph, roots, blocked):
                warns.append(f"{s['id']}: access crosses another private room")
    outcomes = []
    for c in model.get("constraints", []):
        kind = c["type"]
        ids = c.get("spaces", [])
        target = c.get("target")
        met = True
        if kind == "adjacency":
            met = tuple(sorted(ids)) in adjacency
        elif kind == "daylight":
            met = target in glazed
        elif kind == "skylight":
            met = any(
                o["kind"] == "skylight" and o["space_id"] == target
                for o in model["openings"]
            )
        elif kind == "max_footprint":
            met = fp.area <= c["value"] + TOL
        elif kind == "privacy":
            targets = ids or (
                [target]
                if target
                else [s["id"] for s in spaces if s["zone"] == "private"]
            )
            met = all(
                sid
                in reachable(
                    graph,
                    roots,
                    [
                        x["id"]
                        for x in spaces
                        if x["zone"] == "private" and x["id"] != sid
                    ],
                )
                for sid in targets
            )
        elif kind == "wet_grouping":
            met = all(tuple(sorted((a, b))) in adjacency for a, b in zip(ids, ids[1:]))
        elif kind == "wet_stacking":
            met = all(
                rs[a].overlaps(rs[b]) and by_id[a]["level"] != by_id[b]["level"]
                for a, b in zip(ids, ids[1:])
            )
        outcomes.append(
            {
                "type": kind,
                "spaces": ids,
                "target": target,
                "required": c.get("required", False),
                "met": met,
            }
        )
        if not met:
            (fails if c.get("required") else warns).append(
                f"{kind}: {'/'.join(ids) or target or 'building'} constraint not met"
            )
    groups = defaultdict(list)
    for s in spaces:
        if s.get("open_plan_group"):
            groups[s["open_plan_group"]].append(s["id"])
    passages = defaultdict(set)
    for o in model["openings"]:
        if o["kind"] == "passage":
            a, b = walls[o["wall_id"]]["spaces"]
            if a and b:
                passages[a].add(b)
                passages[b].add(a)
    for group, ids in groups.items():
        if not set(ids) <= reachable(passages, {ids[0]}):
            warns.append(
                f"open-plan group {group}: members not connected by open passages"
            )
    for lv in list(levels)[1:]:
        if not any(st["to_level"] == lv for st in model.get("stairs", [])):
            fails.append(f"{lv}: no stair arriving from level below")
    for st in model.get("stairs", []):
        stair_rect = rect(st["rect"])
        host_rect = rs[st["space_id"]]
        physical_fit = (
            min(stair_rect.w, stair_rect.d) >= 2.1 - TOL
            and max(stair_rect.w, stair_rect.d)
            >= st["flight_run"] + 2 * st["landing_depth"] - TOL
        )
        if not stair_rect.inside(host_rect, eps=TOL) or not physical_fit:
            fails.append(f"{st['space_id']}: stair geometry does not fit host space")
        rise = bases[st["to_level"]] - bases[st["from_level"]]
        if abs(st["risers"] * st["riser_mm"] / 1000 - rise) > 0.002 or st["risers"] % 2:
            fails.append(
                f"{st['space_id']}: riser math does not match connected levels"
            )
        if (
            abs(st["flight_run"] - (st["risers"] // 2 - 1) * st["going_mm"] / 1000)
            > 0.002
        ):
            fails.append(f"{st['space_id']}: tread math differs from flight geometry")
        if st["going_mm"] < 250:
            warns.append(f"{st['space_id']}: going below 250 mm concept target")
        if not st["fits"]:
            fails.append(f"{st['space_id']}: U-stair flights and landings do not fit")
        if st["from_level"] not in levels or st["to_level"] not in levels:
            fails.append(f"{st['space_id']}: invalid stair level connection")
            continue
        if f"landing-{st['space_id']}" not in by_id:
            fails.append(f"{st['space_id']}: no upper landing")
        if not any(
            v["kind"] == "stair" and v["space_id"] == st["space_id"]
            for v in model.get("voids", [])
        ):
            fails.append(f"{st['space_id']}: missing shaft opening")
        if not 150 <= st["riser_mm"] <= 190:
            warns.append(
                f"{st['space_id']}: riser {st['riser_mm']} mm outside concept range"
            )
    for f in model.get("furniture", []):
        s = by_id.get(f["space_id"])
        fr = rect(f["rect"])
        margin = f["clearance"]
        clearance = Rect(
            fr.x - margin, fr.y - margin, fr.w + margin * 2, fr.d + margin * 2
        )
        if not s or not clearance.inside(rs[s["id"]], eps=TOL):
            (fails if f.get("required") else warns).append(
                f"{f['id']}: furniture/clearance does not fit room"
            )
        for other in model.get("furniture", []):
            if (
                other["id"] > f["id"]
                and other["space_id"] == f["space_id"]
                and clearance.overlaps(rect(other["rect"]))
            ):
                (fails if f.get("required") or other.get("required") else warns).append(
                    f"{f['id']}: clearance conflicts with {other['id']}"
                )
    for furniture in model.get("furniture", []):
        footprint = rect(furniture["rect"])
        for opening in model["openings"]:
            if (
                opening["kind"] not in ("door", "entrance")
                or opening["space_id"] != furniture["space_id"]
            ):
                continue
            h, c, l = door_points(model, opening)
            sweep = Rect(
                min(h[0], c[0], l[0]),
                min(h[1], c[1], l[1]),
                max(h[0], c[0], l[0]) - min(h[0], c[0], l[0]),
                max(h[1], c[1], l[1]) - min(h[1], c[1], l[1]),
            )
            if footprint.overlaps(sweep, eps=TOL):
                (fails if furniture.get("required") else warns).append(
                    f"{furniture['id']}: conflicts with door swing {opening['id']}"
                )
    for s in spaces:
        if s["zone"] != "circulation":
            continue
        hall_neighbors = [
            i
            for i in graph[s["id"]]
            if i in by_id and by_id[i]["zone"] == "circulation"
        ]
        public_outlet = any(
            i in by_id and (by_id[i]["zone"] == "public" or by_id[i]["open_to_sky"])
            for i in graph[s["id"]]
        )
        if (
            len(hall_neighbors) <= 1
            and not public_outlet
            and max(rs[s["id"]].w, rs[s["id"]].d) > 3
        ):
            warns.append(
                f"{s['id']}: potential circulation dead end over 3 m (concept proxy)"
            )
    from ..building_model.materials import resolve_material

    for owner, assignments in [("building", model.get("materials", {}))] + [
        (s["id"], s.get("materials", {})) for s in spaces
    ]:
        for surface, assignment in assignments.items():
            try:
                mat = resolve_material(assignment)
                if mat.specified_as:
                    warns.append(
                        f"{owner}/{surface}: unknown material {mat.specified_as!r}; neutral fallback used"
                    )
            except SpecError as e:
                fails.append(f"{owner}/{surface}: {e}")
    metrics = {
        "enclosed_area_m2": round(
            sum(s["area"] for s in spaces if not s["open_to_sky"]), 2
        ),
        "circulation_area_m2": round(
            sum(s["area"] for s in spaces if s["zone"] == "circulation"), 2
        ),
        "footprint_m2": round(fp.area, 2),
        "adjacency_realized": len(requested & adjacency),
        "adjacency_requested": len(requested),
        "daylit_rooms": sum(
            s["id"] in glazed
            for s in spaces
            if s["type"] in ("room", "kitchen") and not s["open_to_sky"]
        ),
        "habitable_rooms": sum(
            s["type"] in ("room", "kitchen") and not s["open_to_sky"] for s in spaces
        ),
        "area_deviation_mean": round(
            sum(
                abs(s["area"] - s["target_area"]) / s["target_area"]
                for s in spaces
                if not s["auto_generated"]
            )
            / max(1, sum(not s["auto_generated"] for s in spaces)),
            4,
        ),
        "reachable_spaces": len(seen),
    }
    oks.append(
        f"{len(spaces)} spaces, {len(walls)} walls, {len(model['openings'])} openings"
    )
    return {
        "status": "FAIL" if fails else "PASS",
        "fail": list(dict.fromkeys(fails)),
        "warn": list(dict.fromkeys(warns)),
        "ok": oks,
        "metrics": metrics,
        "constraints": outcomes,
        "disclaimer": DISCLAIMER,
    }
