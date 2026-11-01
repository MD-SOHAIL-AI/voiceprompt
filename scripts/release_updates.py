"""Create and verify signed, public update metadata without a paid service.

The pinned Tauri CLI provides Minisign signing. Native verification uses exactly
the code shipped in VoicePrompt. Private keys and passwords are never printed.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
KEY_DIRECTORY = ROOT / ".tools" / "update-signing"
PUBLIC_KEY = ROOT / "desktop" / "src-tauri" / "update-public-key.pub"
REPOSITORY = "MD-SOHAIL-AI/voiceprompt"


def run_signer(arguments, environment=None):
    command = ["node", str(ROOT / "desktop/node_modules/@tauri-apps/cli/tauri.js"), "signer", *arguments]
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True)
    if completed.returncode:
        raise ValueError("Tauri signing failed. Check the installed CLI, private key, and password; secret output was suppressed.")


def dpapi(data: bytes, *, decrypt=False) -> bytes:
    """Machine DPAPI plus a restricted directory permits the real user and agent.

    User-scoped DPAPI would strand keys created by an isolated agent account.
    Directory ACLs remain essential because machine DPAPI is not user isolation.
    """
    if sys.platform != "win32":
        raise ValueError("Local signing-key setup requires Windows. CI reads protected Actions secrets.")

    class Blob(ctypes.Structure):
        _fields_ = [("length", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(Blob)]
    function.restype = ctypes.c_int
    if not function(ctypes.byref(incoming), None, None, None, None, 1 if decrypt else 5, ctypes.byref(outgoing)):
        raise ValueError("Windows could not protect or unlock the local signing password.")
    try:
        return ctypes.string_at(outgoing.data, outgoing.length)
    finally:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(outgoing.data, ctypes.c_void_p))


def protect_key_directory():
    KEY_DIRECTORY.mkdir(parents=True, exist_ok=True)
    code = r'''$current = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$profile = @(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\*' | Where-Object { [Environment]::ExpandEnvironmentVariables($_.ProfileImagePath) -eq $env:USERPROFILE } | Select-Object -ExpandProperty PSChildName)
if ($profile.Count -ne 1) { exit 1 }
ConvertTo-Json -InputObject @($current, $profile[0]) -Compress'''
    resolved = subprocess.run(["powershell", "-NoProfile", "-Command", code], capture_output=True, text=True)
    if resolved.returncode:
        raise ValueError("Could not identify the Windows profile owner for signing-key permissions. Run setup from the owner's Windows account.")
    identities = set(json.loads(resolved.stdout)) | {"S-1-5-18", "S-1-5-32-544"}
    arguments = ["icacls", str(KEY_DIRECTORY), "/inheritance:r", "/grant:r"]
    arguments += [f"*{identity}:(OI)(CI)F" for identity in sorted(identities)]
    if subprocess.run(arguments, capture_output=True).returncode:
        raise ValueError("Could not restrict signing-key directory permissions.")
    for path in KEY_DIRECTORY.iterdir():
        if subprocess.run(["icacls", str(path), "/reset"], capture_output=True).returncode:
            raise ValueError("Could not apply private signing-key permissions.")


def signing_environment():
    environment = os.environ.copy()
    if not environment.get("VOICEPROMPT_UPDATE_PRIVATE_KEY"):
        key = KEY_DIRECTORY / "update.key"
        password = KEY_DIRECTORY / "password.dpapi"
        if not key.is_file() or not password.is_file():
            raise ValueError("Configure update signing first: python scripts/release_updates.py init")
        environment["VOICEPROMPT_UPDATE_PRIVATE_KEY"] = key.read_text(encoding="utf-8").strip()
        environment["VOICEPROMPT_UPDATE_KEY_PASSWORD"] = dpapi(password.read_bytes(), decrypt=True).decode("utf-8")
    if not environment.get("VOICEPROMPT_UPDATE_KEY_PASSWORD"):
        raise ValueError("VOICEPROMPT_UPDATE_KEY_PASSWORD is missing.")
    environment["TAURI_SIGNING_PRIVATE_KEY"] = environment["VOICEPROMPT_UPDATE_PRIVATE_KEY"]
    environment["TAURI_SIGNING_PRIVATE_KEY_PASSWORD"] = environment["VOICEPROMPT_UPDATE_KEY_PASSWORD"]
    return environment


def configure_github():
    environment = signing_environment()
    for name in ("VOICEPROMPT_UPDATE_PRIVATE_KEY", "VOICEPROMPT_UPDATE_KEY_PASSWORD"):
        completed = subprocess.run(["gh", "secret", "set", name, "--repo", REPOSITORY], input=environment[name], text=True, capture_output=True)
        if completed.returncode:
            raise ValueError("GitHub secret setup failed. Authenticate gh with repository-secret access and rerun init --github. Secret output was suppressed.")
    print("Configured the two protected GitHub Actions secrets. No secret values were printed.")


def initialize(github=False):
    protect_key_directory()
    existing_public = PUBLIC_KEY.read_text(encoding="utf-8").strip() if PUBLIC_KEY.exists() else ""
    key = KEY_DIRECTORY / "update.key"
    if existing_public:
        if not key.exists():
            raise ValueError("A public update identity already exists. Restore its private key; do not regenerate it.")
        print("Keeping the existing update identity.")
        scope = KEY_DIRECTORY / "password-scope.txt"
        if not scope.is_file():
            password = dpapi((KEY_DIRECTORY / "password.dpapi").read_bytes(), decrypt=True)
            (KEY_DIRECTORY / "password.dpapi").write_bytes(dpapi(password))
            scope.write_text("machine-dpapi-with-profile-owner-acl\n", encoding="ascii")
    else:
        KEY_DIRECTORY.mkdir(parents=True, exist_ok=True)
        if key.exists():
            raise ValueError("A private key already exists. Restore its matching public key instead of overwriting it.")
        password = secrets.token_urlsafe(48)
        # Capture the CLI output because key generation prints private material.
        run_signer(["generate", "--ci", "--write-keys", str(key), "--password", password])
        (KEY_DIRECTORY / "password.dpapi").write_bytes(dpapi(password.encode("utf-8")))
        (KEY_DIRECTORY / "password-scope.txt").write_text("machine-dpapi-with-profile-owner-acl\n", encoding="ascii")
        wrapped_public = Path(str(key) + ".pub").read_text(encoding="utf-8").strip()
        PUBLIC_KEY.write_bytes(base64.b64decode(wrapped_public, validate=True))
        print("Created a persistent update identity. The encrypted private key and machine-DPAPI password have restricted profile-owner permissions.")
        print("Back up .tools/update-signing securely. Before moving to another computer, export/re-encrypt the password on this machine.")
    if github:
        configure_github()


def verify(native: Path, metadata: Path, installer: Path):
    completed = subprocess.run([str(native.resolve()), "--verify-update", str(metadata.resolve()), str(installer.resolve())], capture_output=True)
    if completed.returncode:
        raise ValueError("Native update verification rejected the signature, metadata, or installer. Nothing was published.")


def sign(installer: Path, notes: Path, native: Path):
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)[1]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("The stable update feed requires a stable semantic version.")
    if installer.name != f"VoicePrompt-Setup-{version}-x64.exe":
        raise ValueError("The installer filename must match the canonical stable release version.")
    digest = hashlib.file_digest(installer.open("rb"), "sha256").hexdigest()
    manifest = {"schema": 1, "app": "app.voiceprompt.desktop", "channel": "stable", "target": "windows-x86_64",
                "version": version, "notes": notes.read_text(encoding="utf-8"), "published_at": datetime.now(timezone.utc).isoformat(),
                "url": f"https://github.com/{REPOSITORY}/releases/download/v{version}/{installer.name}",
                "size": installer.stat().st_size, "sha256": digest}
    payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    installer.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / ".tools").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="update-sign-", dir=ROOT / ".tools") as directory:
        payload_path = Path(directory) / "payload.json"
        payload_path.write_bytes(payload.encode("utf-8"))
        run_signer(["sign", str(payload_path)], signing_environment())
        signature = base64.b64decode(Path(str(payload_path) + ".sig").read_text().strip(), validate=True).decode("utf-8")
        metadata = Path(directory) / "latest.json"
        metadata.write_text(json.dumps({"payload": payload, "signature": signature}, ensure_ascii=False), encoding="utf-8")
        verify(native, metadata, installer)
        shutil.copyfile(metadata, installer.parent / "latest.json")
    audit = {"mode": "update-signed-release", "update_signature_verified": True, "authenticode_signing_verified": False,
             "installer_sha256": digest, "metadata_sha256": hashlib.sha256((installer.parent / "latest.json").read_bytes()).hexdigest()}
    Path(str(installer) + ".update-signing.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(f"Signed and verified update metadata for {version}; Windows publisher signing remains separate.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("init")
    setup.add_argument("--github", action="store_true", help="Also set the two Actions secrets through authenticated gh.")
    signing = commands.add_parser("sign")
    signing.add_argument("--installer", type=Path, required=True)
    signing.add_argument("--notes", type=Path, required=True)
    signing.add_argument("--native-exe", type=Path, required=True)
    checking = commands.add_parser("verify")
    checking.add_argument("--installer", type=Path, required=True)
    checking.add_argument("--metadata", type=Path, required=True)
    checking.add_argument("--native-exe", type=Path, required=True)
    options = parser.parse_args()
    if options.command == "init": initialize(options.github)
    elif options.command == "sign": sign(options.installer, options.notes, options.native_exe)
    else: verify(options.native_exe, options.metadata, options.installer)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(f"Update release failed: {error}", file=sys.stderr)
        raise SystemExit(1)
