# Architect

An agent skill for editable concept buildings. One canonical model compiles into
coordinated SVG/DXF drawings, GLB, geometric IFC4, an offline 3D viewer, and Blender
render scripts. Edits change model geometry and report consequences.

## Setup

Python 3.12 is the tested runtime. Dependencies live in a project-local environment:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Runtime dependencies: jsonschema, IfcOpenShell and ezdxf. Development dependencies
add pytest, PyYAML and Ruff. Blender 4.5 LTS or later is needed only for PNG/.blend
rendering. Supply its executable with `--blender` if it is not on PATH.

## Browse the examples

Open [the example studio](examples/showcase/index.html) in a browser. The bundled
HTML explorer includes four studies, six Blender renders, an embedded interactive
3D viewer, per-level plans and drawing sets, validation warnings, and downloads
for GLB, IFC, DXF, schedules, model JSON and design briefs. Three courtyard layout
alternatives can also be compared visually.

The complete portable bundle is in `examples/showcase/` (about 20 MB), including
its relative `assets/` directory. It has no CDN, account, API or build dependency.
Share or host that entire directory rather than just its `index.html`. The example
outputs are included outside the ignored `out/` directory.

For a local HTTP preview, including browsers that disallow local-file URLs:

```sh
python3 -m http.server 8764 --bind 127.0.0.1 --directory examples/showcase
```

Then open `http://127.0.0.1:8764/`. Stop the server with Ctrl+C.

To refresh the bundle from generated outputs, run:

```sh
.venv/bin/python tools/build_showcase.py --source out --out examples/showcase
```

The builder reads `out/courtyard/selected`, `out/courtyard/modified`,
`out/villa/selected`, `out/commercial/selected`, and the three alternatives under
`out/courtyard/alternatives/alternative-1` through `alternative-3`. It verifies
snapshot provenance and asset hashes before updating the bundle. Render PNGs are
included when present; unexecuted Blender scripts are not presented as renders.
Edit `renderers/showcase/index_template.html` to change the container design;
`index.html` and `bundle.json` are generated. Large editable `.blend` scenes and
renderer logs are kept out of the portable bundle.

## Use

```sh
.venv/bin/python tools/architect.py concept examples/courtyard-house/building-spec.json --out out/concept
.venv/bin/python tools/architect.py design examples/courtyard-house/building-spec.json --out out/alternatives
.venv/bin/python tools/architect.py build examples/courtyard-house/building-spec.json --variant 1 --out out/selected
.venv/bin/python tools/architect.py modify out/selected/building-spec.json --ceiling living=4.87 --skylight dining --widen-courtyard 1.25 --out out/revised
.venv/bin/python tools/architect.py render out/revised/model.json --out out/revised/renders --view exterior --style daylight --execute --blender /path/to/blender
.venv/bin/python tools/architect.py validate out/revised/model.json
.venv/bin/python -m pytest tests -q
```

Use absolute executable/script paths when invoking from another working directory.
Full command help is available with `tools/architect.py <command> --help`.
See [workflow details](references/workflows.md) for input units, constraints,
open-plan groups, minimum dimensions, furniture, cameras, sections and edit flags.

## Outputs and failure behavior

Concepts include per-level plans, model/spec JSON, GLB, viewer, render scripts,
validation/report and a provenance manifest. Full builds add four elevations,
a true cut-plane section, roof plan, geometric exploded view, layered dimensioned
DXF, IFC4 and room/door/window schedules. Render execution creates PNG, editable
Blender scenes and logs. Scripts plus their adjacent JSON payloads are portable.

Invalid input or failed hard constraints return nonzero. Geometrically invalid
models emit diagnostics instead of a new drawing/render set. Warnings remain
visible even when validation passes. Alternative comparisons report actual area,
daylight, adjacency and circulation metrics. Repeated verified builds are cached;
identical artifacts are not rewritten. Invalidated managed renders are archived.

## Scope

Rectangular sites and spaces, one ground courtyard, flat roofs, U-shaped stairs,
and a deterministic heuristic layout optimizer. Upper floors preserve exact
courtyard/double-height/stair voids. Walls, slabs, roofs, openings, finishes,
frames, doors and stair treads share compiled geometry across viewers/exporters.
Materials include catalog primitives, per-room finishes and validated overrides.

Layouts can be infeasible and preferences may remain unmet. Furniture and
landscape are concept massing. Daylight, privacy and circulation are proxies;
room areas use room boundary rectangles. IFC is a geometric concept handoff,
not a complete discipline BIM model. No structural, code, energy or permit
certification is provided.

Concept design only — requires licensed professional review. Not for construction.
