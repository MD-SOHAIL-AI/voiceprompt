"""Collect notices and source references for the locked Windows Rust graph."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OVERRIDES = ROOT / 'packaging/native-license-overrides'


def collect(metadata, output):
    provenance = {(entry['package'], entry['file']): entry['sha256'] for entry in json.loads((OVERRIDES / 'SOURCES.json').read_text(encoding='utf-8'))}
    ids = {node['id'] for node in metadata['resolve']['nodes']}
    packages = [p for p in metadata['packages'] if p['id'] in ids and p['id'] != metadata['resolve']['root']]
    inventory = []
    for package in sorted(packages, key=lambda p: (p['name'], p['version'])):
        identity = package['name'] + '-' + package['version']
        if not re.fullmatch(r'[A-Za-z0-9_.+-]+', identity):
            raise ValueError('Unsafe dependency identity.')
        folder = Path(package['manifest_path']).parent.resolve()
        files = [p for p in folder.iterdir() if p.is_file() and p.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'UNLICENSE'))]
        if package.get('license_file'):
            files.append(folder / package['license_file'])
        if (folder / 'LICENSES').is_dir():
            files.extend(p for p in (folder / 'LICENSES').rglob('*') if p.is_file())
        override = OVERRIDES / identity
        override_files = list(override.iterdir()) if override.is_dir() else []
        if not files and not override_files:
            raise ValueError('Review and pin upstream license text before packaging: ' + identity)
        destination = output / identity
        destination.mkdir(parents=True, exist_ok=True)
        copied = []
        for source in set(files + override_files):
            allowed = override.resolve() if source in override_files else folder
            if not source.resolve().is_relative_to(allowed) or not source.is_file():
                raise ValueError('Unsafe dependency license path: ' + identity)
            if source in override_files and hashlib.sha256(source.read_bytes()).hexdigest() != provenance.get((identity, source.name)):
                raise ValueError('Review the changed upstream license copy: ' + identity)
            relative = source.relative_to(override if source in override_files else folder)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(relative.as_posix())
        source_url = f"https://static.crates.io/crates/{package['name']}/{identity}.crate" if (package.get('source') or '').startswith('registry+') else package.get('repository')
        # Include unmodified MPL source alongside its notice, even for build dependencies.
        if 'MPL-2.0' in (package.get('license') or ''):
            for source in folder.rglob('*'):
                if source.is_file() and source.suffix in ('.rs', '.toml'):
                    if not source.resolve().is_relative_to(folder):
                        raise ValueError('Unsafe dependency source path: ' + identity)
                    target = destination / 'source' / source.relative_to(folder)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
        inventory.append({'name': package['name'], 'version': package['version'], 'license': package.get('license'),
                          'repository': package.get('repository'), 'source': source_url, 'notices': sorted(copied)})
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OVERRIDES / 'SOURCES.json', output / 'UPSTREAM-LICENSE-SOURCES.json')
    report = {'target': 'x86_64-pc-windows-msvc', 'packages': inventory,
              'cargo_lock_sha256': hashlib.sha256((ROOT / 'desktop/src-tauri/Cargo.lock').read_bytes()).hexdigest()}
    (output / 'inventory.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return len(inventory)


if __name__ == '__main__':
    cargo = shutil.which('cargo') or str(Path(os.environ.get('USERPROFILE', Path.home())) / '.cargo/bin/cargo.exe')
    result = subprocess.run([cargo, 'metadata', '--manifest-path', str(ROOT / 'desktop/src-tauri/Cargo.toml'),
                             '--locked', '--format-version', '1', '--filter-platform', 'x86_64-pc-windows-msvc'],
                            capture_output=True, text=True, encoding='utf-8', check=True)
    count = collect(json.loads(result.stdout), ROOT / 'build/licenses/rust')
    print(f'Collected pinned native notices for {count} Windows dependency packages.')
