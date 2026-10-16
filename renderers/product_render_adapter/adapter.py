"""Adapter to a product-render skill (exploded/editorial stills).

Contract: Architect owns geometry truth; the product-render skill owns visual
composition (camera, lighting, materials, exploded assemblies). It receives
model.json + boxes and must return images WITHOUT altering geometry. Any
geometry change goes back through the canonical model, never the render.
"""

import json, os, sys, hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from engines.bim_exporter.exporters import wall_boxes


def handoff(model_path, out_dir, style="editorial", explode=0.6):
    model = json.load(open(model_path))
    os.makedirs(out_dir, exist_ok=True)
    brief = {
        "source_of_truth": os.path.abspath(model_path),
        "model_hash": hashlib.sha256(
            json.dumps(model, sort_keys=True).encode()
        ).hexdigest(),
        "rule": "Render these boxes exactly; do not invent, move or resize geometry.",
        "boxes": wall_boxes(model),
        "spaces": model["spaces"],
        "materials_spec": model.get("materials", {}),
        "requested": {
            "style": style,
            "explode_factor": explode,
            "views": ["exploded_axonometric", "exterior_3q", "courtyard_interior"],
        },
        "disclaimer": model["meta"].get("disclaimer", ""),
    }
    p = os.path.join(out_dir, "product_render_brief.json")
    json.dump(brief, open(p, "w"), indent=1)
    return p


if __name__ == "__main__":
    print(handoff(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "product_render"))
