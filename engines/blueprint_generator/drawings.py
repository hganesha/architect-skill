"""Model-derived concept drawings and dimensioned CAD handoff."""

from __future__ import annotations
import csv
import io
import math
from datetime import date
from html import escape
from ..building_model.model import Wall
from ..building_model.geometry import rect, level_bases, door_points
from ..bim_exporter.exporters import wall_boxes, roof_parts

INK = "#1a2332"
PAPER = "#faf8f3"
ACCENT = "#a35529"


class SVG:
    def __init__(self, w, h, title, subtitle=""):
        self.w, self.h = w, h
        self.p = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="Arial,sans-serif">',
            f'<rect width="{w}" height="{h}" fill="{PAPER}"/>',
            f'<text x="28" y="34" font-size="19" fill="{INK}" font-weight="bold">{escape(title)}</text>',
            f'<text x="28" y="55" font-size="11" fill="#596371">{escape(subtitle)}</text>',
        ]

    def add(self, s):
        self.p.append(s)

    def done(self):
        self.add(
            f'<line x1="28" y1="{self.h - 51}" x2="{self.w - 28}" y2="{self.h - 51}" stroke="#aaa"/>'
        )
        self.add(
            f'<text x="28" y="{self.h - 33}" font-size="10" fill="{ACCENT}">CONCEPT DESIGN — NOT FOR CONSTRUCTION · Licensed professional review required · {date.today().isoformat()}</text>'
        )
        self.add(
            f'<text x="28" y="{self.h - 16}" font-size="9" fill="{INK}">Dimensions in metres from model geometry · Scale bar governs; scaling changes with print size</text></svg>'
        )
        return "\n".join(self.p)


def _project(model, W=1200, H=900, pad=110):
    fp = rect(model["site"]["footprint"])
    sc = min((W - 2 * pad - 240) / fp.w, (H - 2 * pad - 90) / fp.d)
    ox = pad - fp.x * sc
    oy = H - pad - 70 + fp.y * sc
    return lambda x, y: (ox + x * sc, oy - y * sc), sc


def _rect_svg(svg, P, r, fill, stroke=INK, width=1):
    x, y = P(r.x, r.y2)
    x2, y2 = P(r.x2, r.y)
    svg.add(
        f'<rect x="{x:.3f}" y="{y:.3f}" width="{x2 - x:.3f}" height="{y2 - y:.3f}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'
    )


def _dimension(svg, a, b, text, vertical=False):
    ax, ay = a
    bx, by = b
    svg.add(
        f'<path d="M {ax:.2f} {ay:.2f} L {bx:.2f} {by:.2f}" stroke="{INK}" stroke-width=".7"/>'
    )
    for x, y in (a, b):
        svg.add(
            f'<path d="M {x - 3:.2f} {y + 3:.2f} l 6 -6" stroke="{INK}" stroke-width=".8"/>'
        )
    x, y = (ax + bx) / 2, (ay + by) / 2
    transform = f' transform="rotate(-90 {x - 5} {y})"' if vertical else ""
    svg.add(
        f'<text x="{x - 5 if vertical else x:.2f}" y="{y if vertical else y - 5:.2f}" text-anchor="middle" font-size="9" fill="{INK}"{transform}>{escape(text)}</text>'
    )


def _door_geometry(model, o):
    return door_points(model, o)


