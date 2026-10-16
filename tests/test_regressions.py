"""Behavioral regressions for geometry, interoperability, and CLI contracts."""

import ast
import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engines.spatial_solver.solver import resolve
from engines.design_validator.validator import validate, access_graph, reachable
from engines.building_model.geometry import rect, level_bases
from engines.building_model.inputs import SpecError
from engines.bim_exporter.exporters import wall_boxes, export_glb, export_ifc
from engines.blueprint_generator import drawings


def spec(name="courtyard-house"):
    return json.loads((ROOT / "examples" / name / "building-spec.json").read_text())


def space(m, sid):
    return next(s for s in m["spaces"] if s["id"] == sid)


def cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools/architect.py"), *map(str, args)],
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
    )


@pytest.mark.parametrize(
    "example,variants",
    [
        ("courtyard-house", range(3)),
        ("modern-villa", range(3)),
        ("commercial-building", range(3)),
    ],
)
def test_examples_are_reachable_and_hard_constraints_hold(example, variants):
    for v in variants:
        m = resolve(spec(example), v)
        report = validate(m)
        assert report["status"] == "PASS", report["fail"]
        graph, roots = access_graph(m)
        assert roots
        assert {s["id"] for s in m["spaces"]} <= reachable(graph, roots)
        assert all(c["met"] for c in report["constraints"] if c["required"])


def test_no_openings_or_entrance_cannot_pass():
    m = resolve(spec())
    m["openings"] = []
    v = validate(m)
    assert v["status"] == "FAIL"
    assert any("no exterior entrance" in x for x in v["fail"])
    assert sum("unreachable" in x for x in v["fail"]) == len(m["spaces"])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s["spaces"].append(copy.deepcopy(s["spaces"][0])),
        lambda s: s["spaces"][0].update(level="missing"),
        lambda s: s["spaces"][0].update(target_area=-1),
        lambda s: s["spaces"][0].update(adjacent_to=["missing"]),
        lambda s: s["building"].update(units="centimeters"),
        lambda s: s.update(made_up_constraint=True),
        lambda s: s["site"].update(width=float("nan")),
        lambda s: s["materials"].update(roof={"id": "maple", "roughness": 2}),
        lambda s: s["materials"].update(
            roof={
                "id": "standing_seam_metal",
                "pattern": {"type": "standing_seam", "seam_spacing_m": 0},
            }
        ),
    ],
)
def test_invalid_input_is_rejected(mutate):
    s = spec()
    mutate(s)
    with pytest.raises((SpecError, ValueError)):
        resolve(s)


def test_feet_input_normalizes_dimensions_areas_and_elevations():
    s = spec("modern-villa")
    ft = copy.deepcopy(s)
    ft["building"]["units"] = "feet"
    for key in ["width", "depth"]:
        ft["site"][key] /= 0.3048
    for key in ft["site"]["setbacks"]:
        ft["site"]["setbacks"][key] /= 0.3048
    ft["planning"]["circulation_width"] /= 0.3048
    for lv in ft["levels"]:
        for key in ["height", "elevation"]:
            lv[key] /= 0.3048
    for room in ft["spaces"]:
        room["target_area"] /= 0.3048**2
    a, b = resolve(s), resolve(ft)
    for room in a["spaces"]:
        other = space(b, room["id"])
        assert room["area"] == pytest.approx(other["area"], abs=0.001)
        assert room["rect"] == pytest.approx(other["rect"], abs=0.00001)
    assert a["levels"] == b["levels"]


def test_ceiling_edit_changes_wall_and_roof_geometry_without_moving_rooms():
    s = spec()
    a = resolve(s)
    next(x for x in s["spaces"] if x["id"] == "living")["ceiling_height"] = 4.87
    b = resolve(s)
    assert [x["rect"] for x in a["spaces"]] == [x["rect"] for x in b["spaces"]]
    assert wall_boxes(a) != wall_boxes(b)
    assert max(w["height"] for w in b["walls"] if "living" in w["spaces"]) == 4.87
    roofs = [
        x for x in wall_boxes(b) if x["kind"] == "roof" and x["name"] == "roof-living"
    ]
    assert roofs
    assert all(x["center"][2] == pytest.approx(4.95) for x in roofs)
    assert validate(b)["status"] == "PASS"


