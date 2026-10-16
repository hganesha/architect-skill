#!/usr/bin/env python3
"""Model-first concept architecture: concept / design / build / validate / modify / render."""

from __future__ import annotations
import argparse
import hashlib
from html import escape
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engines.spatial_solver.solver import resolve, VARIANTS
from engines.design_validator.validator import validate
from engines.building_model.inputs import SpecError, normalize
from engines.building_model.model import DISCLAIMER
from engines.bim_exporter.exporters import export_glb, export_ifc, wall_boxes
from engines.blueprint_generator import drawings
from renderers.blender.render_blender import generate


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        if not isinstance(value, str)
        else value
    )


def _report(model, val):
    lines = [
        f"# {model['meta']['name']} — {model['meta']['variant_name']}",
        DISCLAIMER,
        f"\nValidation: **{val['status']}**",
        "\n## Metrics",
    ]
    lines += [f"- {k}: {v}" for k, v in val["metrics"].items()]
    for group in ("fail", "warn"):
        lines.append(f"\n## {group.upper()}")
        lines += [f"- {x}" for x in val[group]] or ["- None"]
    lines.append("\n## Spaces")
    lines += [
        f"- {s['id']}: {s['area']:.1f} m² / target {s['target_area']:.1f} m²; ceiling {s['ceiling_height']:.2f} m; {s['level']}"
        for s in model["spaces"]
    ]
    lines += [
        "\nRender scripts require Blender execution to produce PNG/.blend files.",
        DISCLAIMER,
    ]
    return "\n".join(lines) + "\n"


def pipeline_hash():
    paths = [
        *ROOT.glob("engines/**/*.py"),
        *ROOT.glob("renderers/**/*.py"),
        *ROOT.glob("renderers/**/*.html"),
        *ROOT.glob("renderers/**/*.json"),
        *ROOT.glob("schemas/*.json"),
        ROOT / "materials/catalog.json",
        ROOT / "tools/architect.py",
    ]
    return hashlib.sha256(b"".join(p.read_bytes() for p in sorted(paths))).hexdigest()


def renderer_hash():
    paths = [
        *ROOT.glob("renderers/blender/*.py"),
        ROOT / "renderers/blender/styles.json",
        ROOT / "engines/bim_exporter/exporters.py",
        ROOT / "engines/building_model/materials.py",
        ROOT / "engines/building_model/geometry.py",
        ROOT / "materials/catalog.json",
    ]
    return hashlib.sha256(b"".join(p.read_bytes() for p in sorted(paths))).hexdigest()


def is_render_artifact(rel):
    return rel.startswith("renders/") or Path(rel).name.startswith("render_")


