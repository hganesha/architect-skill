"""The shipped showcase must be portable and backed by complete output snapshots."""

from pathlib import Path
import hashlib
import importlib.util
import json
import re
import shutil
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "showcase_builder", ROOT / "tools/build_showcase.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_shipped_bundle_has_complete_hashed_assets_and_portable_links():
    folder = ROOT / "examples/showcase"
    bundle = json.loads((folder / "bundle.json").read_text())
    assert len(bundle["projects"]) == 4
    for name, expected in bundle["files"].items():
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected, (
            name
        )
    html = (folder / "index.html").read_text()
    payload = re.search(r"const DATA=(.*);\nconst \$=", html).group(1)
    data = json.loads(payload)
    assert len(data["projects"]) == 4 and len(data["alternatives"]) == 3
    assert sum(len(p["renders"]) for p in data["projects"]) == 6
    for project in data["projects"]:
        assert project["status"] == "PASS"
        for url in [project["viewer"], project["cover"]] + [
            f["url"]
            for key in ("drawings", "renders", "downloads")
            for f in project[key]
        ]:
            assert not url.startswith(("/", "http:", "https:", "file:"))
            assert (folder / url).is_file(), url
    assert "fetch(" not in html and "cdn." not in html
    assert all((folder / a["url"]).is_file() for a in data["alternatives"])


def test_builder_rejects_missing_or_stale_sources_without_partial_output(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for _, _, _, relative, _ in builder.PROJECTS:
        folder = source / relative
        folder.mkdir(parents=True)
        model = {"meta": {"name": "Unverified"}}
        (folder / "model.json").write_text(json.dumps(model))
        (folder / "validation.json").write_text(json.dumps({"status": "PASS"}))
        (folder / "manifest.json").write_text(
            json.dumps({"model_hash": "stale", "files": {}})
        )
    target = tmp_path / "showcase"
    with pytest.raises(ValueError, match="provenance mismatch"):
        builder.build(source, target)
    assert not target.exists()


def test_builder_preserves_other_destination_folders(tmp_path):
    target = tmp_path / "user-folder"
    target.mkdir()
    (target / "index.html").write_text("user authored page")
    with pytest.raises(ValueError, match="empty destination"):
        builder.build(ROOT / "examples/showcase", target)
    assert (target / "index.html").read_text() == "user authored page"
