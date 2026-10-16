"""Validate public contracts before resolving geometry, then normalize to SI."""

import copy
import json
import math
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


class SpecError(ValueError):
    pass


def check_schema(data, name="building-spec"):
    schema = json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text())
    errors = sorted(
        Draft202012Validator(schema).iter_errors(data), key=lambda e: str(list(e.path))
    )
    if errors:
        raise SpecError(
            "; ".join(
                f"{'.'.join(map(str, e.path)) or '$'}: {e.message}" for e in errors[:12]
            )
        )


def normalize(spec):
    check_schema(spec)
    s = copy.deepcopy(spec)
    units = s["building"].get("units", "meters")
    factor = 0.3048 if units == "feet" else 1.0

    def scale(obj, keys, power=1):
        for k in keys:
            if k in obj:
                obj[k] *= factor**power

    scale(s["site"], ("width", "depth"))
    scale(s["site"].get("setbacks", {}), ("east", "west", "north", "south"))
    previous_top = 0.0
    level_ids = []
    for lv in s["levels"]:
        scale(lv, ("height", "elevation"))
        lv.setdefault("elevation", previous_top)
        if lv["id"] in level_ids:
            raise SpecError(f"duplicate level id: {lv['id']}")
        if level_ids and lv["elevation"] < previous_top - 0.002:
            raise SpecError("levels must be ordered with non-overlapping elevations")
        level_ids.append(lv["id"])
        previous_top = lv["elevation"] + lv["height"]
    ids = [p["id"] for p in s["spaces"]]
    if len(ids) != len(set(ids)):
        raise SpecError("space IDs must be unique")
    for p in s["spaces"]:
        p.setdefault("level", level_ids[0])
        if p["level"] not in level_ids:
            raise SpecError(f"{p['id']}: unknown level {p['level']}")
        scale(p, ("target_area",), 2)
        scale(p, ("min_width", "min_depth", "ceiling_height"))
        for f in p.get("furniture", []):
            scale(f, ("x", "y", "width", "depth", "height", "clearance"))
        for target in p.get("adjacent_to", []) + ([p["near"]] if p.get("near") else []):
            if target not in ids or target == p["id"]:
                raise SpecError(f"{p['id']}: invalid space reference {target}")
    for c in s.get("constraints", []):
        refs = c.get("spaces", []) + ([c["target"]] if c.get("target") else [])
        if any(x not in ids for x in refs):
            raise SpecError(f"unknown constraint space: {refs}")
        if c["type"] == "adjacency" and len(c.get("spaces", [])) != 2:
            raise SpecError("adjacency constraint needs exactly two spaces")
        if c["type"] in ("daylight", "skylight") and not c.get("target"):
            raise SpecError(f"{c['type']} constraint needs target")
        if (
            c["type"] in ("wet_grouping", "wet_stacking")
            and len(c.get("spaces", [])) < 2
        ):
            raise SpecError(f"{c['type']} constraint needs at least two spaces")
        if c["type"] == "max_footprint":
            if "value" not in c:
                raise SpecError("max_footprint constraint needs value")
            c["value"] *= factor**2
        if c["type"] == "skylight":
            next(p for p in s["spaces"] if p["id"] == c["target"])["skylight"] = True
    scale(s.get("planning", {}), ("circulation_width",))
    section = s.get("drawing", {}).get("section", {})
    scale(section, ("position",))
    for key in ("exterior", "interior"):
        camera = s.get("render", {}).get("cameras", {}).get(key, {})
        for k in ("position", "target"):
            if k in camera:
                camera[k] = [v * factor for v in camera[k]]
    room = s.get("render", {}).get("room")
    if room and room not in ids:
        raise SpecError(f"unknown render room: {room}")
    s["building"]["units"] = "meters"
    s["building"]["input_units"] = spec["building"].get("input_units", units)

    # JSON parsers admit NaN/Infinity; geometries must not.
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise SpecError("numbers must be finite")
        if isinstance(value, dict):
            for x in value.values():
                finite(x)
        if isinstance(value, list):
            for x in value:
                finite(x)

    finite(s)
    return s
