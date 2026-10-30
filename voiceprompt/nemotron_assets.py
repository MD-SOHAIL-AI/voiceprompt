"""Pinned Windows runtime and model cache for local Nemotron inference."""
from __future__ import annotations

import hashlib
import os
import json
import shutil
import sys
import sysconfig
import tempfile
import urllib.request
import uuid
import zipfile
from pathlib import Path

from voiceprompt.config import config_dir


ASSETS = Path(__file__).resolve().parent / "assets"
MODEL_REPO = "nvidia/nemotron-speech-streaming-en-0.6b"
MODEL_REVISION = "ebe59e5a817142986528bbbee5dba8db7b38ed50"
MODEL_FILENAME = "nemotron-speech-streaming-en-0.6b.q8_0.gguf"
MODEL_BYTES = 699872960
MODEL_SHA256 = "d9a01898d2a611c8764e23a1c2f45e70bbd5a425dc4de93692ac951dd603812d"
RUNTIME_NAME = "nemo-speech-0.2.0-windows-x86_64-vulkan"
RUNTIME_SHA256 = "edf15a04ba98740aa0ab75ae4681ac7ad0a488b22b35ce2cbebd10590bb1c1e1"
RUNTIME_URL = f"https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v0.2.0/{RUNTIME_NAME}.zip"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_file() -> Path:
    from huggingface_hub import hf_hub_download
    from huggingface_hub.utils import LocalEntryNotFoundError, disable_progress_bars

    disable_progress_bars()
    try:
        path = Path(hf_hub_download(MODEL_REPO, MODEL_FILENAME, revision=MODEL_REVISION, local_files_only=True))
    except LocalEntryNotFoundError:
        path = Path(hf_hub_download(MODEL_REPO, MODEL_FILENAME, revision=MODEL_REVISION))
    if _valid_model(path):
        return path
    path = Path(hf_hub_download(MODEL_REPO, MODEL_FILENAME, revision=MODEL_REVISION, force_download=True))
    if not _valid_model(path):
        raise RuntimeError("Nemotron weights failed verification. No audio was captured.")
    return path


def _valid_model(path: Path) -> bool:
    return path.is_file() and path.stat().st_size == MODEL_BYTES and sha256_file(path) == MODEL_SHA256


def runtime_files_valid(folder: Path, hashes: dict[str, str]) -> bool:
    return all((folder / name).is_file() and sha256_file(folder / name) == expected for name, expected in hashes.items())


def runtime_directory() -> Path:
    if sys.platform != "win32" or sysconfig.get_platform().lower() != "win-amd64" or sys.maxsize <= 2**32:
        raise RuntimeError("This Nemotron runtime requires 64-bit Windows on an x64 processor.")
    hashes = json.loads((ASSETS / "nemotron-runtime-hashes.json").read_text(encoding="utf-8"))
    root = config_dir() / "runtimes"
    destination = root / RUNTIME_NAME
    if runtime_files_valid(destination / "bin", hashes):
        return destination / "bin"
    if os.environ.get("HF_HUB_OFFLINE") == "1":
        raise RuntimeError("The Nemotron runtime is not cached or failed verification. Prepare it while online first.")

    root.mkdir(parents=True, exist_ok=True)
    archive_path = root / f"{RUNTIME_NAME}.zip"
    if not archive_path.is_file() or sha256_file(archive_path) != RUNTIME_SHA256:
        temporary = root / f"nemotron-{uuid.uuid4().hex}.download"
        try:
            with urllib.request.urlopen(RUNTIME_URL, timeout=60) as source, temporary.open("wb") as output:
                from voiceprompt.downloads import report_progress
                total = int(getattr(source, "headers", {}).get("Content-Length", 0)) or None
                downloaded = 0
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    report_progress({"phase": "Downloading Nemotron runtime", "name": RUNTIME_NAME,
                                     "completed": downloaded, "total": total})
            if sha256_file(temporary) != RUNTIME_SHA256:
                raise RuntimeError("Nemotron runtime failed its checksum. No native code was loaded.")
            temporary.replace(archive_path)
        finally:
            temporary.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="nemotron-install-", dir=root) as directory:
        staging = Path(directory).resolve()
        with zipfile.ZipFile(archive_path) as archive:
            for entry in archive.infolist():
                target = (staging / entry.filename).resolve()
                if not target.is_relative_to(staging) or ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                    raise RuntimeError("Unsafe path in Nemotron runtime archive.")
            archive.extractall(staging)
        package = staging / RUNTIME_NAME
        if not runtime_files_valid(package / "bin", hashes):
            raise RuntimeError("Nemotron runtime files failed verification. No native code was loaded.")
        # Include the upstream licenses/documentation. An interrupted install is
        # detected by the per-binary hashes and repaired on the next preload.
        shutil.copytree(package, destination, dirs_exist_ok=True)
    if not runtime_files_valid(destination / "bin", hashes):
        raise RuntimeError("Nemotron runtime installation is incomplete.")
    return destination / "bin"
