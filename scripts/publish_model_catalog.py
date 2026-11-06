"""Publish authenticated model metadata; keep the last good catalog on failure."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from voiceprompt.model_library import validate_catalog

REPOSITORY = 'MD-SOHAIL-AI/voiceprompt'


def verify(path, native):
    if not path.is_file() or not 0 < path.stat().st_size <= 128 * 1024:
        raise ValueError('Catalog size is invalid.')
    result = subprocess.run([str(Path(native).resolve()), '--verify-model-catalog', str(path.resolve())], timeout=15)
    if result.returncode:
        raise ValueError('The catalog signature is not trusted by the packaged application.')
    catalog = json.loads(json.loads(path.read_text(encoding='utf-8'))['payload'])
    return validate_catalog(catalog)


def check(command):
    result = subprocess.run(['gh', *command, '--repo', REPOSITORY], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('GitHub catalog operation failed. Inspect the release; no success was recorded.')
    return result.stdout


def publish(catalog, native):
    catalog = Path(catalog).resolve()
    if catalog.name != 'model-catalog.json':
        raise ValueError('The catalog feed requires model-catalog.json.')
    value = verify(catalog, native)
    # Listing distinguishes an absent release from authentication/network errors.
    releases = json.loads(check(['release', 'list', '--limit', '100', '--json', 'tagName,isDraft']))
    existing = next((r for r in releases if r['tagName'] == 'model-catalog'), None)
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='catalog-publication-', dir=ROOT / 'build') as temporary:
        folder = Path(temporary)
        previous = folder / 'previous'
        previous.mkdir()
        if existing:
            details = json.loads(check(['release', 'view', 'model-catalog', '--json', 'assets']))
            if any(asset['name'] == catalog.name for asset in details['assets']):
                check(['release', 'download', 'model-catalog', '--pattern', catalog.name, '--dir', str(previous)])
                old = verify(previous / catalog.name, native)
                if value['version'] < old['version']:
                    raise ValueError('Catalog rollback rejected.')
                if value['version'] == old['version'] and value != old:
                    raise ValueError('Changed catalog content requires a new catalog version.')
        else:
            check(['release', 'create', 'model-catalog', '--draft', '--prerelease', '--latest=false',
                   '--target', subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                   '--title', 'Supported speech model catalog', '--notes', 'Reviewed, signed model metadata. Models download only at user request.'])
        try:
            check(['release', 'upload', 'model-catalog', str(catalog), '--clobber'])
            hosted = folder / 'hosted'
            hosted.mkdir()
            check(['release', 'download', 'model-catalog', '--pattern', catalog.name, '--dir', str(hosted)])
            downloaded = hosted / catalog.name
            if downloaded.read_bytes() != catalog.read_bytes():
                raise ValueError('Hosted catalog bytes do not match the verified local catalog.')
            verify(downloaded, native)
        except Exception:
            if (previous / catalog.name).exists():
                check(['release', 'upload', 'model-catalog', str(previous / catalog.name), '--clobber'])
            raise
        if not existing or existing['isDraft']:
            check(['release', 'edit', 'model-catalog', '--draft=false', '--prerelease', '--latest=false'])
    report = {'published': True, 'catalog_version': value['version'], 'models': len(value['models']),
              'sha256': hashlib.sha256(catalog.read_bytes()).hexdigest(), 'native_signature_verified': True}
    (ROOT / 'build/catalog-publication.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'release/model-catalog.json')
    parser.add_argument('--native-exe', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        value = verify(args.catalog, args.native_exe)
        print(json.dumps({'verified': True, 'version': value['version'], 'models': len(value['models'])}))
    else:
        print(json.dumps(publish(args.catalog, args.native_exe)))
