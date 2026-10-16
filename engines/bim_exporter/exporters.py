"""One geometric compilation for GLB, WebGL, Blender, and IFC."""

from __future__ import annotations
import hashlib
import json
import struct
from ..building_model.model import Rect, Wall
from ..building_model.geometry import (
    rect,
    subtract_all,
    level_bases,
    surface_parts,
    door_points,
)
from ..building_model.materials import material_for_surface, resolve_material


def _mat_fields(mat):
    m = mat.to_dict()
    return {
        "material": m["id"],
        "material_name": m["name"],
        "color": m["color"],
        "roughness": m["roughness"],
        "metalness": m["metalness"],
        "pattern": m["pattern"].get("type", "flat"),
        "pattern_settings": m["pattern"],
        "finish": m["finish"],
    }


def roof_parts(model, space):
    if space["open_to_sky"]:
        return []
    bases = level_bases(model)
    z = bases[space["level"]]
    # A roof is only exposed where no occupied floor exists above this space.
    cuts = [rect(s["rect"]) for s in model["spaces"] if bases[s["level"]] > z + 0.002]
    # An active stair shaft continues to its destination storey, never capped below it.
    cuts += [
        rect(st["rect"]) for st in model["stairs"] if st["space_id"] == space["id"]
    ]
    return [
        part
        for r in surface_parts(model, space, "roof")
        for part in subtract_all(r, cuts)
    ]


