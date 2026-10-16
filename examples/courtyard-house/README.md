# Acceptance test — Courtyard Residence

Brief (natural language): *"Design a 2,500 ft² courtyard residence with three
bedrooms, an open-plan living area, and a central garden."* — encoded as
`building-spec.json` (site 70 × 110 ft ≈ 21.3 × 33.5 m, entrance east).

```bash
cd architect-skill
# 1. Three viable alternatives, each with dimensioned plan + matching 3D model
 .venv/bin/python tools/architect.py design examples/courtyard-house/building-spec.json --out out/courtyard --alternatives 3
# 2. Select alternative 1 and generate the full set (elevations, section, roof,
#    exploded axonometric, schedules, GLB, IFC, interactive viewer, Blender script)
 .venv/bin/python tools/architect.py build examples/courtyard-house/building-spec.json --variant 1 --out out/courtyard/selected
# 3. Modification test: widen courtyard by a width factor, raise living ceiling, skylight over dining
 .venv/bin/python tools/architect.py modify examples/courtyard-house/building-spec.json \
  --widen-courtyard 1.25 --ceiling living=4.87 --skylight dining --out out/courtyard/modified
# 4. Automated acceptance checks
.venv/bin/python -m pytest tests -q
```

Expected: a real exterior entrance, reachable rooms, no overlapping spaces, every opening hosted inside its wall, plan /
GLB / elevations compiled from the same `model.json`, and `consequences.md`
reporting exactly which areas changed after the edit. Validation WARNs are
disclosed, never hidden. Concept design only — not for construction.

Renders: run `tools/architect.py render <model.json> --out <renders> --execute --blender <executable>` using the virtual environment. Script generation alone does not produce an image.
