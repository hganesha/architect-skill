"""IFC4 with real geometry, stable GUIDs, spatial hierarchy and hosted openings."""

from collections import defaultdict
import json
import uuid
import numpy as np
import ifcopenshell
import ifcopenshell.api as api
from ..building_model.geometry import rect, level_bases
from ..building_model.model import Wall


def write_ifc(model, path):
    from .exporters import wall_boxes, _CUBE, _FACES

    f = api.run("project.create_file", version="IFC4")

    def entity(kind, name, semantic=None):
        e = api.run("root.create_entity", f, ifc_class=kind, name=name)
        e.GlobalId = ifcopenshell.guid.compress(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"architect/{model['meta']['name']}/{kind}/{semantic or name}",
            ).hex
        )
        return e

    project = entity("IfcProject", model["meta"]["name"])
    api.run(
        "unit.assign_unit",
        f,
        length={"is_metric": True, "raw": "METERS"},
        area={"is_metric": True, "raw": "METERS"},
        volume={"is_metric": True, "raw": "METERS"},
    )
    context = api.run("context.add_context", f, context_type="Model")
    body = api.run(
        "context.add_context",
        f,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=context,
    )
    site = entity("IfcSite", "Site")
    building = entity("IfcBuilding", model["meta"]["name"])
    api.run("aggregate.assign_object", f, products=[site], relating_object=project)
    api.run("aggregate.assign_object", f, products=[building], relating_object=site)
    for e in (site, building):
        api.run("geometry.edit_object_placement", f, product=e, matrix=np.eye(4))
    storeys = {}
    for lv in model["levels"]:
        e = entity("IfcBuildingStorey", lv["id"])
        e.Elevation = float(lv["elevation"])
        storeys[lv["id"]] = e
        api.run("aggregate.assign_object", f, products=[e], relating_object=building)
        matrix = np.eye(4)
        matrix[2, 3] = lv["elevation"]
        api.run("geometry.edit_object_placement", f, product=e, matrix=matrix)

    def props(e, values):
        p = api.run("pset.add_pset", f, product=e, name="ArchitectConcept")
        api.run(
            "pset.edit_pset",
            f,
            pset=p,
            properties={**values, "Disclaimer": model["meta"]["disclaimer"]},
        )

    styles = {}
    material_entities = {}

    def geometry(e, boxes):
        vertices = []
        faces = []
        for b in boxes:
            vertices.append(
                [
                    [float(b["center"][k] + v[k] * b["size"][k]) for k in range(3)]
                    for v in _CUBE
                ]
            )
            faces.append([list(t) for t in _FACES])
        if vertices:
            rep = api.run(
                "geometry.add_mesh_representation",
                f,
                context=body,
                vertices=vertices,
                faces=faces,
            )
            api.run("geometry.assign_representation", f, product=e, representation=rep)
            for item, box in zip(rep.Items, boxes):
                if "color" not in box:
                    continue
                key = json.dumps(
                    [box["material"], box["color"], box["roughness"], box["metalness"]]
                )
                if key not in styles:
                    style = api.run("style.add_style", f, name=box["material_name"])
                    api.run(
                        "style.add_surface_style",
                        f,
                        style=style,
                        ifc_class="IfcSurfaceStyleShading",
                        attributes={
                            "SurfaceColour": dict(
                                zip(
                                    ("Red", "Green", "Blue"),
                                    map(float, box["color"][:3]),
                                )
                            ),
                            "Transparency": float(1 - box["color"][3]),
                        },
                    )
                    styles[key] = style
                api.run("style.assign_item_style", f, item=item, style=styles[key])
            if boxes and "material" in boxes[0]:
                name = boxes[0]["material_name"]
                if name not in material_entities:
                    material_entities[name] = api.run(
                        "material.add_material", f, name=name
                    )
                api.run(
                    "material.assign_material",
                    f,
                    products=[e],
                    material=material_entities[name],
                )
        api.run("geometry.edit_object_placement", f, product=e, matrix=np.eye(4))

    def contain(e, level):
        api.run(
            "spatial.assign_container",
            f,
            products=[e],
            relating_structure=storeys[level],
        )

    groups = defaultdict(list)
    for b in wall_boxes(model):
        groups[(b["kind"], b.get("host_id", b["name"]), b["level"])].append(b)
    walls = {}
    for w in model["walls"]:
        e = entity("IfcWall", w["id"])
        walls[w["id"]] = e
        contain(e, w["level"])
        geometry(e, groups.get(("wall", w["id"], w["level"]), []))
        props(e, {"SourceId": w["id"], "Kind": w["kind"], "Thickness": w["thickness"]})
    roofs = {}
    slabs = {}
    for (kind, host, level), boxes in groups.items():
        if kind not in ("floor", "courtyard", "roof", "finish", "stair", "furniture"):
            continue
        cls = {
            "floor": "IfcSlab",
            "courtyard": "IfcSlab",
            "roof": "IfcRoof",
            "finish": "IfcCovering",
            "stair": "IfcStairFlight",
            "furniture": "IfcFurnishingElement",
        }[kind]
        e = entity(cls, f"{kind}:{host}", f"{kind}:{host}:{level}")
        contain(e, level)
        geometry(e, boxes)
        props(e, {"SourceId": host, "Material": boxes[0]["material_name"]})
        if kind == "roof":
            roofs[host] = e
        if kind in ("floor", "courtyard"):
            slabs[host] = e
        if kind == "stair":
            st = next(s for s in model["stairs"] if s["space_id"] == host)
            e.NumberOfRisers = st["risers"]
            e.NumberOfTreads = st["risers"] - 2
            e.RiserHeight = st["riser_mm"] / 1000
            e.TreadLength = st["going_mm"] / 1000
    bases = level_bases(model)
    for s in model["spaces"]:
        e = entity("IfcSpace", s["name"], s["id"])
        api.run(
            "aggregate.assign_object",
            f,
            products=[e],
            relating_object=storeys[s["level"]],
        )
        r = rect(s["rect"])
        geometry(
            e,
            [
                {
                    "center": [r.cx, r.cy, bases[s["level"]] + s["ceiling_height"] / 2],
                    "size": [r.w, r.d, s["ceiling_height"]],
                }
            ],
        )
        props(
            e,
            {
                "SourceId": s["id"],
                "Area": s["area"],
                "TargetArea": s["target_area"],
                "Zone": s["zone"],
            },
        )
    wallmap = {w["id"]: w for w in model["walls"]}
    for o in model["openings"]:
        s = next(s for s in model["spaces"] if s["id"] == o["space_id"])
        level = s["level"]
        host = (
            roofs.get(o.get("roof_id"))
            if o["kind"] == "skylight"
            else walls.get(o["wall_id"])
        )
        if not host:
            raise ValueError(f"{o['id']}: IFC host missing")
        opening = entity("IfcOpeningElement", o["id"])
        if o["kind"] == "skylight":
            r = rect(o["rect"])
            bounds = {
                "center": [r.cx, r.cy, bases[level] + s["ceiling_height"] + 0.08],
                "size": [r.w, r.d, 0.5],
            }
        else:
            w = wallmap[o["wall_id"]]
            wo = Wall(w["id"], w["level"], w["x1"], w["y1"], w["x2"], w["y2"])
            x, y = wo.point_at(o["offset"])
            bounds = {
                "center": [x, y, bases[level] + o["sill"] + o["height"] / 2],
                "size": [w["thickness"] + 0.2, o["width"], o["height"]]
                if wo.vertical
                else [o["width"], w["thickness"] + 0.2, o["height"]],
            }
        geometry(opening, [bounds])
        api.run("feature.add_feature", f, feature=opening, element=host)
        props(
            opening, {"SourceId": o["id"], "HostId": o.get("roof_id") or o["wall_id"]}
        )
        if o["kind"] != "passage":
            e = entity(
                "IfcDoor" if o["kind"] in ("door", "entrance") else "IfcWindow", o["id"]
            )
            contain(e, level)
            boxes = [
                b
                for k in ("frame", "glass", "door")
                for b in groups.get((k, o["id"], level), [])
            ]
            geometry(e, boxes)
            api.run("feature.add_filling", f, opening=opening, element=e)
            e.OverallWidth = float(o["width"])
            e.OverallHeight = float(
                o["depth"] if o["kind"] == "skylight" else o["height"]
            )
    # Slab openings for stairs are real IfcRelVoidsElement relationships as well as cut meshes.
    for st in model["stairs"]:
        shaft = rect(st["shaft_rect"])
        landing = slabs.get(f"landing-{st['space_id']}")
        if landing:
            e = entity("IfcOpeningElement", f"shaft-{st['space_id']}")
            geometry(
                e,
                [
                    {
                        "center": [shaft.cx, shaft.cy, bases[st["to_level"]] - 0.09],
                        "size": [shaft.w, shaft.d, 0.4],
                    }
                ],
            )
            api.run("feature.add_feature", f, feature=e, element=landing)
    f.header.file_description.description = (
        "ViewDefinition [ReferenceView]",
        model["meta"]["disclaimer"],
    )
    f.write(str(path))
    return len(f.by_type("IfcProduct"))