def wall_boxes(model):
    boxes = []
    bases = level_bases(model)
    by_id = {s["id"]: s for s in model["spaces"]}
    ops = {}

    def box(name, kind, space, level, center, size, mat, **extra):
        if min(size) <= 1e-7:
            return
        identity = f"{kind}|{name}|{len(boxes)}"
        boxes.append(
            {
                "id": hashlib.sha1(identity.encode()).hexdigest()[:16],
                "name": name,
                "kind": kind,
                "space": space,
                "level": level,
                "center": list(center),
                "size": list(size),
                **_mat_fields(mat),
                **extra,
            }
        )

    for o in model["openings"]:
        if o["wall_id"]:
            ops.setdefault(o["wall_id"], []).append(o)
    for w in model["walls"]:
        wo = Wall(w["id"], w["level"], w["x1"], w["y1"], w["x2"], w["y2"])
        z = bases[w["level"]]
        apertures = [
            Rect(o["offset"] - o["width"] / 2, o["sill"], o["width"], o["height"])
            for o in ops.get(w["id"], [])
        ]
        pieces = subtract_all(Rect(0, 0, wo.length, w["height"]), apertures)
        surf = "interior_wall" if w["kind"] == "interior" else "exterior_wall"
        core = material_for_surface(model, surf)
        if core.pattern.get("type") == "slat":
            core = resolve_material("lime_plaster")
        for i, p in enumerate(pieces):
            px, py = wo.point_at(p.cx)
            size = (
                [w["thickness"], p.w, p.d]
                if wo.vertical
                else [p.w, w["thickness"], p.d]
            )
            box(
                w["id"],
                "wall",
                next((s for s in w["spaces"] if s), None),
                w["level"],
                [px, py, z + p.cy],
                size,
                core,
                host_id=w["id"],
            )
        # Finishes are layers on wall faces; a slat assignment never deletes the core.
        finishes = []
        for sid in w["spaces"]:
            s = by_id.get(sid)
            if not s or s["open_to_sky"]:
                continue
            material = s.get("materials", {}).get("wall")
            if material:
                sr = rect(s["rect"])
                sign = (
                    1 if (sr.cx > w["x1"] if wo.vertical else sr.cy > w["y1"]) else -1
                )
                finishes.append((sid, sign, resolve_material(material)))
        exterior = material_for_surface(model, surf)
        if exterior.pattern.get("type") == "slat":
            s = next(
                (by_id[i] for i in w["spaces"] if i and not by_id[i]["open_to_sky"]),
                None,
            )
            sr = rect(s["rect"])
            sign = -1 if (sr.cx > w["x1"] if wo.vertical else sr.cy > w["y1"]) else 1
            finishes.append((s["id"], sign, exterior))
        for sid, sign, mat in finishes:
            slat = mat.pattern.get("type") == "slat"
            thick = mat.pattern.get("slat_depth_m", 0.04) if slat else 0.012
            step = mat.pattern.get("slat_width_m", 0.09) + mat.pattern.get(
                "gap_m", 0.02
            )
            for p in pieces:
                segments = []
                if slat:
                    cur = p.x
                    while cur < p.x2 - 1e-6:
                        segments.append(
                            (
                                cur,
                                min(cur + mat.pattern.get("slat_width_m", 0.09), p.x2),
                            )
                        )
                        cur += step
                else:
                    segments = [(p.x, p.x2)]
                for lo, hi in segments:
                    px, py = wo.point_at((lo + hi) / 2)
                    offset = sign * (w["thickness"] + thick) / 2
                    px += offset if wo.vertical else 0
                    py += 0 if wo.vertical else offset
                    size = (
                        [thick, hi - lo, p.d] if wo.vertical else [hi - lo, thick, p.d]
                    )
                    box(
                        w["id"],
                        "finish",
                        sid,
                        w["level"],
                        [px, py, z + p.cy],
                        size,
                        mat,
                        host_id=w["id"],
                    )
        frame = resolve_material("oak")
        for o in ops.get(w["id"], []):
            px, py = wo.point_at(o["offset"])
            oz = z + o["sill"]
            depth = 0.045
            if o["kind"] == "window" or o.get("glazed"):
                size = (
                    [depth, o["width"], o["height"]]
                    if wo.vertical
                    else [o["width"], depth, o["height"]]
                )
                box(
                    o["id"],
                    "glass",
                    o["space_id"],
                    w["level"],
                    [px, py, oz + o["height"] / 2],
                    size,
                    resolve_material("glass"),
                    host_id=o["id"],
                )
            if o["kind"] == "passage":
                continue
            for off in [-o["width"] / 2 + 0.025, o["width"] / 2 - 0.025]:
                fx, fy = wo.point_at(o["offset"] + off)
                size = (
                    [w["thickness"] + 0.035, 0.05, o["height"]]
                    if wo.vertical
                    else [0.05, w["thickness"] + 0.035, o["height"]]
                )
                box(
                    o["id"],
                    "frame",
                    o["space_id"],
                    w["level"],
                    [fx, fy, oz + o["height"] / 2],
                    size,
                    frame,
                    host_id=o["id"],
                )
            size = (
                [w["thickness"] + 0.035, o["width"], 0.05]
                if wo.vertical
                else [o["width"], w["thickness"] + 0.035, 0.05]
            )
            box(
                o["id"],
                "frame",
                o["space_id"],
                w["level"],
                [px, py, oz + o["height"] - 0.025],
                size,
                frame,
                host_id=o["id"],
            )
            if o["kind"] == "window":
                box(
                    o["id"],
                    "frame",
                    o["space_id"],
                    w["level"],
                    [px, py, oz + 0.025],
                    size,
                    frame,
                    host_id=o["id"],
                )
            elif not o.get("glazed"):
                # Open door leaf, hinged at the low-offset jamb, perpendicular to wall.
                hinge, closed, leaf = door_points(model, o)
                size = (
                    [o["width"], 0.04, o["height"] - 0.05]
                    if wo.vertical
                    else [0.04, o["width"], o["height"] - 0.05]
                )
                cx, cy = (hinge[0] + leaf[0]) / 2, (hinge[1] + leaf[1]) / 2
                box(
                    o["id"],
                    "door",
                    o["space_id"],
                    w["level"],
                    [cx, cy, oz + (o["height"] - 0.05) / 2],
                    size,
                    frame,
                    host_id=o["id"],
                )
    for s in model["spaces"]:
        z = bases[s["level"]]
        r = rect(s["rect"])
        kind = "courtyard" if s["open_to_sky"] else "floor"
        for part in surface_parts(model, s, "floor"):
            box(
                f"slab-{s['id']}",
                kind,
                s["id"],
                s["level"],
                [part.cx, part.cy, z - 0.09],
                [part.w, part.d, 0.18],
                material_for_surface(
                    model, "courtyard" if s["open_to_sky"] else "floor", s
                ),
                host_id=s["id"],
            )
        for part in roof_parts(model, s):
            mat = material_for_surface(model, "roof")
            rz = z + s["ceiling_height"] + 0.08
            box(
                f"roof-{s['id']}",
                "roof",
                s["id"],
                s["level"],
                [part.cx, part.cy, rz],
                [part.w, part.d, 0.16],
                mat,
                host_id=f"roof-{s['id']}",
            )
            if mat.pattern.get("type") == "standing_seam":
                step = mat.pattern.get("seam_spacing_m", 0.45)
                sh = mat.pattern.get("seam_height_m", 0.025)
                x = part.x + step
                while x < part.x2 - 0.05:
                    box(
                        f"seam-{s['id']}",
                        "seam",
                        s["id"],
                        s["level"],
                        [x, part.cy, rz + 0.08 + sh / 2],
                        [0.03, part.d, sh],
                        mat,
                        host_id=f"roof-{s['id']}",
                    )
                    x += step
        if model.get("roof", {}).get("form") == "flat with parapet":
            for wall in model["walls"]:
                if wall["kind"] != "exterior" or s["id"] not in wall["spaces"]:
                    continue
                vertical = abs(wall["x1"] - wall["x2"]) < 1e-6
                for part in roof_parts(model, s):
                    fixed = wall["x1"] if vertical else wall["y1"]
                    if (
                        min(
                            abs(fixed - (part.x if vertical else part.y)),
                            abs(fixed - (part.x2 if vertical else part.y2)),
                        )
                        > 0.002
                    ):
                        continue
                    lo = max(
                        min(wall["y1"], wall["y2"])
                        if vertical
                        else min(wall["x1"], wall["x2"]),
                        part.y if vertical else part.x,
                    )
                    hi = min(
                        max(wall["y1"], wall["y2"])
                        if vertical
                        else max(wall["x1"], wall["x2"]),
                        part.y2 if vertical else part.x2,
                    )
                    if hi - lo < 0.01:
                        continue
                    center = (
                        [fixed, (lo + hi) / 2, z + s["ceiling_height"] + 0.16 + 0.225]
                        if vertical
                        else [
                            (lo + hi) / 2,
                            fixed,
                            z + s["ceiling_height"] + 0.16 + 0.225,
                        ]
                    )
                    size = [0.12, hi - lo, 0.45] if vertical else [hi - lo, 0.12, 0.45]
                    box(
                        f"parapet-{s['id']}",
                        "roof",
                        s["id"],
                        s["level"],
                        center,
                        size,
                        material_for_surface(model, "exterior_wall"),
                        host_id=f"roof-{s['id']}",
                    )
        if s["skylight"]:
            for o in model["openings"]:
                if o["kind"] == "skylight" and o["space_id"] == s["id"]:
                    aperture = rect(o["rect"])
                    rz = z + s["ceiling_height"] + 0.17
                    box(
                        o["id"],
                        "glass",
                        s["id"],
                        s["level"],
                        [aperture.cx, aperture.cy, rz],
                        [aperture.w, aperture.d, 0.035],
                        resolve_material("glass"),
                        host_id=o["id"],
                    )
                    for a in [
                        Rect(
                            aperture.x - 0.04,
                            aperture.y - 0.04,
                            aperture.w + 0.08,
                            0.04,
                        ),
                        Rect(aperture.x - 0.04, aperture.y2, aperture.w + 0.08, 0.04),
                        Rect(aperture.x - 0.04, aperture.y, 0.04, aperture.d),
                        Rect(aperture.x2, aperture.y, 0.04, aperture.d),
                    ]:
                        box(
                            o["id"],
                            "frame",
                            s["id"],
                            s["level"],
                            [a.cx, a.cy, rz],
                            [a.w, a.d, 0.08],
                            resolve_material("stainless_steel"),
                            host_id=o["id"],
                        )
    for st in model["stairs"]:
        r = rect(st["rect"])
        z = bases[st["from_level"]]
        rise = bases[st["to_level"]] - z
        n = st["risers"]
        axis = st["axis"]
        width = (r.w if axis == "y" else r.d) / 2
        low = st["landing_at"] == "low"
        length = r.d if axis == "y" else r.w
        start = r.y if axis == "y" else r.x
        # Equal flights: n/2 risers per flight, n/2-1 treads, then a landing.
        going = st["going_mm"] / 1000
        per_flight = n // 2 - 1
        flight_run = per_flight * going
        for flight in range(2):
            for j in range(per_flight):
                along = (
                    st["landing_depth"] + (j + 0.5) * going
                    if flight == 0
                    else st["landing_depth"] + flight_run - (j + 0.5) * going
                )
                if not low:
                    along = length - along
                a = start + along
                b = (r.x if axis == "y" else r.y) + (
                    width / 2 if flight == 0 else width * 1.5
                )
                step = j + 1 if flight == 0 else n // 2 + j + 1
                center = (
                    [b, a, z + rise * step / n - 0.025]
                    if axis == "y"
                    else [a, b, z + rise * step / n - 0.025]
                )
                size = (
                    [width - 0.04, going, 0.05]
                    if axis == "y"
                    else [going, width - 0.04, 0.05]
                )
                box(
                    f"tread-{st['space_id']}-{flight}-{j}",
                    "stair",
                    st["space_id"],
                    st["from_level"],
                    center,
                    size,
                    material_for_surface(model, "floor", by_id[st["space_id"]]),
                    host_id=st["space_id"],
                )
        turn_depth = length - st["landing_depth"] - flight_run
        turn = start + length - turn_depth / 2 if low else start + turn_depth / 2
        center = (
            [r.cx, turn, z + rise / 2 - 0.05]
            if axis == "y"
            else [turn, r.cy, z + rise / 2 - 0.05]
        )
        size = [r.w, turn_depth, 0.1] if axis == "y" else [turn_depth, r.d, 0.1]
        box(
            f"turn-{st['space_id']}",
            "stair",
            st["space_id"],
            st["from_level"],
            center,
            size,
            material_for_surface(model, "floor"),
            host_id=st["space_id"],
        )
        # Roof above shaft at the destination storey, leaving the lower opening clear.
        lv = next(l for l in model["levels"] if l["id"] == st["to_level"])
        shaft = rect(st["shaft_rect"])
        box(
            f"roof-shaft-{st['space_id']}",
            "roof",
            st["space_id"],
            st["to_level"],
            [shaft.cx, shaft.cy, lv["elevation"] + lv["height"] + 0.08],
            [shaft.w, shaft.d, 0.16],
            material_for_surface(model, "roof"),
            host_id=f"roof-shaft-{st['space_id']}",
        )
    for f in model.get("furniture", []):
        r = rect(f["rect"])
        box(
            f["id"],
            "furniture",
            f["space_id"],
            f["level"],
            [r.cx, r.cy, bases[f["level"]] + f["height"] / 2],
            [r.w, r.d, f["height"]],
            resolve_material("oak"),
            host_id=f["id"],
        )
    return boxes