def test_skylight_is_a_real_roof_aperture():
    s = spec()
    a = resolve(s)
    next(x for x in s["spaces"] if x["id"] == "dining")["skylight"] = True
    b = resolve(s)
    o = next(x for x in b["openings"] if x["kind"] == "skylight")
    aperture = rect(o["rect"])
    parts = [x for x in wall_boxes(b) if x["kind"] == "roof" and x["space"] == "dining"]
    assert parts and wall_boxes(a) != wall_boxes(b)
    for p in parts:
        footprint = rect(
            {
                "x": p["center"][0] - p["size"][0] / 2,
                "y": p["center"][1] - p["size"][1] / 2,
                "w": p["size"][0],
                "d": p["size"][1],
            }
        )
        assert not footprint.overlaps(aperture)
    assert any(x["kind"] == "glass" and x["name"] == o["id"] for x in wall_boxes(b))


def test_double_height_stairs_and_elevations():
    m = resolve(spec("modern-villa"))
    bases = level_bases(m)
    living = space(m, "living")
    for s in m["spaces"]:
        if bases[s["level"]] > bases[living["level"]]:
            assert not rect(living["rect"]).overlaps(rect(s["rect"]), eps=0.002)
    assert m["stairs"][0]["fits"]
    assert space(m, "landing-stair")["level"] == "upper"
    shaft = rect(m["stairs"][0]["shaft_rect"])
    upperfloors = [
        b for b in wall_boxes(m) if b["kind"] == "floor" and b["level"] == "upper"
    ]
    for b in upperfloors:
        assert not rect(
            {
                "x": b["center"][0] - b["size"][0] / 2,
                "y": b["center"][1] - b["size"][1] / 2,
                "w": b["size"][0],
                "d": b["size"][1],
            }
        ).overlaps(shaft, eps=0.002)
    assert (
        sum(b["kind"] == "stair" for b in wall_boxes(m)) == m["stairs"][0]["risers"] - 1
    )
    tampered = copy.deepcopy(m)
    space(tampered, "primary")["rect"] = living["rect"]
    space(tampered, "primary")["area"] = living["area"]
    assert validate(tampered)["status"] == "FAIL"


def test_open_plan_connections_and_layered_slats():
    m = resolve(spec())
    walls = {w["id"]: w for w in m["walls"]}
    assert any(
        o["kind"] == "passage"
        and set(walls[o["wall_id"]]["spaces"]) == {"living", "dining"}
        for o in m["openings"]
    )
    b = wall_boxes(m)
    finishes = [x for x in b if x["kind"] == "finish" and x["pattern"] == "slat"]
    assert finishes
    assert all(
        any(core["kind"] == "wall" and core["host_id"] == f["host_id"] for core in b)
        for f in finishes
    )


def test_required_constraints_and_furniture_cannot_silently_fail():
    s = spec()
    s["constraints"].append({"type": "max_footprint", "value": 1, "required": True})
    assert validate(resolve(s))["status"] == "FAIL"
    s = spec()
    next(x for x in s["spaces"] if x["id"] == "living")["furniture"] = [
        {"id": "oversize", "width": 100, "depth": 100, "required": True}
    ]
    assert any("clearance" in x for x in validate(resolve(s))["fail"])


def test_glb_outward_faces_normals_and_pbr(tmp_path):
    path = tmp_path / "model.glb"
    m = resolve(spec())
    export_glb(m, path)
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<III", data)
    assert (magic, version, length) == (0x46546C67, 2, len(data))
    size = struct.unpack_from("<I", data, 12)[0]
    g = json.loads(data[20 : 20 + size])
    binary = data[28 + size :]
    assert all(
        "roughnessFactor" in mat["pbrMetallicRoughness"] for mat in g["materials"]
    )
    p = g["meshes"][0]["primitives"][0]

    def vecs(index):
        a = g["accessors"][index]
        view = g["bufferViews"][a["bufferView"]]
        return [
            struct.unpack_from("<fff", binary, view["byteOffset"] + i * 12)
            for i in range(a["count"])
        ]

    vertices = vecs(p["attributes"]["POSITION"])
    normals = vecs(p["attributes"]["NORMAL"])
    center = [sum(v[k] for v in vertices) / len(vertices) for k in range(3)]
    for i in range(0, len(vertices), 3):
        a, b, c = vertices[i : i + 3]
        u = [b[k] - a[k] for k in range(3)]
        v = [c[k] - a[k] for k in range(3)]
        n = [
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        ]
        assert sum(n[k] * (a[k] - center[k]) for k in range(3)) > 0
        assert sum(n[k] * normals[i][k] for k in range(3)) > 0


