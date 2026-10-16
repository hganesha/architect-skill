"""Generate portable Blender scripts and optionally execute Blender."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engines.bim_exporter.exporters import wall_boxes


def generate(
    model,
    out,
    style="daylight",
    view="exterior",
    resolution=(1920, 1280),
    samples=None,
    room=None,
    camera=None,
    target=None,
    lens=None,
    hide_roof=False,
    execute=False,
    blender=None,
):
    styles = json.loads((Path(__file__).with_name("styles.json")).read_text())
    if style not in styles:
        raise ValueError(f"unsupported render style: {style}")
    if view == "courtyard" and not any(s["open_to_sky"] for s in model["spaces"]):
        raise ValueError("courtyard view requires a courtyard")
    if room and room not in {s["id"] for s in model["spaces"]}:
        raise ValueError(f"unknown render room: {room}")
    if len(resolution) != 2 or min(resolution) < 32 or max(resolution) > 8192:
        raise ValueError("resolution must be between 32 and 8192 pixels per axis")
    for name, values in [("camera", camera), ("target", target)]:
        if values is not None and (
            len(values) != 3 or not all(math.isfinite(v) for v in values)
        ):
            raise ValueError(f"{name} needs three finite coordinates")
    if lens is not None and not 10 <= lens <= 150:
        raise ValueError("lens must be between 10 and 150 mm")
    if camera is not None and target is not None and list(camera) == list(target):
        raise ValueError("camera and target must differ")
    if samples is not None and samples < 1:
        raise ValueError("samples must be positive")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"render_{style}_{view}"
    payload = {
        "model": model,
        "boxes": wall_boxes(model),
        "model_hash": hashlib.sha256(
            json.dumps(model, sort_keys=True).encode()
        ).hexdigest(),
        "style": styles[style],
        "options": {
            "view": view,
            "resolution": resolution,
            "samples": samples,
            "room": room,
            "camera": camera,
            "target": target,
            "lens": lens,
            "hide_roof": hide_roof,
        },
    }
    payload_path = out / f"{stem}.json"
    payload_path.write_text(json.dumps(payload, indent=2))
    script = out / f"{stem}.py"
    script.write_text(Path(__file__).with_name("scene.py").read_text())
    result = {
        "script": str(script),
        "payload": str(payload_path),
        "image": str(script.with_suffix(".png")),
        "blend": str(script.with_suffix(".blend")),
        "executed": False,
    }
    if execute:
        executable = blender or shutil.which("blender")
        if not executable:
            raise RuntimeError(
                "Blender executable not found; use --blender /path/to/blender. Script generation succeeded."
            )
        log = script.with_suffix(".log")
        with log.open("w") as output:
            completed = subprocess.run(
                [
                    str(executable),
                    "--background",
                    "--factory-startup",
                    "--python-exit-code",
                    "1",
                    "--python",
                    str(script.resolve()),
                ],
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        result["log"] = str(log)
        if completed.returncode:
            raise RuntimeError(
                f"Blender failed ({completed.returncode}); see {log}:\n"
                + "\n".join(log.read_text().splitlines()[-12:])
            )
        if not script.with_suffix(".png").is_file():
            raise RuntimeError("Blender exited without producing a PNG")
        result["executed"] = True
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model")
    ap.add_argument("--out", default="renders")
    ap.add_argument("--style", default="daylight")
    ap.add_argument(
        "--view",
        choices=["exterior", "interior", "courtyard", "axonometric"],
        default="exterior",
    )
    ap.add_argument("--resolution", default="1920x1280")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--room")
    ap.add_argument("--camera", type=float, nargs=3)
    ap.add_argument("--target", type=float, nargs=3)
    ap.add_argument("--lens", type=float)
    ap.add_argument("--hide-roof", action="store_true")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--blender")
    a = ap.parse_args()
    try:
        result = generate(
            json.loads(Path(a.model).read_text()),
            a.out,
            style=a.style,
            view=a.view,
            resolution=tuple(map(int, a.resolution.lower().split("x"))),
            samples=a.samples,
            room=a.room,
            camera=a.camera,
            target=a.target,
            lens=a.lens,
            hide_roof=a.hide_roof,
            execute=a.execute,
            blender=a.blender,
        )
        print(json.dumps(result, indent=2))
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        ap.exit(1, f"{e}\n")


if __name__ == "__main__":
    main()