_CUBE = [
    (-0.5, -0.5, -0.5),
    (0.5, -0.5, -0.5),
    (0.5, 0.5, -0.5),
    (-0.5, 0.5, -0.5),
    (-0.5, -0.5, 0.5),
    (0.5, -0.5, 0.5),
    (0.5, 0.5, 0.5),
    (-0.5, 0.5, 0.5),
]
_FACES = [
    (0, 2, 1),
    (0, 3, 2),
    (4, 5, 6),
    (4, 6, 7),
    (0, 5, 4),
    (0, 1, 5),
    (1, 6, 5),
    (1, 2, 6),
    (2, 7, 6),
    (2, 3, 7),
    (3, 4, 7),
    (3, 0, 4),
]


def export_glb(model, path):
    boxes = wall_boxes(model)
    mats = []
    mat_ids = {}
    nodes = []
    meshes = []
    accessors = []
    views = []
    parts = []
    offset = 0
    for b in boxes:
        key = json.dumps([b["material"], b["color"], b["roughness"], b["metalness"]])
        if key not in mat_ids:
            mat_ids[key] = len(mats)
            mats.append(
                {
                    "name": b["material_name"],
                    "pbrMetallicRoughness": {
                        "baseColorFactor": b["color"],
                        "roughnessFactor": b["roughness"],
                        "metallicFactor": b["metalness"],
                    },
                    "alphaMode": "BLEND" if b["color"][3] < 1 else "OPAQUE",
                }
            )
        # Separate vertices per face keep architectural edges sharp.
        positions = []
        normals = []
        indices = []
        for tri in _FACES:
            a, c, d = [_CUBE[i] for i in tri]
            u = [c[i] - a[i] for i in range(3)]
            v = [d[i] - a[i] for i in range(3)]
            normal = [
                u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0],
            ]
            for i in tri:
                x, y, z = [
                    b["center"][k] + _CUBE[i][k] * b["size"][k] for k in range(3)
                ]
                positions.append([x, z, -y])
                normals.append([normal[0], normal[2], -normal[1]])
                indices.append(len(indices))
        attrs = {}
        for name, values in [("POSITION", positions), ("NORMAL", normals)]:
            data = b"".join(struct.pack("<fff", *v) for v in values)
            views.append(
                {
                    "buffer": 0,
                    "byteOffset": offset,
                    "byteLength": len(data),
                    "target": 34962,
                }
            )
            parts.append(data)
            offset += len(data)
            acc = {
                "bufferView": len(views) - 1,
                "componentType": 5126,
                "count": len(values),
                "type": "VEC3",
            }
            if name == "POSITION":
                acc.update(
                    {
                        "min": [min(v[k] for v in values) for k in range(3)],
                        "max": [max(v[k] for v in values) for k in range(3)],
                    }
                )
            accessors.append(acc)
            attrs[name] = len(accessors) - 1
        data = struct.pack("<" + "H" * len(indices), *indices)
        views.append(
            {
                "buffer": 0,
                "byteOffset": offset,
                "byteLength": len(data),
                "target": 34963,
            }
        )
        parts.append(data)
        offset += len(data)
        accessors.append(
            {
                "bufferView": len(views) - 1,
                "componentType": 5123,
                "count": len(indices),
                "type": "SCALAR",
            }
        )
        meshes.append(
            {
                "primitives": [
                    {
                        "attributes": attrs,
                        "indices": len(accessors) - 1,
                        "material": mat_ids[key],
                    }
                ]
            }
        )
        nodes.append(
            {
                "mesh": len(meshes) - 1,
                "name": f"{b['kind']}:{b['name']}",
                "extras": {
                    "id": b["id"],
                    "space_id": b["space"],
                    "level": b["level"],
                    "host_id": b.get("host_id"),
                },
            }
        )
    binary = b"".join(parts)
    gltf = {
        "asset": {
            "version": "2.0",
            "generator": "architect-skill 2.0",
            "copyright": model["meta"]["disclaimer"],
        },
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": mats,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
    }
    data = json.dumps(gltf).encode()
    data += b" " * ((-len(data)) % 4)
    binary += b"\0" * ((-len(binary)) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 28 + len(data) + len(binary)))
        f.write(struct.pack("<II", len(data), 0x4E4F534A))
        f.write(data)
        f.write(struct.pack("<II", len(binary), 0x004E4942))
        f.write(binary)
    return len(boxes)


def export_ifc(model, path):
    from .ifc import write_ifc

    return write_ifc(model, path)
