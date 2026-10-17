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
draw.rounded_rectangle((4, 4, 252, 252), radius=56, fill="#285D46")
draw.rounded_rectangle((104, 52, 152, 144), radius=24, fill="white")
draw.arc((80, 92, 176, 176), 0, 180, fill="white", width=12)
draw.line((128, 176, 128, 204), fill="white", width=12)
draw.line((100, 204, 156, 204), fill="white", width=12)
image.save(BUILD / "VoicePrompt.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

licenses = BUILD / "licenses"
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