def floor_plan(model, level_id=None):
    level_id = level_id or model["levels"][0]["id"]
    lv = next(l for l in model["levels"] if l["id"] == level_id)
    svg = SVG(
        1200,
        900,
        f"{model['meta']['name']} — Floor plan · {level_id}",
        f"Variant {model['meta']['variant'] + 1}: {model['meta']['variant_name']} · elevation {lv['elevation']:.2f} m",
    )
    P, sc = _project(model)
    fp = rect(model["site"]["footprint"])
    spaces = [s for s in model["spaces"] if s["level"] == level_id]
    labels = []
    palette = {
        "public": "#f0e1c9",
        "private": "#dce6d6",
        "service": "#e3ddef",
        "circulation": "#f5edde",
        "outdoor": "#cbded2",
    }
    for i, s in enumerate(spaces):
        r = rect(s["rect"])
        _rect_svg(svg, P, r, palette[s["zone"]], "none")
        cx, cy = P(r.cx, r.cy)
        label = (
            s["name"]
            if min(r.w, r.d) * sc > 50 and len(s["name"]) * 5 < r.w * sc
            else str(i + 1)
        )
        labels.append(
            f'<text x="{cx:.2f}" y="{cy - 12:.2f}" text-anchor="middle" font-size="10" fill="{INK}">{escape(label)}</text>'
        )
        if min(r.w, r.d) * sc > 55:
            labels.append(
                f'<text x="{cx:.2f}" y="{cy + 2:.2f}" text-anchor="middle" font-size="8" fill="#53616d">{s["area"]:.1f} m² / {s["area"] * 10.7639:.0f} ft²</text>'
            )
            labels.append(
                f'<text x="{cx:.2f}" y="{cy + 15:.2f}" text-anchor="middle" font-size="8" fill="#53616d">{r.w:.2f} × {r.d:.2f} m</text>'
            )
        svg.add(
            f'<text x="955" y="{100 + i * 19}" font-size="9" fill="{INK}">{i + 1}. {escape(s["name"])} · {s["area"]:.1f} m²</text>'
        )
    # Cut the very same wall solids shown in 3D at a horizontal plan plane.
    cut = lv["elevation"] + min(1.1, lv["height"] / 2)
    for b in wall_boxes(model):
        if (
            b["level"] == level_id
            and b["kind"] == "wall"
            and b["center"][2] - b["size"][2] / 2 - 1e-6
            <= cut
            <= b["center"][2] + b["size"][2] / 2 + 1e-6
        ):
            _rect_svg(
                svg,
                P,
                rect(
                    {
                        "x": b["center"][0] - b["size"][0] / 2,
                        "y": b["center"][1] - b["size"][1] / 2,
                        "w": b["size"][0],
                        "d": b["size"][1],
                    }
                ),
                INK,
                "none",
            )
    walls = {w["id"]: w for w in model["walls"]}
    for o in model["openings"]:
        if o["kind"] == "skylight":
            if any(s["id"] == o["space_id"] for s in spaces):
                _rect_svg(svg, P, rect(o["rect"]), "none", "#548aa0", 1)
            continue
        w = walls[o["wall_id"]]
        if w["level"] != level_id:
            continue
        wo = Wall(w["id"], w["level"], w["x1"], w["y1"], w["x2"], w["y2"])
        if o["kind"] == "window":
            a = P(*wo.point_at(o["offset"] - o["width"] / 2))
            b = P(*wo.point_at(o["offset"] + o["width"] / 2))
            svg.add(
                f'<path d="M {a[0]} {a[1]} L {b[0]} {b[1]}" stroke="#4d7f9b" stroke-width="1.5"/>'
            )
        elif o["kind"] != "passage":
            hinge, closed, leaf = [P(*v) for v in _door_geometry(model, o)]
            v = (closed[0] - hinge[0], closed[1] - hinge[1])
            u = (leaf[0] - hinge[0], leaf[1] - hinge[1])
            sweep = int(v[0] * u[1] - v[1] * u[0] > 0)
            radius = o["width"] * sc
            svg.add(
                f'<path d="M {hinge[0]} {hinge[1]} L {leaf[0]} {leaf[1]} M {closed[0]} {closed[1]} A {radius} {radius} 0 0 {sweep} {leaf[0]} {leaf[1]}" fill="none" stroke="{INK}" stroke-width=".8"/>'
            )
    for f in model.get("furniture", []):
        if f["level"] == level_id:
            _rect_svg(svg, P, rect(f["rect"]), "#cbb89d", "#82725f", 0.7)
    for st in model["stairs"]:
        if st["from_level"] == level_id or st["to_level"] == level_id:
            r = rect(st["rect"])
            _rect_svg(svg, P, r, "none", "#7b6652", 0.7)
            for b in wall_boxes(model):
                if b["kind"] == "stair" and b.get("host_id") == st["space_id"]:
                    rr = rect(
                        {
                            "x": b["center"][0] - b["size"][0] / 2,
                            "y": b["center"][1] - b["size"][1] / 2,
                            "w": b["size"][0],
                            "d": b["size"][1],
                        }
                    )
                    _rect_svg(svg, P, rr, "none", "#8f7960", 0.4)
            cx, cy = P(r.cx, r.cy)
            svg.add(
                f'<text x="{cx}" y="{cy}" font-size="9" text-anchor="middle">UP ↑ · {st["risers"]} risers</text>'
            )
    svg.p.extend(labels)
    x0, yt = P(fp.x, fp.y2)
    x1, yb = P(fp.x2, fp.y)
    _dimension(svg, (x0, yt - 40), (x1, yt - 40), f"{fp.w:.2f} m")
    _dimension(svg, (x0 - 45, yt), (x0 - 45, yb), f"{fp.d:.2f} m", True)
    # Dimension chain of rooms touching the south boundary.
    cuts = sorted(
        {
            round(x, 5)
            for s in spaces
            if abs(s["rect"]["y"] - fp.y) < 0.002
            for x in (s["rect"]["x"], s["rect"]["x"] + s["rect"]["w"])
        }
    )
    for a, b in zip(cuts, cuts[1:]):
        if (b - a) * sc > 28:
            _dimension(
                svg, (P(a, fp.y)[0], yb + 22), (P(b, fp.y)[0], yb + 22), f"{b - a:.2f}"
            )
    section = model.get("drawing", {}).get("section", {})
    axis = section.get("axis", "x")
    court = next((s for s in spaces if s["open_to_sky"]), None)
    position = section.get(
        "position",
        rect(court["rect"]).cy
        if court and axis == "x"
        else rect(court["rect"]).cx
        if court
        else fp.cy
        if axis == "x"
        else fp.cx,
    )
    a, b = (
        (P(fp.x, position), P(fp.x2, position))
        if axis == "x"
        else (P(position, fp.y), P(position, fp.y2))
    )
    svg.add(
        f'<path d="M {a[0]} {a[1]} L {b[0]} {b[1]}" stroke="{ACCENT}" stroke-width=".8" stroke-dasharray="7 5"/><text x="{a[0] - 18}" y="{a[1] - 7}" font-size="10" fill="{ACCENT}">A</text>'
    )
    svg.add(
        f'<g transform="translate(1100,65)"><path d="M 0 27 L 0 0 L -5 10 M 0 0 L 5 10" stroke="{INK}" fill="none"/><text x="10" y="12" font-size="11">N</text></g>'
    )
    svg.add(
        f'<rect x="28" y="793" width="{5 * sc}" height="4" fill="{INK}"/><text x="28" y="786" font-size="9">0 — 5 m</text>'
    )
    svg.add(
        f'<text x="28" y="821" font-size="10" fill="{INK}">Entrance: {escape(model["site"]["entrance"])} · Floor/wall finishes: see model and room schedule</text>'
    )
    return svg.done()


