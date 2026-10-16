#!/usr/bin/env python3
"""Bundle real example outputs into a portable, offline HTML showcase."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = [
    (
        "courtyard-revised",
        "Courtyard + skylight study",
        "A wider garden, a raised living ceiling, and a roof aperture over the dining room.",
        "courtyard/modified",
        "Revised residence",
    ),
    (
        "courtyard-original",
        "Courtyard residence",
        "The original single-storey brief: three bedrooms, connected living spaces, and a central garden.",
        "courtyard/selected",
        "Original residence",
    ),
    (
        "modern-villa",
        "Two-storey villa",
        "Explore a double-height living space, a courtyard void, and a stair connecting two levels.",
        "villa/selected",
        "Two levels",
    ),
    (
        "commercial",
        "Retail + studio",
        "A small commercial program with retail, café, studio, and service spaces around a shared court.",
        "commercial/selected",
        "Commercial study",
    ),
]
DRAWINGS = [
    ("plan_ground.svg", "Ground floor"),
    ("plan_upper.svg", "Upper floor"),
    ("section.svg", "Section A–A′"),
    ("roof_plan.svg", "Roof plan"),
    ("exploded.svg", "Exploded axonometric"),
] + [
    (f"elevation_{side}.svg", f"{side.title()} elevation")
    for side in ("east", "west", "north", "south")
]
DOWNLOADS = [
    ("model.glb", "3D model", "GLB"),
    ("model.ifc", "BIM model", "IFC"),
    ("plan_ground.dxf", "Ground-floor drawing", "DXF"),
    ("plan_upper.dxf", "Upper-floor drawing", "DXF"),
    ("building-spec.json", "Design brief", "JSON"),
    ("model.json", "Resolved model", "JSON"),
    ("validation.json", "Validation report", "JSON"),
    ("report.md", "Design report", "MD"),
    ("schedule_room.csv", "Room schedule", "CSV"),
    ("schedule_door.csv", "Door schedule", "CSV"),
    ("schedule_window.csv", "Window schedule", "CSV"),
]
RENDERS = [
    (
        "renders/render_daylight_exterior.png",
        "Daylight exterior",
        "Raised living roof and dining skylight.",
    ),
    (
        "renders/render_cinematic_interior.png",
        "Living interior",
        "Layered wood finishes and warm interior lighting.",
    ),
    (
        "renders/render_daylight_courtyard.png",
        "Inside the court",
        "The open garden and surrounding room boundaries.",
    ),
    (
        "renders/render_night_exterior.png",
        "Night exterior",
        "Interior lights, glazing, and roof aperture.",
    ),
    (
        "renders/render_clay_axonometric.png",
        "Clay model",
        "Orthographic massing with neutral materials.",
    ),
    (
        "editorial-check/render_editorial_exterior.png",
        "Editorial exterior",
        "A muted presentation of the same building geometry.",
    ),
]


def read(path):
    return json.loads(path.read_text())


def build(source, destination):
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if not source.is_dir():
        raise ValueError(f"output source is missing: {source}")
    if destination == source or source.is_relative_to(destination):
        raise ValueError("showcase must not contain or replace its source directory")
    previous = (
        read(destination / "bundle.json")
        if (destination / "bundle.json").exists()
        else {}
    )
    if (
        destination.exists()
        and any(destination.iterdir())
        and previous.get("generator") != "architect-showcase"
    ):
        raise ValueError(
            "choose an empty destination or a previously generated showcase"
        )
    with tempfile.TemporaryDirectory(prefix="architect-showcase-") as temporary:
        stage = Path(temporary)
        projects = []

        def copy(origin, relative):
            origin = origin.resolve()
            if not origin.is_relative_to(source):
                raise ValueError("assets must stay inside the source output directory")
            if not origin.is_file():
                raise ValueError(f"missing asset: {origin}")
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
            return relative.as_posix()

        for pid, title, description, folder, tag in PROJECTS:
            folder = source / folder
            model = read(folder / "model.json")
            validation = read(folder / "validation.json")
            manifest = read(folder / "manifest.json")
            if validation["status"] != "PASS":
                raise ValueError(f"{pid}: cannot showcase a failed design")
            expected = hashlib.sha256(
                json.dumps(model, sort_keys=True).encode()
            ).hexdigest()
            if manifest.get("model_hash") != expected:
                raise ValueError(f"{pid}: model provenance mismatch")

            def asset(name):
                path = folder / name
                recorded = manifest.get("files", {}).get(name)
                if (
                    not recorded
                    or hashlib.sha256(path.read_bytes()).hexdigest() != recorded
                ):
                    raise ValueError(
                        f"{pid}: missing/stale artifact {name}; rebuild the example"
                    )
                return copy(path, Path("assets") / pid / name)

            project = {
                "id": pid,
                "title": title,
                "description": description,
                "tag": tag,
                "building": model["meta"]["name"],
                "metrics": validation["metrics"],
                "status": validation["status"],
                "warnings": validation["warn"],
                "constraints": validation.get("constraints", []),
                "levels": len(model["levels"]),
                "spaces": len(model["spaces"]),
                "modelHash": expected,
                "viewer": asset("viewer.html"),
                "drawings": [],
                "renders": [],
                "downloads": [],
            }
            for name, label in DRAWINGS:
                if (folder / name).exists():
                    project["drawings"].append({"label": label, "url": asset(name)})
            for name, label, format_ in DOWNLOADS:
                if (folder / name).exists():
                    project["downloads"].append(
                        {
                            "label": label,
                            "format": format_,
                            "url": asset(name),
                            "bytes": (folder / name).stat().st_size,
                        }
                    )
            for name, label, caption in RENDERS:
                if (folder / name).exists():
                    project["renders"].append(
                        {"label": label, "caption": caption, "url": asset(name)}
                    )
            project["cover"] = (
                project["renders"][0]["url"]
                if project["renders"]
                else project["drawings"][0]["url"]
            )
            projects.append(project)
        alternatives = []
        for index in range(1, 4):
            folder = source / "courtyard/alternatives" / f"alternative-{index}"
            m = read(folder / "model.json")
            v = read(folder / "validation.json")
            if v["status"] != "PASS":
                raise ValueError(f"courtyard alternative {index} failed validation")
            snapshot = read(folder / "manifest.json")
            if (
                snapshot.get("model_hash")
                != hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest()
            ):
                raise ValueError(
                    f"courtyard alternative {index}: model provenance mismatch"
                )
            for name in ("model.json", "validation.json", "plan_ground.svg"):
                if hashlib.sha256(
                    (folder / name).read_bytes()
                ).hexdigest() != snapshot.get("files", {}).get(name):
                    raise ValueError(
                        f"courtyard alternative {index}: stale artifact {name}"
                    )
            path = copy(
                folder / "plan_ground.svg",
                Path("assets/alternatives") / f"plan-{index}.svg",
            )
            alternatives.append(
                {
                    "name": m["meta"]["variant_name"],
                    "number": index,
                    "url": path,
                    "metrics": v["metrics"],
                    "warnings": len(v["warn"]),
                }
            )
        data = {
            "projects": projects,
            "alternatives": alternatives,
            "disclaimer": "Concept design only — requires licensed professional review. Not for construction.",
        }
        payload = (
            json.dumps(data, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        template = (ROOT / "renderers/showcase/index_template.html").read_text()
        (stage / "index.html").write_text(
            template.replace("/*__SHOWCASE_DATA__*/null", payload)
        )
        files = {
            str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in stage.rglob("*")
            if p.is_file()
        }
        (stage / "bundle.json").write_text(
            json.dumps(
                {
                    "generator": "architect-showcase",
                    "schema_version": 1,
                    "projects": [p["id"] for p in projects],
                    "files": files,
                },
                indent=2,
            )
            + "\n"
        )
        # Complete input/asset checks before replacing any previous bundle files.
        for rel in previous.get("files", {}):
            if Path(rel).is_absolute() or ".." in Path(rel).parts:
                raise ValueError("invalid bundle manifest path")
        destination.mkdir(parents=True, exist_ok=True)
        for path in stage.rglob("*"):
            if path.is_file():
                target = destination / path.relative_to(stage)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.read_bytes() != path.read_bytes():
                    shutil.copyfile(path, target)
        for rel, oldhash in previous.get("files", {}).items():
            old = destination / rel
            if (
                rel not in files
                and old.is_file()
                and hashlib.sha256(old.read_bytes()).hexdigest() == oldhash
            ):
                old.unlink()
    size = sum((destination / rel).stat().st_size for rel in files)
    return {
        "index": str(destination / "index.html"),
        "projects": len(projects),
        "files": len(files),
        "size_mb": round(size / 1024**2, 1),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "out")
    parser.add_argument("--out", type=Path, default=ROOT / "examples/showcase")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.source, args.out), indent=2))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
