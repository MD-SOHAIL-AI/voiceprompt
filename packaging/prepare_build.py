"""Build assets and collect verbatim license files from installed distributions."""
import importlib.metadata as metadata
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
BUILD.mkdir(exist_ok=True)
image = Image.new("RGBA", (256, 256))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((4, 4, 252, 252), radius=56, fill="#172A20")
for x, height in zip((62, 95, 128, 161, 194), (56, 112, 160, 96, 44)):
    draw.rounded_rectangle((x - 5, 128 - height // 2, x + 5, 128 + height // 2), radius=5, fill="#8BD0AF")
image.save(BUILD / "VoicePrompt.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
native_icons = ROOT / 'desktop/src-tauri/icons'
native_icons.mkdir(parents=True, exist_ok=True)
shutil.copy2(BUILD / 'VoicePrompt.ico', native_icons / 'icon.ico')

licenses = BUILD / "licenses"
if licenses.resolve().parent != BUILD.resolve() or licenses.name != "licenses":
    raise RuntimeError("Unexpected license staging directory")
if licenses.exists():
    shutil.rmtree(licenses)
licenses.mkdir(exist_ok=True)
inventory = []
for distribution in metadata.distributions():
    name = distribution.metadata["Name"]
    destination = licenses / name
    destination.mkdir(exist_ok=True)
    texts = []
    for item in distribution.files or []:
        parts = [part.lower() for part in item.parts]
        if any(part in {"licenses", "license", "licences"} for part in parts) or item.name.lower().startswith(("license", "copying", "notice", "copyright")):
            source = distribution.locate_file(item)
            if source.is_file() and source.suffix.lower() not in {".py", ".pyc"}:
                # Retain package-relative directories so notices with equal names coexist.
                target = destination / item
                if ".." in item.parts:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                texts.append(str(item))
    inventory.append({"name": name, "version": distribution.version,
                      "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License", "See package notices"),
                      "files": texts})
(licenses / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
print(f"Prepared icon and notices for {len(inventory)} installed distributions.")