def elevation(model, side="east"):
    fp = rect(model["site"]["footprint"])
    boxes = wall_boxes(model)
    span = fp.d if side in ("east", "west") else fp.w
    base = min(l["elevation"] for l in model["levels"])
    top = max(b["center"][2] + b["size"][2] / 2 for b in boxes)
    sc = min(800 / span, 300 / (top - base))
    svg = SVG(
        1050,
        520,
        f"{model['meta']['name']} — {side.title()} elevation",
        "Orthographic view of canonical geometry",
    )
    ox, oy = 90, 415
    normal_axis = 0 if side in ("east", "west") else 1
    along_axis = 1 - normal_axis
    # Orthographic painter order: draw far solids first, near facade last.
    direction = 1 if side in ("east", "north") else -1
    for b in sorted(boxes, key=lambda b: direction * b["center"][normal_axis]):
        if b["kind"] in ("furniture", "stair", "finish"):
            continue
        x = (
            ox
            + (
                b["center"][along_axis]
                - b["size"][along_axis] / 2
                - (fp.y if along_axis == 1 else fp.x)
            )
            * sc
        )
        y = oy - (b["center"][2] + b["size"][2] / 2 - base) * sc
        fill = (
            "#9dbbca"
            if b["kind"] == "glass"
            else "#bba58a"
            if b["kind"] in ("door", "frame")
            else "#e6dfd1"
        )
        svg.add(
            f'<rect x="{x}" y="{y}" width="{b["size"][along_axis] * sc}" height="{b["size"][2] * sc}" fill="{fill}" stroke="{INK}" stroke-width=".4"/>'
        )
    for l in model["levels"]:
        y = oy - (l["elevation"] - base) * sc
        svg.add(
            f'<path d="M {ox - 10} {y} h {span * sc + 20}" stroke="#7e8790" stroke-dasharray="5 4"/><text x="{ox + span * sc + 25}" y="{y}" font-size="10">{escape(l["id"])} {l["elevation"]:.2f} m</text>'
        )
    _dimension(
        svg,
        (ox - 35, oy),
        (ox - 35, oy - (top - base) * sc),
        f"{top - base:.2f} m",
        True,
    )
    return svg.done()


