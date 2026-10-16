# Validation rules

FAIL blocks presentation exports and returns a nonzero CLI status:

- Invalid schema, duplicate IDs, unresolved references or invalid units/dimensions.
- Overlapping rooms, footprint violations, geometry/area mismatch, incomplete tiling.
- Occupied space intersecting courtyard, double-height or stair voids; vertical collisions.
- No exterior entrance or any modeled space unreachable through doors/passages/stairs.
- Missing opening host, aperture outside its wall/roof, opening collisions or a skylight
  blocked by an upper floor.
- A level with no arriving stair, missing shaft/landing, or U-stair geometry that cannot fit.
- Missed `required` constraints, explicit room minima/area tolerances, or required furniture
  whose geometry/clearance does not fit.

WARN is reported and may need design iteration:

- Room area deviation greater than 25% without a hard tolerance; narrow dimensions.
- Missed preferred adjacency, disconnected open-plan groups, access through another private
  room, or concept circulation dead ends.
- Habitable rooms without exterior/courtyard glazing or a skylight. This is a daylight
  availability proxy, not an illumination or energy simulation.
- Stair riser outside the documented concept range, optional furniture clearance conflicts,
  or unknown materials using a named neutral fallback.

Required constraints are never silently downgraded. A `PASS` is limited to these
concept checks and can include design-quality warnings. The solver is a heuristic;
its failure is not proof that no feasible building design exists.

Not checked: governing building codes, fire safety, structural adequacy, accessibility
compliance, engineering systems, certified net floor area, energy performance or cost.

Concept design only — requires licensed professional review. Not for construction.
