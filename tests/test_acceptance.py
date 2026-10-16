#!/usr/bin/env python3
"""Acceptance test: courtyard house (1-storey) + modern villa (2-storey, stair).

Run: python tests/test_acceptance.py   — exits non-zero on any failure.
"""

import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engines.spatial_solver.solver import resolve
from engines.design_validator.validator import validate
from engines.bim_exporter.exporters import wall_boxes, export_glb
from engines.blueprint_generator import drawings

ROOT = os.path.join(os.path.dirname(__file__), "..")
ok = True


def check(name, cond, extra=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    ok = ok and cond


def run_acceptance():
    global ok
    ok = True
    for ex, variants in (
        ("courtyard-house", 3),
        ("modern-villa", 1),
        ("commercial-building", 1),
    ):
        spec = json.load(open(os.path.join(ROOT, "examples", ex, "building-spec.json")))
        for v in range(variants):
            m = resolve(spec, v)
            val = validate(m)
            check(
                f"{ex} v{v + 1}: no FAIL",
                val["status"] == "PASS",
                "; ".join(val["fail"]),
            )
            check(
                f"{ex} v{v + 1}: has walls+openings",
                len(m["walls"]) > 10 and len(m["openings"]) > 5,
            )
            svg = drawings.floor_plan(m)
            check(
                f"{ex} v{v + 1}: plan SVG dimensioned",
                " m</text>" in svg and "CONCEPT DESIGN" in svg,
            )
            boxes = wall_boxes(m)
            check(f"{ex} v{v + 1}: 3D boxes from same model", len(boxes) > 20)
            if len(spec["levels"]) > 1:
                check(
                    f"{ex} v{v + 1}: stair computed",
                    len(m["stairs"]) == 1 and m["stairs"][0]["risers"] > 5,
                )
            if v == 0:
                p = f"/tmp/{ex}.glb"
                n = export_glb(m, p)
                check(f"{ex}: GLB written", os.path.getsize(p) > 1000, f"{n} boxes")

    # --- material primitives
    from engines.building_model.materials import resolve_material, CATALOG

    for mid in (
        "standing_seam_metal",
        "pine_wood",
        "stucco",
        "wood_slat",
        "marble",
        "quartz",
        "stainless_steel",
        "maple",
    ):
        check(f"catalog has {mid}", mid in CATALOG)
    check(
        "alias pipe_wood -> pine_wood", resolve_material("pipe_wood").id == "pine_wood"
    )
    check(
        "alias stainless -> stainless_steel",
        resolve_material("stainless").id == "stainless_steel",
    )
    check("stainless is metallic", resolve_material("stainless_steel").metalness == 1.0)
    check(
        "inline override wins",
        resolve_material({"id": "maple", "roughness": 0.35}).roughness == 0.35,
    )
    _villa = json.load(
        open(os.path.join(ROOT, "examples/modern-villa/building-spec.json"))
    )
    _vm = resolve(_villa, 0)
    _vb = wall_boxes(_vm)
    check(
        "villa: standing-seam ribs generated",
        any(
            b["kind"] == "seam" and b["material"] == "standing_seam_metal" for b in _vb
        ),
    )
    check(
        "villa: wood slat segmentation",
        sum(1 for b in _vb if b.get("pattern") == "slat") > 20,
    )
    check(
        "villa: marble + quartz present",
        {"marble", "quartz"} <= {b.get("material") for b in _vb},
    )
    check(
        "villa: model resolves materials",
        _vm["materials_resolved"]["floor"]["id"] == "maple",
    )

    # modification test: widen courtyard -> courtyard area grows, everything still valid
    spec = json.load(
        open(os.path.join(ROOT, "examples/courtyard-house/building-spec.json"))
    )
    before = resolve(spec, 0)
    spec2 = json.loads(json.dumps(spec))
    for s in spec2["spaces"]:
        if s.get("open_to_sky"):
            s["target_area"] *= 1.25
    after = resolve(spec2, 0)
    cb = next(s for s in before["spaces"] if s["open_to_sky"])
    ca = next(s for s in after["spaces"] if s["open_to_sky"])
    check(
        "modify: courtyard grew",
        ca["area"] > cb["area"],
        f"{cb['area']:.1f} -> {ca['area']:.1f} m²",
    )
    check(
        "modify: still valid",
        validate(after)["status"] == "PASS",
        "; ".join(validate(after)["fail"]),
    )
    print("\nALL PASS" if ok else "\nSOME FAILURES")
    return ok


def test_acceptance():
    assert run_acceptance()


if __name__ == "__main__":
    sys.exit(0 if run_acceptance() else 1)