def section(model, axis=None, position=None):
    fp = rect(model["site"]["footprint"])
    settings = model.get("drawing", {}).get("section", {})
    axis = axis or settings.get("axis", "x")
    court = next((s for s in model["spaces"] if s["open_to_sky"]), None)
    position = (
        position
        if position is not None
        else settings.get(
            "position",
            rect(court["rect"]).cy
            if court and axis == "x"
            else rect(court["rect"]).cx
            if court
            else fp.cy
            if axis == "x"
            else fp.cx,
        )
    )
    if not (
        (fp.y <= position <= fp.y2) if axis == "x" else (fp.x <= position <= fp.x2)
    ):
        raise ValueError("section position lies outside building")
    boxes = wall_boxes(model)
    top = max(b["center"][2] + b["size"][2] / 2 for b in boxes)
    zmin = min(l["elevation"] for l in model["levels"]) - 0.2
    span = fp.w if axis == "x" else fp.d
    sc = min(800 / span, 300 / (top - zmin))
    ox, base = 90, 410
    svg = SVG(
        1050,
        520,
        f"{model['meta']['name']} — Section A–A′",
        f"Actual cut: {'Y' if axis == 'x' else 'X'} = {position:.2f} m · {axis.upper()} horizontal / Z vertical",
    )
    along = 0 if axis == "x" else 1
    normal = 1 - along
    for b in boxes:
        if (
            not b["center"][normal] - b["size"][normal] / 2 - 0.0001
            <= position
            <= b["center"][normal] + b["size"][normal] / 2 + 0.0001
        ):
            continue
        x = (
            ox
            + (
                b["center"][along]
                - b["size"][along] / 2
                - (fp.x if along == 0 else fp.y)
            )
            * sc
        )
        y = base - (b["center"][2] + b["size"][2] / 2 - zmin) * sc
        fill = (
            "#96b5c5"
            if b["kind"] == "glass"
            else "#303b44"
            if b["kind"] == "wall"
            else "#bfaa8a"
        )
        svg.add(
            f'<rect data-source="{escape(b["name"], quote=True)}" x="{x}" y="{y}" width="{b["size"][along] * sc}" height="{b["size"][2] * sc}" fill="{fill}" stroke="{INK}" stroke-width=".5"/>'
        )
    for s in model["spaces"]:
        r = rect(s["rect"])
        if (r.y < position < r.y2) if axis == "x" else (r.x < position < r.x2):
            c = r.cx if axis == "x" else r.cy
            x = ox + (c - (fp.x if along == 0 else fp.y)) * sc
            y = base - (level_bases(model)[s["level"]] + 0.25 - zmin) * sc
            svg.add(
                f'<text x="{x}" y="{y}" text-anchor="middle" font-size="9">{escape(s["name"])}{" · open to sky" if s["open_to_sky"] else ""}</text>'
            )
    for lv in model["levels"]:
        y = base - (lv["elevation"] - zmin) * sc
        svg.add(
            f'<text x="{ox + span * sc + 15}" y="{y}" font-size="10">{escape(lv["id"])} {lv["elevation"]:.2f} m</text>'
        )
    return svg.done()


