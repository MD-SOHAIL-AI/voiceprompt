"""Explicit, zero-cost update-signed release mode around the existing builder.

The inner unsigned-preview build verifies packaging without claiming a Windows
publisher identity. This driver packages the final stable filename, signs its
metadata, and rejects any package the native verifier cannot authenticate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from release_updates import ROOT, PUBLIC_KEY, sign, signing_environment

POWERSHELL = shutil.which("pwsh") or shutil.which("powershell") or "powershell"


def run(command, environment=None):
    if subprocess.run(command, cwd=ROOT, env=environment).returncode:
        raise ValueError("Release build or verification failed. No release was published.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes", type=Path, required=True)
    parser.add_argument("--inno-compiler", type=Path, default=ROOT / ".tools/inno/ISCC.exe")
    parser.add_argument("--skip-build", action="store_true", help="Repackage an already verified local stage; not used by CI.")
    parser.add_argument("--native-exe", type=Path, help="Use an already built native shell; the existing builder validates its version.")
    options = parser.parse_args()
    signing_environment()  # Fail before touching an existing stage.
    if not PUBLIC_KEY.read_text().strip():
        raise ValueError("Configure the public update key before building.")
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)[1]
    if not options.inno_compiler.is_file():
        fallback = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Inno Setup 6/ISCC.exe"
        if not fallback.is_file(): raise ValueError("Inno Setup 6 is required.")
        options.inno_compiler = fallback
    run([sys.executable, "scripts/verify_versions.py"])
    if not options.notes.is_file(): raise ValueError("Release notes are required.")
    if not options.skip_build:
        arguments = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/build_desktop.ps1", "-Python", sys.executable,
                     "-InnoCompiler", str(options.inno_compiler), "-AllowUnsignedPreview"]
        if options.native_exe: arguments += ["-NativeExecutable", str(options.native_exe.resolve())]
        # Build-time WebView checks must not share a live user's locked profile.
        (ROOT / "build").mkdir(exist_ok=True)
        environment = os.environ.copy()
        environment["VOICEPROMPT_ACCEPTANCE_DIR"] = tempfile.mkdtemp(prefix="update-smoke-", dir=ROOT / "build")
        run(arguments, environment)
    stage = ROOT / "dist/VoicePrompt"
    smoke_path = ROOT / "build/frozen-smoke.json"
    if not smoke_path.is_file():
        raise ValueError("A passing frozen smoke report is required, including when repackaging a local stage.")
    smoke = json.loads(smoke_path.read_text(encoding="utf-8-sig"))
    if smoke.get("error") or not smoke.get("tauri") or smoke.get("version") != version or len(smoke.get("workers", {})) != 4 or not smoke.get("rnnoise"):
        raise ValueError("Frozen application and worker verification did not pass for this version.")
    manifest_path = stage / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest["engine_version"] != version:
        raise ValueError("The staged engine does not match the release version.")
    for path, field in [(stage / "VoicePrompt.exe", "desktop_shell_sha256"), (stage / "engine/VoicePromptEngine.exe", "engine_sha256")]:
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != manifest[field]:
                raise ValueError("The staged application changed after build verification.")
    manifest["signing_mode"] = "update-signed-release"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    licenses = stage / "licenses/minisign-verify"
    licenses.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "UPSTREAM.md"):
        (licenses / name).write_bytes((ROOT / "desktop/src-tauri/vendor/minisign-verify" / name).read_bytes())
    inventory = sorted(str(path.relative_to(stage)) for path in stage.rglob("*") if path.is_file() and path.name != "installed-files.txt")
    (stage / "installed-files.txt").write_text("\n".join(inventory) + "\n", encoding="utf-8-sig")
    run([str(options.inno_compiler), f"/DAppVersion={version}", "/DUpdateSignedRelease", "packaging/voiceprompt.iss"])
    installer = ROOT / f"release/VoicePrompt-Setup-{version}-x64.exe"
    digest = hashlib.file_digest(installer.open("rb"), "sha256").hexdigest()
    Path(str(installer) + ".sha256").write_text(f"{digest}  {installer.name}\n", encoding="ascii")
    # Retain the established Windows-byte audit, with its honest unsigned status.
    run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/check_windows_signing.ps1", "-Installer", str(installer), "-AllowUnsignedPreview"])
    sign(installer, options.notes, stage / "VoicePrompt.exe")
    print(f"Update-signed release ready: {installer.name}. No Windows publisher certificate was used.")


if __name__ == "__main__":
    try: main()
    except (ValueError, OSError) as error:
        print(f"Release blocked: {error}", file=sys.stderr)
        raise SystemExit(1)