def test_ifc_roundtrip_schema_relationships_and_geometry(tmp_path):
    import ifcopenshell, ifcopenshell.validate, ifcopenshell.geom

    m = resolve(spec())
    next(x for x in m["spaces"] if x["id"] == "dining")["skylight"] = True
    # Resolve the input again so the roof opening also exists.
    s = spec()
    next(x for x in s["spaces"] if x["id"] == "dining")["skylight"] = True
    m = resolve(s)
    path = tmp_path / "model.ifc"
    export_ifc(m, path)
    f = ifcopenshell.open(path)
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, logger)
    assert not logger.statements, logger.statements
    assert len(f.by_type("IfcRelVoidsElement")) >= len(m["openings"])
    assert len(f.by_type("IfcBuildingStorey")) == len(m["levels"])
    settings = ifcopenshell.geom.settings()
    for wall in f.by_type("IfcWall")[:3]:
        assert len(ifcopenshell.geom.create_shape(settings, wall).geometry.verts) > 0
    ids = {w.Name: w.GlobalId for w in f.by_type("IfcWall")}
    export_ifc(m, tmp_path / "again.ifc")
    again = ifcopenshell.open(tmp_path / "again.ifc")
    assert ids == {w.Name: w.GlobalId for w in again.by_type("IfcWall")}


def test_dxf_has_units_openings_arcs_and_actual_dimensions():
    import ezdxf
    import io

    m = resolve(spec())
    doc = ezdxf.read(io.StringIO(drawings.dxf_plan(m)))
    msp = doc.modelspace()
    assert doc.units == 6
    assert len(msp.query("DIMENSION")) > len(m["spaces"])
    assert len(msp.query("ARC")) > 0
    assert len(msp.query('LWPOLYLINE[layer=="windows"]')) > 0


def test_section_only_draws_solids_crossing_cut_plane():
    m = resolve(spec())
    position = space(m, "courtyard")["rect"]["y"] + 1.0
    svg = ET.fromstring(drawings.section(m, axis="x", position=position))
    sources = {
        node.attrib["data-source"]
        for node in svg.iter()
        if "data-source" in node.attrib
    }
    expected = {
        b["name"]
        for b in wall_boxes(m)
        if b["center"][1] - b["size"][1] / 2 - 0.0001
        <= position
        <= b["center"][1] + b["size"][1] / 2 + 0.0001
    }
    assert sources == expected
    with pytest.raises(ValueError):
        drawings.section(m, axis="y", position=-100)


def test_cli_invalid_build_and_validate_exit_nonzero(tmp_path):
    s = spec()
    s["constraints"].append({"type": "max_footprint", "required": True, "value": 1})
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(s))
    out = tmp_path / "failed"
    result = cli("build", path, "--out", out)
    assert result.returncode == 1
    assert (out / "validation.json").exists()
    assert not (out / "model.glb").exists()
    assert not list(out.glob("plan*"))
    assert cli("validate", out / "model.json").returncode == 1
    assert cli("build", path, "--variant", "0", "--out", out).returncode != 0