def roof_plan(model):
    svg = SVG(
        1200,
        900,
        f"{model['meta']['name']} — Roof plan",
        "Actual roof surfaces and hosted skylight apertures",
    )
    P, sc = _project(model)
    for s in model["spaces"]:
        if s["open_to_sky"]:
            _rect_svg(svg, P, rect(s["rect"]), "#cbded2")
        for r in roof_parts(model, s):
            _rect_svg(svg, P, r, "#ded4c3")
    for st in model["stairs"]:
        _rect_svg(svg, P, rect(st["shaft_rect"]), "#ded4c3")
    for o in model["openings"]:
        if o["kind"] == "skylight":
            _rect_svg(svg, P, rect(o["rect"]), "#9dbbca")
    svg.add(
        '<text x="28" y="820" font-size="10">Green: open courtyard · Blue: roof glazing</text>'
    )
    return svg.done()


def exploded(model):
    svg = SVG(
        1200,
        900,
        f"{model['meta']['name']} — Exploded axonometric",
        "Canonical wall/slab solids; floors separated by 3 m",
    )
    boxes = wall_boxes(model)
    levels = {l["id"]: i for i, l in enumerate(model["levels"])}
    points = []

    def iso(x, y, z):
        return ((x - y) * 0.866, (x + y) * 0.5 - z)

    faces = []
    for b in boxes:
        if b["kind"] not in ("wall", "floor", "courtyard", "stair"):
            continue
        x, y, z = b["center"]
        sx, sy, sz = [v / 2 for v in b["size"]]
        z += levels[b["level"]] * 3
        verts = [
            (x + dx * sx, y + dy * sy, z + dz * sz)
            for dx, dy, dz in [
                (-1, -1, -1),
                (1, -1, -1),
                (1, 1, -1),
                (-1, 1, -1),
                (-1, -1, 1),
                (1, -1, 1),
                (1, 1, 1),
                (-1, 1, 1),
            ]
        ]
        for indices, shade in [
            ([4, 5, 6, 7], 1),
            ([2, 3, 7, 6], 0.8),
            ([1, 2, 6, 5], 0.65),
        ]:
            p = [iso(*verts[i]) for i in indices]
            points += p
            faces.append(
                (
                    sum(sum(verts[i]) for i in indices) / len(indices),
                    p,
                    b["color"],
                    shade,
                )
            )
    xmin, xmax = min(x for x, y in points), max(x for x, y in points)
    ymin, ymax = min(y for x, y in points), max(y for x, y in points)
    sc = min(1100 / (xmax - xmin), 700 / (ymax - ymin))
    for _, pts, color, shade in sorted(faces, key=lambda f: f[0]):
        pts = " ".join(
            f"{50 + (x - xmin) * sc:.2f},{95 + (y - ymin) * sc:.2f}" for x, y in pts
        )
        fill = "#" + "".join(
            f"{max(0, min(255, int(v * 255 * shade))):02x}" for v in color[:3]
        )
        svg.add(
            f'<polygon points="{pts}" fill="{fill}" stroke="#5d6265" stroke-width=".35"/>'
        )
    return svg.done()


def schedule_csv(model, kind="room"):
    out = io.StringIO()
    wr = csv.writer(out)
    if kind == "room":
        wr.writerow(
            [
                "id",
                "name",
                "level",
                "zone",
                "area_m2",
                "area_ft2",
                "target_m2",
                "ceiling_m",
                "floor_material",
                "wall_material",
            ]
        )
        from ..building_model.materials import material_for_surface

        for s in model["spaces"]:
            wr.writerow(
                [
                    s["id"],
                    s["name"],
                    s["level"],
                    s["zone"],
                    s["area"],
                    round(s["area"] * 10.7639),
                    s["target_area"],
                    s["ceiling_height"],
                    material_for_surface(model, "floor", s).name,
                    material_for_surface(model, "interior_wall", s).name,
                ]
            )
    else:
        wr.writerow(["id", "kind", "host", "width_m", "height_m", "sill_m", "space"])
        for o in model["openings"]:
            if (kind == "door" and o["kind"] in ("door", "entrance", "passage")) or (
                kind == "window" and o["kind"] in ("window", "skylight")
            ):
                wr.writerow(
                    [
                        o["id"],
                        o["kind"],
                        o.get("roof_id") or o["wall_id"],
                        o["width"],
                        o["height"],
                        o["sill"],
                        o["space_id"],
                    ]
                )
    return out.getvalue()


