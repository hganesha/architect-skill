# Workflow details

All commands below use `<python>` for the skill's `.venv/bin/python` and
`<architect>` for the absolute path to `tools/architect.py`. Spec paths and output
paths are user-selected; supporting assets always resolve relative to this skill.

## Quick concept and alternatives

```
<python> <architect> concept brief.json --out concept/
<python> <architect> design brief.json --alternatives 3 --out alternatives/
<python> <architect> build brief.json --variant 2 --out selected/
```

The three variants adjust courtyard aspect/position; courtyard-free designs adjust
massing. Layout optimization weighs adjacency, room proportions, area fit and wet
room proximity. Circulation is an explicit space allocation. Required constraints
remain hard even when the heuristic cannot satisfy them. A comparison includes
status, enclosed area, mean fractional area deviation, daylit/habitable counts,
realized/requested adjacency, circulation area and validation counts. A failed
alternative emits diagnostics and makes `design` exit nonzero. Review feasible
alternatives individually; do not automatically relax requirements.

## Intent examples

```json
{
  "id": "living", "name": "Living", "level": "ground",
  "type": "room", "zone": "public", "target_area": 40,
  "open_plan_group": "day-spaces", "adjacent_to": ["dining"],
  "min_width": 3, "min_depth": 4, "max_area_deviation": 0.35,
  "materials": {"floor": "maple", "wall": "wood_slat"},
  "furniture": [{"id": "sofa", "width": 2.1, "depth": 0.9,
                 "height": 0.8, "clearance": 0.6, "required": true}]
}
```

Furniture `x`/`y` are offsets from the room's south-west corner; omitted offsets
center the item. Clearance is a concept envelope on all sides. Required explicit
furniture failures block output; optional pack items that cannot fit are omitted.
Furniture is furniture massing, not detailed manufacturer assets.

Constraints: adjacency (two `spaces`), daylight/skylight (`target`), privacy
(`target`, `spaces`, or all private rooms), max_footprint (`value` area),
wet_grouping (ordered same-level shared-edge `spaces`), wet_stacking (ordered
spaces on different levels with overlapping footprints). Each accepts `required`
and `priority`. A preference that is missed becomes a warning; a missed hard
constraint fails the build. Wet checks do not verify plumbing systems.

`building.units: feet` converts dimensional inputs, including room areas,
elevations, furniture, camera positions, section position and footprint limits.
Omitted engine defaults and material fields ending `_m` are already SI.
The persisted spec after an edit is normalized SI. Edit flags always use SI.

## Edits and provenance

```
<python> <architect> modify selected/building-spec.json --variant 2 \
  --widen-courtyard 1.25 --ceiling living=4.87 --skylight dining --out revised/
```

Courtyard widening preserves depth and multiplies width; the resulting aspect is
saved in the spec. Moving near a space adds a required shared-edge adjacency,
which may reflow other spaces. The planner does not currently lock arbitrary
existing coordinates. `consequences.md` lists moved rectangles, ceiling and area
changes, gained/lost adjacencies, validation changes and changed/unchanged outputs.
Wall/opening IDs derive from semantic hosts instead of coordinate positions;
topology changes can still create or remove IDs.

`manifest.json` records model/spec/pipeline hashes and artifact hashes. The CLI
preflights ownership before overwriting generated files. Unrelated files are kept.
A model failure replaces managed presentation files with diagnostics. Managed
render artifacts invalidated by a rebuild move under `stale-renders/<old-hash>/`.
A repeated identical build reuses verified artifacts. Never present an archived
render as representing the current model.

## Drawing controls

```json
{"drawing": {"section": {"axis": "x", "position": 12.5}}}
```

`axis: x` cuts at constant Y; `axis: y` cuts at constant X. Default section passes
through the courtyard center, or footprint center. All section solids must
intersect that plane. The plan marks the same cut. SVG carries overall/room
sizes, a dimension chain, scale bar, north arrow, room key and date. DXF has metre
units, layer-separated cut walls/openings, door arcs and dimension entities.
Drawn room bounds do not deduct wall thickness for a certified net area.

## Render controls

```
<python> <architect> render selected/model.json --out selected/renders \
  --view interior --room living --style cinematic --resolution 1600x1000 \
  --samples 128 --execute --blender /path/to/blender
```

Additional controls: `--camera X Y Z`, `--target X Y Z`, `--lens 24`, `--hide-roof`.
Coordinates are absolute SI in the model's X east/Y north/Z up frame. Camera presets
can be persisted in `render.cameras.exterior` and `.interior`, each with `position`,
`target`, `lens`; `render.room` chooses an interior room. Courtyard view requires a
courtyard. Unknown rooms/styles and invalid sizes fail explicitly. Blender output
logs are saved beside the generated script. A successful command verifies PNG
creation; the agent must also visually inspect composition and geometry.

## Interoperability and checks

GLB uses outward triangles, explicit face normals, PBR factors, metre coordinates
converted from Z up to glTF Y up, and semantic IDs in node extras. IFC4 uses
IfcOpenShell, stable GUIDs, project/site/building/storey hierarchy, SI units,
placements, geometric representations, hosted opening relationships and fillings.
IFC spaces are concept room volumes; finishes and stair geometry are separate
products. Use `ifcopenshell.validate` and a geometry iterator when changing IFC.

The built-in viewer is offline and has orbit, pan, zoom, fit, roof visibility,
level filtering, exploded floors, room selection by ray intersection, and free
WASD/QE walking. Walking is a navigation tool, not collision or accessibility
simulation. Test at high device pixel ratio as well as normal desktop sizing.
