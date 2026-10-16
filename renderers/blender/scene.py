"""Embedded in generated render scripts; executed by Blender 4.5 LTS or later."""

import bpy
import math
import json
from pathlib import Path
from mathutils import Vector

PAYLOAD = json.loads(Path(__file__).with_suffix(".json").read_text())
model = PAYLOAD["model"]
style = PAYLOAD["style"]
options = PAYLOAD["options"]
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
materials = {}


def material(b):
    key = json.dumps(
        [
            b["material"],
            b["color"],
            b["roughness"],
            b["metalness"],
            b.get("pattern_settings", {}),
        ],
        sort_keys=True,
    )
    if key in materials:
        return materials[key]
    m = bpy.data.materials.new(b["material_name"])
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    color = b["color"][:3]
    if style.get("clay"):
        color = [0.78, 0.76, 0.71]
    elif "saturation" in style:
        grey = sum(color) / 3
        color = [grey + (v - grey) * style["saturation"] for v in color]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = (
        0.75 if style.get("clay") else b["roughness"]
    )
    bsdf.inputs["Metallic"].default_value = 0 if style.get("clay") else b["metalness"]
    if b["kind"] == "glass" and not style.get("clay"):
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = 1
        bsdf.inputs["IOR"].default_value = 1.45
        bsdf.inputs["Roughness"].default_value = 0.08
    pattern = b.get("pattern", "flat")
    if pattern not in ("flat", "standing_seam", "slat") and not style.get("clay"):
        # Object-space coordinates have metre units because dimensions are applied.
        coord = nt.nodes.new("ShaderNodeTexCoord")
        mapping = nt.nodes.new("ShaderNodeVectorMath")
        mapping.operation = "MULTIPLY"
        mapping.inputs[1].default_value = (
            (0.5, 8.0, 8.0) if pattern in ("grain", "brushed") else (1.0, 1.0, 1.0)
        )
        nt.links.new(coord.outputs["Object"], mapping.inputs[0])
        settings = b.get("pattern_settings", {})
        scale = settings.get("scale", 4.0 if pattern == "veined" else 18.0)
        tex = nt.nodes.new(
            "ShaderNodeTexBrick" if pattern == "brick" else "ShaderNodeTexNoise"
        )
        tex.inputs["Scale"].default_value = scale
        nt.links.new(mapping.outputs[0], tex.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*[v * 0.78 for v in color], 1)
        ramp.color_ramp.elements[1].color = (*[min(1.0, v * 1.15) for v in color], 1)
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = settings.get("strength", 0.15)
        bump.inputs["Distance"].default_value = 0.002
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    materials[key] = m
    return m


for b in PAYLOAD["boxes"]:
    if options.get("hide_roof") and (
        b["kind"] in ("roof", "seam") or b["name"].startswith("SKY-")
    ):
        continue
    bpy.ops.mesh.primitive_cube_add(size=1, location=b["center"])
    ob = bpy.context.object
    ob.name = f"{b['kind']}:{b['name']}"
    ob.dimensions = b["size"]
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.data.materials.append(material(b))
    ob["source_id"] = b.get("host_id", b["name"])
    ob["space_id"] = b.get("space") or ""
    ob["level"] = b["level"]
    if b["kind"] != "glass":
        mod = ob.modifiers.new("Soft architectural edges", "BEVEL")
        mod.width = min(style.get("bevel", 0.008), min(b["size"]) * 0.15)
        mod.segments = 2
        normal = ob.modifiers.new("Weighted face normals", "WEIGHTED_NORMAL")
# Simple site context also comes from the canonical model.
for tree in model.get("landscape", []):
    x, y, z = tree["center"]
    h = tree["height"]
    radius = tree["radius"]
    bark = {
        "material": "tree-bark",
        "material_name": "Tree bark",
        "kind": "landscape",
        "color": [0.25, 0.18, 0.1, 1],
        "roughness": 0.9,
        "metalness": 0,
        "pattern": "flat",
    }
    leaf = {
        **bark,
        "material": "tree-leaf",
        "material_name": "Tree canopy",
        "color": [0.2, 0.34, 0.12, 1],
    }
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=0.09, depth=h * 0.65, location=(x, y, z + h * 0.325)
    )
    bpy.context.object.data.materials.append(material(bark))
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=2, radius=radius, location=(x, y, z + h * 0.72)
    )
    bpy.context.object.data.materials.append(material(leaf))