def _publish(stage, out):
    """Only manage files owned by this tool; retain unrelated user files."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    previous = load(out / "manifest.json") if (out / "manifest.json").exists() else {}
    current = {}
    changed = []
    unchanged = []
    for rel in previous.get("files", {}):
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise ValueError("invalid output manifest path")
    for path in Path(stage).rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(stage))
        target = out / rel
        if (
            target.exists()
            and rel not in previous.get("files", {})
            and not (rel == "manifest.json" and previous)
        ):
            raise ValueError(
                f"refusing to overwrite unowned output: {target}; choose an empty output directory"
            )
    for path in sorted(Path(stage).rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(stage))
        target = out / rel
        data = path.read_bytes()
        current[rel] = hashlib.sha256(data).hexdigest()
        if target.is_file() and target.read_bytes() == data:
            unchanged.append(rel)
            continue
        if (
            target.exists()
            and rel not in previous.get("files", {})
            and not (rel == "manifest.json" and previous)
        ):
            raise ValueError(
                f"refusing to overwrite unowned output: {target}; choose an empty output directory"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".tmp")
        temp.write_bytes(data)
        os.replace(temp, target)
        changed.append(rel)
    for rel, oldhash in previous.get("files", {}).items():
        # Failed models must not leave a previous drawing set beside new diagnostics.
        if (
            rel not in current
            and (target := out / rel).is_file()
            and hashlib.sha256(target.read_bytes()).hexdigest() == oldhash
        ):
            if is_render_artifact(rel):
                archived = (
                    out
                    / "stale-renders"
                    / previous.get("model_hash", "unknown")[:12]
                    / rel
                )
                archived.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, archived)
            else:
                target.unlink()
    manifest = (
        load(Path(stage) / "manifest.json")
        if (Path(stage) / "manifest.json").exists()
        else {}
    )
    manifest.update(
        files={k: v for k, v in current.items() if k != "manifest.json"},
        changed=changed,
        unchanged=unchanged,
    )
    write(out / "manifest.json", manifest)
    return changed, unchanged


def _save(model, out, full=False, spec=None):
    val = validate(model)
    out = Path(out)
    old = load(out / "manifest.json") if (out / "manifest.json").exists() else {}
    ph = pipeline_hash()
    if (
        old.get("model_hash") == digest(model)
        and old.get("spec_hash") == digest(spec)
        and old.get("pipeline_hash") == ph
        and old.get("full") == full
        and old.get("files")
        and all(
            (out / rel).is_file()
            and hashlib.sha256((out / rel).read_bytes()).hexdigest() == h
            for rel, h in old["files"].items()
        )
    ):
        val["outputs_changed"] = []
        val["outputs_unchanged"] = list(old["files"])
        return val
    with tempfile.TemporaryDirectory(prefix="architect-build-") as temporary:
        stage = Path(temporary)
        write(stage / "model.json", model)
        write(stage / "validation.json", val)
        write(stage / "report.md", _report(model, val))
        if spec is not None:
            write(stage / "building-spec.json", spec)
        if val["status"] == "PASS":
            for lv in model["levels"]:
                write(
                    stage / f"plan_{lv['id']}.svg", drawings.floor_plan(model, lv["id"])
                )
                if full:
                    write(
                        stage / f"plan_{lv['id']}.dxf",
                        drawings.dxf_plan(model, lv["id"]),
                    )
            export_glb(model, stage / "model.glb")
            if full:
                export_ifc(model, stage / "model.ifc")
                for side in ("north", "south", "east", "west"):
                    write(
                        stage / f"elevation_{side}.svg", drawings.elevation(model, side)
                    )
                for name, fn in [
                    ("section", drawings.section),
                    ("roof_plan", drawings.roof_plan),
                    ("exploded", drawings.exploded),
                ]:
                    write(stage / f"{name}.svg", fn(model))
                for k in ("room", "door", "window"):
                    write(stage / f"schedule_{k}.csv", drawings.schedule_csv(model, k))
            template = (ROOT / "renderers/webgl/viewer_template.html").read_text()
            # Script JSON must not be able to close its script tag via a project/room name.
            payload = (
                json.dumps({"model": model, "boxes": wall_boxes(model)})
                .replace("<", "\\u003c")
                .replace(">", "\\u003e")
                .replace("&", "\\u0026")
            )
            template = template.replace(
                "MODEL_TITLE", escape(model["meta"]["name"])
            ).replace("VARIANT_NAME", escape(model["meta"]["variant_name"]))
            write(
                stage / "viewer.html",
                template.replace("/*__MODEL_JSON__*/null", payload),
            )
            generate(model, stage / "renders")
            if (
                old.get("model_hash") == digest(model)
                and old.get("renderer_hash") == renderer_hash()
            ):
                # Preserve verified image/scene/payload profiles through drawing-only
                # updates. A renderer or geometry change invalidates these artifacts.
                for rel, h in old.get("files", {}).items():
                    source = out / rel
                    if (
                        is_render_artifact(rel)
                        and source.is_file()
                        and hashlib.sha256(source.read_bytes()).hexdigest() == h
                    ):
                        destination = stage / rel
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(source.read_bytes())
        write(
            stage / "manifest.json",
            {
                "status": val["status"],
                "model_hash": digest(model),
                "spec_hash": digest(spec) if spec else None,
                "render_status": old.get("render_status", "script_only")
                if old.get("model_hash") == digest(model)
                and old.get("renderer_hash") == renderer_hash()
                and val["status"] == "PASS"
                else "script_only",
                "renderer_hash": renderer_hash(),
                "schema_version": "2.0",
                "pipeline_hash": ph,
                "full": full,
            },
        )
        changed, unchanged = _publish(stage, out)
    val["outputs_changed"] = changed
    val["outputs_unchanged"] = unchanged
    return val


def cmd_design(a):
    spec = load(a.spec)
    normalize(spec)
    rows = []
    failed = 0
    for i in range(a.alternatives):
        out = Path(a.out) / f"alternative-{i + 1}"
        try:
            m = resolve(spec, i)
            v = _save(m, out, spec=spec)
            rows.append((i + 1, m["meta"]["variant_name"], v))
        except SpecError as e:
            out.mkdir(parents=True, exist_ok=True)
            v = {"status": "FAIL", "fail": [str(e)], "warn": [], "metrics": {}}
            write(out / "validation.json", v)
            rows.append((i + 1, VARIANTS[i]["name"], v))
        failed += v["status"] != "PASS"
    comparison = [
        f"# Alternatives — {spec['building']['name']}",
        DISCLAIMER,
        "\n| # | Concept | Status | Enclosed m² | Area deviation | Daylit rooms | Adjacency | Circulation m² | FAIL / WARN |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, name, v in rows:
        m = v["metrics"]
        comparison.append(
            f"| {i} | {name} | {v['status']} | {m.get('enclosed_area_m2', '—')} | {m.get('area_deviation_mean', '—')} | {m.get('daylit_rooms', '—')}/{m.get('habitable_rooms', '—')} | {m.get('adjacency_realized', '—')}/{m.get('adjacency_requested', '—')} | {m.get('circulation_area_m2', '—')} | {len(v['fail'])} / {len(v['warn'])} |"
        )
    comparison.append(
        "\nSelect a feasible alternative for a full build. Failed alternatives contain diagnostics only."
    )
    write(Path(a.out) / "comparison.md", "\n".join(comparison))
    print("\n".join(comparison))
    return 1 if failed else 0


def cmd_build(a):
    spec = load(a.spec)
    m = resolve(spec, a.variant - 1)
    v = _save(m, a.out, full=a.mode != "concept", spec=spec)
    print(
        f"{v['status']}: {a.out} ({len(v['fail'])} fail, {len(v['warn'])} warn; {len(v['outputs_changed'])} outputs changed)"
    )
    for fail in v["fail"]:
        print("FAIL:", fail)
    return int(v["status"] != "PASS")


def cmd_validate(a):
    v = validate(load(a.model))
    print(json.dumps(v, indent=2))
    return int(v["status"] != "PASS")


def cmd_modify(a):
    raw = load(a.spec)
    before = resolve(raw, a.variant - 1)
    spec = normalize(raw)
    changes = []
    by_id = {s["id"]: s for s in spec["spaces"]}

    def target(sid):
        if sid not in by_id:
            raise SpecError(f"unknown space ID: {sid}")
        return by_id[sid]

    def pairs(values):
        for value in values or []:
            if "=" not in value:
                raise SpecError(f"expected space=value: {value}")
            yield value.split("=", 1)

    if a.widen_courtyard is not None:
        if a.widen_courtyard <= 0:
            raise SpecError("courtyard width factor must be positive")
        court = next((s for s in before["spaces"] if s["open_to_sky"]), None)
        if not court:
            raise SpecError("no courtyard to widen")
        r = court["rect"]
        s = target(court["id"])
        s["target_area"] = r["w"] * a.widen_courtyard * r["d"]
        s["aspect_ratio"] = r["w"] * a.widen_courtyard / r["d"]
        changes.append(f"{s['id']}: width × {a.widen_courtyard}")
    for field, values in [
        ("ceiling_height", a.ceiling),
        ("target_area", a.area),
        ("min_width", a.min_width),
    ]:
        for sid, value in pairs(values):
            target(sid)[field] = float(value)
            changes.append(f"{sid}: {field} -> {value} (SI)")
    for sid in a.skylight or []:
        target(sid)["skylight"] = True
        changes.append(f"{sid}: add skylight")
    for sid, near in pairs(a.move_near):
        target(sid)["near"] = target(near)["id"]
        spec.setdefault("constraints", []).append(
            {"type": "adjacency", "spaces": [sid, near], "required": True}
        )
        changes.append(f"{sid}: require adjacency to {near}")
    for surface, material in pairs(a.material):
        if surface not in ("exterior", "interior", "flooring", "roof", "courtyard"):
            raise SpecError(f"unsupported building surface: {surface}")
        spec.setdefault("materials", {})[surface] = material
        changes.append(f"{surface}: material -> {material}")
    if not changes:
        raise SpecError("no edits supplied")
    after = resolve(spec, a.variant - 1)
    v = _save(after, a.out, full=True, spec=spec)
    # Keep the historical filename for clients, but authoritative spec is building-spec.json.
    write(Path(a.out) / "building-spec.modified.json", spec)
    bmap = {s["id"]: s for s in before["spaces"]}
    lines = ["# Modification consequences", DISCLAIMER, "\n## Requested edits"] + [
        f"- {c}" for c in changes
    ]
    lines.append("\n## Geometry and area changes")
    for s in after["spaces"]:
        b = bmap.get(s["id"])
        if b and (
            b["rect"] != s["rect"]
            or b["ceiling_height"] != s["ceiling_height"]
            or b["area"] != s["area"]
        ):
            lines.append(
                f"- {s['id']}: area {b['area']:.2f} → {s['area']:.2f} m²; rect {b['rect']} → {s['rect']}; ceiling {b['ceiling_height']} → {s['ceiling_height']} m"
            )
    beforev = validate(before)
    for key in ("fail", "warn"):
        added = set(v[key]) - set(beforev[key])
        removed = set(beforev[key]) - set(v[key])
        lines.append(f"\n## {key.upper()} diff")
        lines += [f"- Added: {x}" for x in sorted(added)] + [
            f"- Resolved: {x}" for x in sorted(removed)
        ]

    def adjacency(m):
        return {
            tuple(sorted(x for x in w["spaces"] if x))
            for w in m["walls"]
            if all(w["spaces"])
        }

    gained = adjacency(after) - adjacency(before)
    lost = adjacency(before) - adjacency(after)
    lines += [
        "\n## Adjacency diff",
        f"- Gained: {sorted(gained)}",
        f"- Lost: {sorted(lost)}",
        f"\n3D geometry changed: {wall_boxes(before) != wall_boxes(after)}",
        f"Validation: {v['status']}",
        f"Changed outputs: {', '.join(v['outputs_changed'])}",
        f"Unchanged outputs: {', '.join(v['outputs_unchanged'])}",
    ]
    write(Path(a.out) / "consequences.md", "\n".join(lines))
    manifest = load(Path(a.out) / "manifest.json")
    for rel in ("building-spec.modified.json", "consequences.md"):
        manifest["files"][rel] = hashlib.sha256(
            (Path(a.out) / rel).read_bytes()
        ).hexdigest()
    write(Path(a.out) / "manifest.json", manifest)
    print("\n".join(lines))
    return int(v["status"] != "PASS")


def cmd_render(a):
    model = load(a.model)
    v = validate(model)
    if v["status"] != "PASS":
        raise SpecError("cannot render invalid model: " + "; ".join(v["fail"]))
    result = generate(
        model,
        a.out,
        style=a.style,
        view=a.view,
        resolution=tuple(map(int, a.resolution.lower().split("x"))),
        samples=a.samples,
        room=a.room,
        camera=a.camera,
        target=a.target,
        lens=a.lens,
        hide_roof=a.hide_roof,
        execute=a.execute,
        blender=a.blender,
    )
    parent = Path(a.model).resolve().parent
    if (parent / "manifest.json").exists():
        manifest = load(parent / "manifest.json")
        for key in ("script", "payload", "image", "blend", "log"):
            if key in result:
                path = Path(result[key]).resolve()
                if path.is_file() and path.is_relative_to(parent):
                    manifest["files"][str(path.relative_to(parent))] = hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
        manifest["render_status"] = "rendered" if result["executed"] else "script_only"
        manifest["rendered_model_hash"] = digest(model) if result["executed"] else None
        manifest["renderer_hash"] = renderer_hash()
        write(parent / "manifest.json", manifest)
    print(json.dumps(result, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(required=True)
    d = sub.add_parser("design")
    d.add_argument("spec")
    d.add_argument("--out", required=True)
    d.add_argument("--alternatives", type=int, choices=(1, 2, 3), default=3)
    d.set_defaults(f=cmd_design)
    for name in ("concept", "build"):
        b = sub.add_parser(name)
        b.add_argument("spec")
        b.add_argument("--variant", type=int, choices=(1, 2, 3), default=1)
        b.add_argument("--out", required=True)
        b.set_defaults(f=cmd_build, mode=name)
    v = sub.add_parser("validate")
    v.add_argument("model")
    v.set_defaults(f=cmd_validate)
    m = sub.add_parser("modify")
    m.add_argument("spec")
    m.add_argument("--out", required=True)
    m.add_argument("--variant", type=int, choices=(1, 2, 3), default=1)
    m.add_argument("--widen-courtyard", type=float)
    for name in ("ceiling", "skylight", "move-near", "area", "min-width", "material"):
        m.add_argument("--" + name, action="append")
    m.set_defaults(f=cmd_modify)
    r = sub.add_parser("render")
    r.add_argument("model")
    r.add_argument("--out", required=True)
    r.add_argument(
        "--style",
        choices=("clay", "editorial", "daylight", "cinematic", "night"),
        default="daylight",
    )
    r.add_argument(
        "--view",
        choices=("exterior", "interior", "courtyard", "axonometric"),
        default="exterior",
    )
    r.add_argument("--resolution", default="1920x1280")
    r.add_argument("--samples", type=int)
    r.add_argument("--room")
    r.add_argument("--camera", type=float, nargs=3)
    r.add_argument("--target", type=float, nargs=3)
    r.add_argument("--lens", type=float)
    r.add_argument("--hide-roof", action="store_true")
    r.add_argument("--execute", action="store_true")
    r.add_argument("--blender")
    r.set_defaults(f=cmd_render)
    a = ap.parse_args()
    try:
        return a.f(a)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
