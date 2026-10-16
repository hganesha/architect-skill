# Concept drawing standards

All linework derives from resolved model geometry. SVG and DXF plan walls are
horizontal cuts of the same solids used in 3D. Door gaps, leaves and quarter-circle
swing arcs share hosted positions; windows occupy real wall apertures.

Plans include room name/area/size or a numbered room key for small spaces,
overall dimensions, a boundary dimension chain, north arrow, scale bar and section
cut indicator. Furniture is optional concept massing. DXF sets metre units and
uses layers for walls, openings, furniture, stairs, labels and dimension entities.
Room dimensions follow room boundary rectangles; they are not certified clear
internal dimensions after deducting wall and finish thicknesses.

Full sets include four orthographic elevations, an actual X/Z or Y/Z cut-plane
section, roof surfaces/apertures, a geometric exploded axonometric, and CSV schedules.
Section position/axis can be specified through `drawing.section`. Only solids that
intersect the section plane are drawn. Heights use explicit level elevations and
space ceilings. Roofs and skylights follow actual exported geometry.

Every sheet includes project/drawing identity, date, metric notation, a scale note
and concept disclaimer. The scale bar governs when displayed or printed at a
changed size. These are concept sheets, not a permit or construction set.