fp = model["site"]["footprint"]
cx = fp["x"] + fp["w"] / 2
cy = fp["y"] + fp["d"] / 2
bottom = min(l["elevation"] for l in model["levels"])
top = max(b["center"][2] + b["size"][2] / 2 for b in PAYLOAD["boxes"])
bpy.ops.mesh.primitive_plane_add(
    size=max(model["site"]["width"], model["site"]["depth"]) * 3,
    location=(cx, cy, bottom - 0.195),
)
bpy.context.object.data.materials.append(
    material(
        {
            "material": "site",
            "material_name": "Site ground",
            "kind": "landscape",
            "color": [0.45, 0.49, 0.37, 1],
            "roughness": 0.95,
            "metalness": 0,
            "pattern": "flat",
        }
    )
)
world = bpy.data.worlds.new("Architect world")
bpy.context.scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (*style["world"], 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = style[
    "world_strength"
]
bpy.ops.object.light_add(type="SUN", location=(cx, cy, top + 8))
sun = bpy.context.object
sun.data.energy = style["sun_energy"]
sun.data.angle = math.radians(5)
sun.rotation_euler = (
    math.radians(90 - style["sun_altitude"]),
    0,
    math.radians(style["sun_azimuth"]),
)
if style.get("interior_lights") or options["view"] == "interior":
    levels = {l["id"]: l for l in model["levels"]}
    for s in model["spaces"]:
        if s["open_to_sky"]:
            continue
        r = s["rect"]
        z = levels[s["level"]]["elevation"] + s["ceiling_height"] - 0.2
        bpy.ops.object.light_add(
            type="AREA", location=(r["x"] + r["w"] / 2, r["y"] + r["d"] / 2, z)
        )
        light = bpy.context.object
        light.data.energy = max(80.0, s["area"] * 12)
        light.data.color = (
            (1.0, 0.76, 0.5) if style.get("interior_lights") else (1.0, 0.94, 0.84)
        )
        light.data.shape = "DISK"
        light.data.size = min(r["w"], r["d"]) * 0.5
view = options["view"]
camera_spec = (
    model.get("render", {})
    .get("cameras", {})
    .get("interior" if view == "interior" else "exterior", {})
)
room_id = options.get("room") or model.get("render", {}).get("room")
room = next((s for s in model["spaces"] if s["id"] == room_id), None)
if not room:
    room = next(
        (s for s in model["spaces"] if s["id"] == "living"),
        max(
            (s for s in model["spaces"] if not s["open_to_sky"]),
            key=lambda s: s["area"],
        ),
    )
r = room["rect"]
z = next(l["elevation"] for l in model["levels"] if l["id"] == room["level"])
dist = max(fp["w"], fp["d"]) * 1.2
if view == "interior":
    position = [r["x"] + 0.5, r["y"] + 0.5, z + 1.6]
    target = [r["x"] + r["w"] * 0.75, r["y"] + r["d"] * 0.75, z + 1.5]
elif view == "courtyard":
    court = next(s for s in model["spaces"] if s["open_to_sky"])
    r = court["rect"]
    position = [r["x"] + 0.4, r["y"] + 0.4, bottom + 1.6]
    target = [r["x"] + r["w"] * 0.8, r["y"] + r["d"] * 0.8, bottom + 2.0]
else:
    position = [cx + dist, cy - dist, top + dist * 0.55]
    target = [cx, cy, (top + bottom) * 0.42]
position = options.get("camera") or camera_spec.get("position", position)
target = options.get("target") or camera_spec.get("target", target)
bpy.ops.object.camera_add(location=position)
camera = bpy.context.object
bpy.context.scene.camera = camera
camera.rotation_euler = (
    (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
)
camera.data.lens = options.get("lens") or camera_spec.get(
    "lens", 24 if view in ("interior", "courtyard") else 48
)
if view == "axonometric":
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(fp["w"], fp["d"]) * 1.65
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = options.get("samples") or style["samples"]
scene.cycles.use_denoising = True
scene.render.resolution_x, scene.render.resolution_y = options["resolution"]
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = "AgX"
scene.view_settings.exposure = style.get("exposure", 0)
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(Path(__file__).with_suffix(".png"))
scene["disclaimer"] = model["meta"]["disclaimer"]
scene["source_model_hash"] = PAYLOAD["model_hash"]
# Camera-attached concept label: presentation annotation, separate from building geometry.
label_data = bpy.data.curves.new("Concept disclaimer", "FONT")
label_data.body = (
    "CONCEPT DESIGN ONLY — Licensed professional review required. Not for construction."
)
label_data.size = 1
label = bpy.data.objects.new("Concept disclaimer", label_data)
bpy.context.collection.objects.link(label)
label.parent = camera
bpy.context.view_layer.update()
width = (
    camera.data.ortho_scale
    if camera.data.type == "ORTHO"
    else 2 * 0.5 * math.tan(camera.data.angle_x / 2)
)
height = width * options["resolution"][1] / options["resolution"][0]
label.scale = (width * 0.94 / max(label.dimensions.x, 1e-6),) * 3
label.location = (-width * 0.47, -height * 0.47, -0.5)
label_mat = bpy.data.materials.new("Disclaimer ink")
label_mat.use_nodes = True
nodes = label_mat.node_tree.nodes
nodes.clear()
output = nodes.new("ShaderNodeOutputMaterial")
emission = nodes.new("ShaderNodeEmission")
emission.inputs["Color"].default_value = (0.035, 0.045, 0.055, 1)
label_mat.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
label_data.materials.append(label_mat)
label.visible_shadow = False
bpy.ops.wm.save_as_mainfile(filepath=str(Path(__file__).with_suffix(".blend")))
bpy.ops.render.render(write_still=True)
print("RENDERED", scene.render.filepath)