def test_cli_edit_persistence_and_portable_scripts(tmp_path):
    original = tmp_path / "source.json"
    original.write_text(json.dumps(spec()))
    out = tmp_path / "first"
    result = cli(
        "modify",
        original,
        "--ceiling",
        "living=4.87",
        "--skylight",
        "dining",
        "--out",
        out,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    model = json.loads((out / "model.json").read_text())
    assert space(model, "living")["ceiling_height"] == 4.87
    assert any(o["kind"] == "skylight" for o in model["openings"])
    assert (out / "consequences.md").exists()
    for path in (out / "renders").glob("*.py"):
        ast.parse(path.read_text())
    second = cli(
        "modify",
        out / "building-spec.json",
        "--area",
        "study=14",
        "--out",
        tmp_path / "second",
    )
    assert second.returncode == 0, second.stderr
    model = json.loads((tmp_path / "second/model.json").read_text())
    assert space(model, "living")["ceiling_height"] == 4.87
    assert (
        cli(
            "modify", original, "--ceiling", "unknown=4", "--out", tmp_path / "bad"
        ).returncode
        != 0
    )


def test_cli_widen_is_width_factor_and_comparison_has_metrics(tmp_path):
    original = tmp_path / "spec.json"
    original.write_text(json.dumps(spec()))
    before = resolve(spec())
    out = tmp_path / "modified"
    r = cli("modify", original, "--widen-courtyard", "1.25", "--out", out)
    assert r.returncode == 0, r.stderr
    after = json.loads((out / "model.json").read_text())
    assert space(after, "courtyard")["rect"]["w"] == pytest.approx(
        space(before, "courtyard")["rect"]["w"] * 1.25, abs=0.00001
    )
    assert space(after, "courtyard")["rect"]["d"] == pytest.approx(
        space(before, "courtyard")["rect"]["d"], abs=0.00001
    )
    r = cli("design", original, "--out", tmp_path / "alts")
    assert r.returncode == 0, r.stderr
    text = (tmp_path / "alts/comparison.md").read_text()
    assert "Adjacency" in text and "Circulation" in text and "Daylit" in text


def test_repeated_build_cache_and_failed_rebuild_remove_old_presentation(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(json.dumps(spec()))
    out = tmp_path / "result"
    first = cli("build", path, "--out", out)
    assert first.returncode == 0, first.stderr
    before = (out / "model.glb").stat().st_mtime_ns
    second = cli("build", path, "--out", out)
    assert second.returncode == 0, second.stderr
    assert (out / "model.glb").stat().st_mtime_ns == before
    assert "0 outputs changed" in second.stdout
    s = spec()
    s["constraints"].append({"type": "max_footprint", "value": 1, "required": True})
    path.write_text(json.dumps(s))
    failed = cli("build", path, "--out", out)
    assert failed.returncode == 1
    assert not (out / "model.glb").exists()
    assert not (out / "viewer.html").exists()
    assert not list(out.glob("plan_*.svg"))
    assert json.loads((out / "manifest.json").read_text())["status"] == "FAIL"


def test_output_preflight_preserves_unowned_files(tmp_path):
    out = tmp_path / "existing"
    out.mkdir()
    (out / "model.glb").write_text("user-owned-file")
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec()))
    result = cli("build", path, "--out", out)
    assert result.returncode == 1
    assert "unowned" in result.stderr
    assert (out / "model.glb").read_text() == "user-owned-file"
    assert not (out / "model.json").exists()


def test_door_leaf_matches_plan_and_declared_tread_going():
    from engines.building_model.geometry import door_points

    m = resolve(spec("modern-villa"))
    boxes = wall_boxes(m)
    for o in m["openings"]:
        if o["kind"] not in ("door", "entrance") or o.get("glazed"):
            continue
        hinge, closed, leaf = door_points(m, o)
        b = next(b for b in boxes if b["kind"] == "door" and b["name"] == o["id"])
        assert b["center"][:2] == pytest.approx(
            [(hinge[0] + leaf[0]) / 2, (hinge[1] + leaf[1]) / 2]
        )
    st = m["stairs"][0]
    for b in boxes:
        if b["kind"] == "stair" and b["name"].startswith("tread-"):
            assert b["size"][1 if st["axis"] == "y" else 0] == pytest.approx(
                st["going_mm"] / 1000
            )


def test_optional_material_fallback_is_visible_and_required_minimum_is_hard():
    s = spec()
    s["materials"]["exterior"] = "unknown-vendor-finish"
    assert any("neutral fallback" in w for w in validate(resolve(s))["warn"])
    s = spec()
    next(x for x in s["spaces"] if x["id"] == "living")["min_width"] = 100
    assert validate(resolve(s))["status"] == "FAIL"


def test_drawing_only_rebuild_preserves_render_and_geometry_edit_archives_it(
    tmp_path, monkeypatch
):
    import hashlib
    import importlib.util

    module_spec = importlib.util.spec_from_file_location(
        "architect_cli", ROOT / "tools/architect.py"
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    s = spec()
    m = resolve(s)
    out = tmp_path / "build"
    assert module._save(m, out, full=True, spec=s)["status"] == "PASS"
    image = out / "custom-presentation/render_completed.png"
    image.parent.mkdir()
    image.write_bytes(b"completed-render-artifact")
    manifest = module.load(out / "manifest.json")
    manifest["files"]["custom-presentation/render_completed.png"] = hashlib.sha256(
        image.read_bytes()
    ).hexdigest()
    manifest["render_status"] = "rendered"
    module.write(out / "manifest.json", manifest)
    monkeypatch.setattr(module, "pipeline_hash", lambda: "drawing-only-revision")
    assert module._save(m, out, full=True, spec=s)["status"] == "PASS"
    assert image.read_bytes() == b"completed-render-artifact"
    assert module.load(out / "manifest.json")["render_status"] == "rendered"
    changed = copy.deepcopy(s)
    next(room for room in changed["spaces"] if room["id"] == "living")[
        "ceiling_height"
    ] = 4.87
    assert (
        module._save(resolve(changed), out, full=True, spec=changed)["status"] == "PASS"
    )
    assert not image.exists()
    assert list((out / "stale-renders").rglob("render_completed.png"))
