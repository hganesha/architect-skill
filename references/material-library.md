# Material Library — primitives

A material primitive = category + PBR values + finish + a **pattern behaviour**.
It is consumed identically by the GLB exporter (geometry + metallic/roughness),
the WebGL viewer (colour), and Blender (procedural nodes), so a material change
in the model propagates to plan legend, 3D and renders at once.

Pattern behaviours with *geometric* effect in the exporter:
- `standing_seam` — raised seam ribs added across roof slabs (spacing/height from the primitive)
- `slat` — wall pieces segmented into battens with shadow gaps (width/gap/depth from the primitive)

All other patterns (`grain`, `veined`, `brushed`, `noise`, `speckle`, `brick`)
drive Blender procedural textures and PBR values in GLB.

Assign in a BuildingSpec at building level
(`materials: {exterior: stucco, flooring: maple, roof: standing_seam_metal}`)
or per space (`spaces[].materials: {floor: marble, wall: wood_slat}`).
Values may be a catalog id, an alias (`pipe_wood`, `timber`, `stainless`),
or an inline override (`{"id": "maple", "roughness": 0.35}`).
Source of truth: `materials/catalog.json` (schema: `schemas/material.schema.json`).

| id | Material | Category | Finish | Pattern | Typical use |
|---|---|---|---|---|---|
| `standing_seam_metal` | Standing Seam Metal | metal | matte zinc / charcoal | standing_seam | roof, exterior_wall |
| `pine_wood` | Pine Wood | wood | clear matte, visible soft grain | grain | floor, interior_wall, ceiling, joinery |
| `stucco` | Stucco | plaster | fine sand texture | noise | exterior_wall, interior_wall |
| `wood_slat` | Wood Slat Screen | wood_screen | oiled timber battens with shadow gaps | slat | exterior_wall, feature_wall, screen, ceiling |
| `marble` | Marble | stone | polished, grey-gold veining | veined | floor, bath_wall, counter |
| `quartz` | Quartz (Engineered Stone) | stone | honed, fine aggregate speckle | speckle | counter, floor, bath_wall |
| `stainless_steel` | Stainless Steel | metal | brushed, hairline grain | brushed | counter, fixture, cladding, appliance |
| `maple` | Maple | wood | satin, pale even grain | grain | floor, joinery, stair, interior_wall |
| `oak` | Oak | wood | natural oil, pronounced grain | grain | floor, joinery, stair |
| `teak` | Teak | wood | natural oil, golden brown | grain | floor, exterior_screen, joinery |
| `walnut` | Walnut | wood | satin, dark chocolate grain | grain | joinery, feature_wall, floor |
| `natural_stone` | Natural Stone | stone | split-face / roughly dressed | noise | exterior_wall, landscape_wall |
| `limestone` | Limestone | stone | honed, warm ivory | noise | floor, exterior_wall |
| `travertine` | Travertine | stone | filled, linear pitting | grain | floor, bath_wall |
| `concrete` | Polished Concrete | mineral | polished, subtle trowel variation | noise | floor, counter |
| `lime_plaster` | Lime Plaster | plaster | hand-troweled, soft variation | noise | interior_wall, ceiling |
| `terracotta` | Terracotta | ceramic | matte fired clay | flat | floor, roof_tile, screen |
| `brick` | Brick | masonry | stretcher bond, lime mortar | brick | exterior_wall, interior_wall |
| `blackened_steel` | Blackened Steel | metal | blackened, waxed | brushed | fixture, frame, cladding |
| `brass` | Brass | metal | brushed, unlacquered | brushed | fixture, trim, hardware |
| `glass` | Glass | glass | clear low-iron | flat | window, door_lite, balustrade |
| `courtyard_green` | Courtyard Planting / Gravel | landscape | planting and gravel (concept) | noise | courtyard, landscape |
