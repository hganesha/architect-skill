"""Material primitives.

A material is NOT just a colour swatch. Each primitive carries:
  category · PBR (base colour, roughness, metalness) · finish · a *pattern
  behaviour* · typical applications.

Pattern behaviours are consumed downstream, from the same primitive:
  standing_seam -> raised seam ribs are added to roof geometry (exporter)
  slat          -> wall pieces are segmented into battens with shadow gaps
  grain/veined/brushed/noise/speckle/brick -> procedural nodes in Blender,
                   colour + roughness/metalness in GLB and the WebGL viewer

Source of truth for the catalog: materials/catalog.json (agent-editable).
Resolve by id ("marble"), alias ("pipe_wood" -> pine_wood, "timber" -> oak),
or an inline override dict {"id": "maple", "color": [...], "roughness": 0.4}.
Unknown free-text names (e.g. "timber + flat slab") fall back gracefully to a
neutral material that *keeps the original text* so nothing is silently lost.
"""

from __future__ import annotations
import json, os
from dataclasses import dataclass, field

_CATALOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "materials", "catalog.json"
)


def _load():
    try:
        raw = json.load(open(_CATALOG_PATH))
    except Exception:
        return {}, {}
    mats = {k: v for k, v in raw.items() if not k.startswith("_")}
    aliases = {}
    for mid, m in mats.items():
        for a in m.get("aliases", []):
            aliases[a] = mid
        aliases[mid] = mid
        aliases[m["name"].lower().replace(" ", "_")] = mid
    return mats, aliases


CATALOG, ALIASES = _load()

FALLBACK_COLOR = [0.85, 0.82, 0.76, 1]


@dataclass
class Material:
    id: str
    name: str
    category: str = "generic"
    color: list = field(default_factory=lambda: list(FALLBACK_COLOR))
    roughness: float = 0.8
    metalness: float = 0.0
    finish: str = ""
    pattern: dict = field(default_factory=lambda: {"type": "flat"})
    typical_use: list = field(default_factory=list)
    specified_as: str = ""  # original free text, if the id was not in the catalog

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "color": self.color,
            "roughness": self.roughness,
            "metalness": self.metalness,
            "finish": self.finish,
            "pattern": self.pattern,
            "typical_use": self.typical_use,
            **({"specified_as": self.specified_as} if self.specified_as else {}),
        }


def resolve_material(spec, default_id="stucco") -> Material:
    """spec: catalog id | alias | inline dict | free text | None."""
    if spec is None:
        spec = default_id
    if isinstance(spec, dict):
        base = resolve_material(
            spec.get("id") or spec.get("name") or default_id, default_id
        )
        for k in (
            "color",
            "roughness",
            "metalness",
            "finish",
            "pattern",
            "name",
            "category",
        ):
            if k in spec:
                setattr(base, k, spec[k])
        from .inputs import check_schema

        check_schema(base.to_dict(), "material")
        return base
    key = str(spec).strip().lower().replace(" ", "_").replace("-", "_")
    mid = ALIASES.get(key)
    if mid and mid in CATALOG:
        m = CATALOG[mid]
        return Material(
            id=mid,
            name=m["name"],
            category=m.get("category", "generic"),
            color=list(m.get("color", FALLBACK_COLOR)),
            roughness=m.get("roughness", 0.8),
            metalness=m.get("metalness", 0.0),
            finish=m.get("finish", ""),
            pattern=dict(m.get("pattern", {"type": "flat"})),
            typical_use=list(m.get("typical_use", [])),
        )
    base = (
        resolve_material(default_id, "stucco")
        if default_id != "stucco"
        else Material(
            id="stucco",
            name="Stucco",
            category="plaster",
            color=[0.93, 0.90, 0.84, 1],
            roughness=0.95,
        )
    )
    base.specified_as = str(spec)
    return base


def material_for_surface(
    model: dict, surface: str, space: dict | None = None
) -> Material:
    """Assignment rules: per-space override > building materials > defaults.

    surface: exterior_wall | interior_wall | floor | roof | courtyard
    Space overrides: space['materials'] = {'floor': 'marble', 'wall': 'wood_slat'}
    Building spec:   model['materials'] = {'exterior': ..., 'interior': ...,
                                           'flooring': ..., 'roof': ...}
    """
    mats = model.get("materials", {}) or {}
    if space and isinstance(space.get("materials"), dict):
        key = {"floor": "floor", "interior_wall": "wall", "exterior_wall": "wall"}.get(
            surface
        )
        if key and space["materials"].get(key):
            return resolve_material(space["materials"][key])
    defaults = {
        "exterior_wall": ("exterior", "natural_stone"),
        "interior_wall": ("interior", "lime_plaster"),
        "floor": ("flooring", "limestone"),
        "roof": ("roof", "concrete"),
        "courtyard": ("courtyard", "courtyard_green"),
    }
    key, dflt = defaults.get(surface, (None, "stucco"))
    return resolve_material(mats.get(key), dflt)


def catalog_markdown() -> str:
    lines = [
        "| id | Material | Category | Finish | Pattern | Typical use |",
        "|---|---|---|---|---|---|",
    ]
    for mid, m in CATALOG.items():
        pat = m.get("pattern", {}).get("type", "flat")
        lines.append(
            f"| `{mid}` | {m['name']} | {m.get('category', '')} | {m.get('finish', '')} | {pat} | {', '.join(m.get('typical_use', []))} |"
        )
    return "\n".join(lines)
