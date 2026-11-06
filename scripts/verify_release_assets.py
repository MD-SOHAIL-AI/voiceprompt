"""Verify uploaded draft assets before changing the public release/feed."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'MD-SOHAIL-AI/voiceprompt'


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_downloaded(local, hosted, installer, names):
    """Compare every required asset, then validate the installer sidecar."""
    hashes = {}
    for name in names:
        if Path(name).name != name or not name:
            raise ValueError('Release assets must be plain filenames.')
        original, downloaded = local / name, hosted / name
        if not original.is_file() or not downloaded.is_file():
            raise ValueError(f'Required release asset missing: {name}')
        expected, actual = sha256(original), sha256(downloaded)
        if actual != expected:
            raise ValueError(f'Hosted release asset changed: {name}')
        hashes[name] = actual
    checksum = (hosted / (installer + '.sha256')).read_text(encoding='utf-8-sig').strip()
    if checksum != hashes[installer] + '  ' + installer:
        raise ValueError('The hosted installer checksum sidecar is invalid.')
    return hashes


def verify_draft(tag, installer, *, metadata=None, native=None, command=subprocess.run):
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-(?:rc|beta|preview)\.[1-9]\d*)?', tag):
        raise ValueError('A versioned release tag is required.')
    stable = '-' not in tag
    if stable and (metadata is None or native is None):
        raise ValueError('Stable assets require signed metadata and the native signature verifier.')
    installer = Path(installer).resolve()
    expected_name = f'VoicePrompt-Setup-{tag[1:]}-x64' + ('' if stable else '-unsigned-preview') + '.exe'
    if installer.name != expected_name:
        raise ValueError('The installer filename must match the release tag and channel.')
    names = [installer.name, installer.name + '.sha256', installer.name + '.signing.json']
    if stable:
        if Path(metadata).name != 'latest.json' or Path(metadata).parent.resolve() != installer.parent:
            raise ValueError('Signed metadata must be staged with the installer.')
        names += [Path(metadata).name, installer.name + '.update-signing.json']
    viewed = command(['gh', 'release', 'view', tag, '--repo', REPOSITORY, '--json', 'isDraft,tagName,assets'], capture_output=True, text=True)
    if viewed.returncode:
        raise ValueError('The release draft could not be inspected.')
    release = json.loads(viewed.stdout)
    if release.get('tagName') != tag or release.get('isDraft') is not True:
        raise ValueError('Only an unpublished matching draft can be verified for promotion.')
    if not set(names).issubset({asset['name'] for asset in release.get('assets', [])}):
        raise ValueError('The release draft is missing required assets.')
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hosted-release-', dir=ROOT / 'build') as temporary:
        hosted = Path(temporary).resolve()
        if not hosted.is_relative_to((ROOT / 'build').resolve()):
            raise ValueError('Invalid hosted verification directory.')
        args = ['gh', 'release', 'download', tag, '--repo', REPOSITORY, '--dir', str(hosted)]
        for name in names: args += ['--pattern', name]
        if command(args, capture_output=True).returncode:
            raise ValueError('The draft assets could not be independently downloaded.')
        hashes = verify_downloaded(installer.parent, hosted, installer.name, names)
        if stable:
            from release_updates import verify
            verify(Path(native), hosted / Path(metadata).name, hosted / installer.name)
        report = {'tag': tag, 'repository': REPOSITORY, 'draft_verified': True,
                  'update_signature_verified': stable, 'sha256': hashes}
        (installer.parent / (tag + '.hosted-verification.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--installer', type=Path, required=True)
    parser.add_argument('--metadata', type=Path)
    parser.add_argument('--native-exe', type=Path)
    options = parser.parse_args()
    try:
        print(json.dumps(verify_draft(options.tag, options.installer, metadata=options.metadata, native=options.native_exe)))
    except (ValueError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(f'Release remains unpublished: {error}')
