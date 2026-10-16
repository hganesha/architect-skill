---
name: architect
description: Create editable concept building designs with coordinated floor plans, elevations, sections, 3D models, IFC exports and Blender renders. Use for space planning, building alternatives, architectural drawing sets and conversational geometry or material edits. Does not produce certified construction documents.
---

# Architect

The resolved `model.json` is the source of truth. Drawings, meshes and renders
compile from its coordinates and relationships. Never use image generation to
invent dimensioned linework or claim an edit changed geometry without checking it.

## Included examples

Users can inspect actual outputs in [the example studio](examples/showcase/index.html):
four studies, renders, drawings, embedded 3D, validation warnings, and model/CAD
file downloads. Share the entire `examples/showcase/` directory so relative assets
remain available. Refresh it with `tools/build_showcase.py` after regenerating the
example snapshots; see [README](README.md#browse-the-examples).

## Runtime and paths

Resolve this skill's root from the location of this file, **not the user's current
working directory**. Run `<skill-root>/.venv/bin/python <skill-root>/tools/architect.py`.
If the local environment is missing, use Python 3.12 to create `.venv` in the skill
root and install `<skill-root>/requirements.txt`. Dependencies include JSON Schema,
IfcOpenShell and ezdxf. Do not silently fall back to placeholder IFC or CAD files.
Blender 4.5 LTS or later is required only to execute a render script.

## Choose the requested mode

| Request | Action |
|---|---|
| Quick concept or one layout | `concept <spec.json> --out <dir>` |
| Explore alternatives | `design <spec.json> --alternatives 3 --out <dir>` (1–3 supported) |
| Coordinated drawing/model set | `build <spec.json> --variant 1 --out <dir>` |
| Change an existing design | `modify <latest-building-spec.json> ... --out <dir>` |
| Render an existing model | `render <model.json> --view exterior --style daylight --out <dir>` |
| Check a model | `validate <model.json>` |

Do not force alternatives or a selection round for a small edit, a render request,
or a user who already specified a design. When alternatives are requested, compare
trade-offs in `comparison.md`; use the user's selection or authorization to choose.

## Brief and intent

Encode the brief using [BuildingSpec](schemas/building-spec.schema.json). Ask only
for missing essentials that block a useful concept; record assumptions. If input
uses `building.units: feet`, lengths are feet and areas are square feet. The engine
normalizes all dimensions and elevations to metres; resolved geometry is always SI.
Material pattern fields ending in `_m` remain metres. CLI edit dimensions are SI.

Read [architectural grammar](references/architectural-grammar.md) for planning work
and [drawing standards](references/drawing-standards.md) for a drawing set.

- `adjacent_to` and `near` are preferences; `constraints[].required: true` is hard.
- Use `open_plan_group` for spaces joined by wide open passages.
- Use `min_width` (shorter side), `min_depth` (longer side) and
  `max_area_deviation` (fraction) for explicit hard room requirements.
- `planning.circulation_width` budgets real galleries. `planning.furnish` enables
  optional furniture packs. Explicit room furniture can specify clearance and
  `required: true`; see [workflow details](references/workflows.md).
- Materials are catalog IDs, aliases or validated overrides; read
  [material library](references/material-library.md) when assigning them. Unknown
  names produce an explicit fallback warning. Slats are finishes over solid walls.

## Build, inspect, deliver

A successful concept emits `model.json`, `building-spec.json`, `validation.json`,
`report.md`, `plan_<level-id>.svg`, `model.glb`, `viewer.html`, Blender scripts and
`manifest.json`. A full build also emits dimensioned DXF, four elevations,
`section.svg`, `roof_plan.svg`, `exploded.svg` and room/door/window CSV schedules.

CLI failures return nonzero. Invalid models produce diagnostics, never a new
presentation set. Read the actual FAIL and WARN lists. Do not describe a failed
alternative as viable or claim the heuristic solver proves feasibility.

Inspect at least a plan, the viewer and the relevant edited drawing/render. Confirm
an exterior entrance and room reachability, open-plan connections, courtyard/vertical
voids, stairs/landings, roof apertures and dimensions. Check the metrics against the
brief; `PASS` means concept geometry passed these checks, not design approval.
See [validation rules](references/validation-rules.md) for exact coverage.

For edits, start from the latest saved `building-spec.json`. Available flags:
`--ceiling living=4.87`, `--skylight dining`, `--widen-courtyard 1.25` (width factor),
`--area study=14`, `--min-width bedroom-2=2.8`, `--move-near bedroom-2=courtyard`
(required adjacency), `--material exterior=stucco`. Reject unknown IDs; never claim
arbitrary coordinate movement is supported. Read `consequences.md` for spatial,
area, adjacency and validation changes. Regenerated files preserve identical content;
unchanged whole builds are cached. Previous managed render files are archived when
invalidated; execute renders again after changing the model.

## Renders

`render` generates a portable `.py` + `.json` pair. Add `--execute` and, if needed,
`--blender <executable>` to produce `.png`, editable `.blend` and `.log`. Verify the
PNG exists and inspect it before calling the render complete. Supported styles:
clay, editorial, daylight, cinematic, night. Views: exterior, interior, courtyard,
axonometric. Camera, target, room, lens, resolution and samples are configurable;
see [workflow details](references/workflows.md). Night/cinematic include interior
lights; clay changes materials. Presentation styling must preserve geometry.

## Limits

Rectangular sites/spaces, one ground courtyard, flat roofs and U-shaped stairs.
Layouts use deterministic local optimization and can be infeasible. Daylight,
privacy, circulation and furniture checks are concept proxies, not simulations.
Room areas follow room boundary rectangles; they are not certified net floor areas.
IFC is a geometric concept handoff, not a complete authored BIM discipline model.
Explicitly report unsupported geometry instead of approximating it silently.

Every presentation includes: “Concept design only — requires licensed professional
review. Not for construction.” Do not claim code, engineering, permit or construction
readiness. Keep technical setup details in delivery notes, outside the design itself.