def dxf_plan(model, level_id=None):
    import ezdxf

    level_id = level_id or model["levels"][0]["id"]
    lv = next(l for l in model["levels"] if l["id"] == level_id)
    doc = ezdxf.new("R2010")
    doc.units = 6
    msp = doc.modelspace()
    layers = {
        "walls": 7,
        "windows": 4,
        "doors": 2,
        "dimensions": 8,
        "labels": 7,
        "furniture": 3,
        "stairs": 6,
    }
    for name, color in layers.items():
        doc.layers.new(name, dxfattribs={"color": color})
    z = lv["elevation"] + min(1.1, lv["height"] / 2)
    for b in wall_boxes(model):
        if b["level"] != level_id:
            continue
        if b["kind"] in ("wall", "glass", "furniture", "stair") and (
            b["kind"] != "wall"
            or b["center"][2] - b["size"][2] / 2
            <= z
            <= b["center"][2] + b["size"][2] / 2
        ):
            x, y = b["center"][:2]
            w, d = b["size"][:2]
            layer = {
                "wall": "walls",
                "glass": "windows",
                "furniture": "furniture",
                "stair": "stairs",
            }[b["kind"]]
            msp.add_lwpolyline(
                [
                    (x - w / 2, y - d / 2),
                    (x + w / 2, y - d / 2),
                    (x + w / 2, y + d / 2),
                    (x - w / 2, y + d / 2),
                ],
                close=True,
                dxfattribs={"layer": layer},
            )
    walls = {w["id"]: w for w in model["walls"]}
    for o in model["openings"]:
        if (
            o["kind"] not in ("door", "entrance")
            or walls[o["wall_id"]]["level"] != level_id
        ):
            continue
        h, c, l = _door_geometry(model, o)
        msp.add_line(h, l, dxfattribs={"layer": "doors"})
        a = math.degrees(math.atan2(c[1] - h[1], c[0] - h[0]))
        b = math.degrees(math.atan2(l[1] - h[1], l[0] - h[0]))
        a, b = (a, b) if (b - a) % 360 <= 180 else (b, a)
        msp.add_arc(h, o["width"], a, b, dxfattribs={"layer": "doors"})
    for s in model["spaces"]:
        if s["level"] != level_id:
            continue
        r = rect(s["rect"])
        msp.add_text(
            f"{s['name']} {s['area']:.1f} m2",
            height=0.22,
            dxfattribs={"layer": "labels"},
        ).set_placement((r.cx, r.cy))
        for p1, p2, base, angle in [
            ((r.x, r.y), (r.x2, r.y), (r.x, r.y + 0.35), 0),
            ((r.x, r.y), (r.x, r.y2), (r.x + 0.35, r.y), 90),
        ]:
            dim = msp.add_linear_dim(
                base=base,
                p1=p1,
                p2=p2,
                angle=angle,
                dimstyle="EZDXF",
                override={"dimtxt": 0.16, "dimasz": 0.12},
                dxfattribs={"layer": "dimensions"},
            )
            dim.render()
    fp = rect(model["site"]["footprint"])
    for p1, p2, base, angle in [
        ((fp.x, fp.y), (fp.x2, fp.y), (fp.x, fp.y - 1), 0),
        ((fp.x, fp.y), (fp.x, fp.y2), (fp.x - 1, fp.y), 90),
    ]:
        dim = msp.add_linear_dim(
            base=base,
            p1=p1,
            p2=p2,
            angle=angle,
            dimstyle="EZDXF",
            override={"dimtxt": 0.2, "dimasz": 0.15},
            dxfattribs={"layer": "dimensions"},
        )
        dim.render()
    msp.add_text(
        "CONCEPT DESIGN ONLY - NOT FOR CONSTRUCTION", height=0.25
    ).set_placement((fp.x, fp.y - 2))
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue()
