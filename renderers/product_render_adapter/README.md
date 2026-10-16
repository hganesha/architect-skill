# Optional presentation handoff

`adapter.py` emits a JSON brief containing the canonical model path, compiled
boxes, spaces, material assignments and requested views. It does not invoke an
external skill or assume one is installed. The built-in Blender renderer can
produce exterior, interior, courtyard and axonometric views directly.

A downstream renderer may change camera, lighting and presentation. Building
geometry changes must return through the canonical model and be recompiled.
Use the source model hash to identify which revision a still represents.
