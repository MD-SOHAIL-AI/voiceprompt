"""Synchronize release identity, lockfiles and Windows numeric resources."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def set_version(version, root=ROOT):
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-(?:rc|beta|preview)\.[1-9]\d*)?', version)
    if not match:
        raise ValueError('Use MAJOR.MINOR.PATCH, optionally followed by -rc.N, -beta.N or -preview.N.')
    for name in ('pyproject.toml', 'desktop/src-tauri/Cargo.toml'):
        path = root / name
        text, count = re.subn(r'^version = "[^"]+"', f'version = "{version}"', path.read_text(), count=1, flags=re.M)
        if count != 1: raise ValueError(f'Missing version in {name}')
        path.write_text(text, encoding='utf-8')
    path = root / 'voiceprompt/__init__.py'
    path.write_text(re.sub(r'__version__ = "[^"]+"', f'__version__ = "{version}"', path.read_text()), encoding='utf-8')
    for name in ('desktop/package.json', 'desktop/package-lock.json', 'desktop/src-tauri/tauri.conf.json'):
        path = root / name
        data = json.loads(path.read_text())
        data['version'] = version
        if name.endswith('package-lock.json'): data['packages']['']['version'] = version
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    path = root / 'desktop/src-tauri/Cargo.lock'
    text, count = re.subn(r'(name = "voiceprompt-desktop"\nversion = ")[^"]+', r'\g<1>' + version, path.read_text(), count=1)
    if count != 1: raise ValueError('Missing desktop package in Cargo.lock')
    path.write_text(text, encoding='utf-8')
    path = root / 'packaging/version.txt'
    text = path.read_text()
    numeric = ', '.join([*match.groups(), '0'])
    text = re.sub(r'(filevers|prodvers)=\([^)]+\)', lambda item: item[1] + '=(' + numeric + ')', text)
    text = re.sub(r"(StringStruct\('(?:FileVersion|ProductVersion)', ')[^']+", r'\g<1>' + version, text)
    path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version')
    set_version(parser.parse_args().version)
