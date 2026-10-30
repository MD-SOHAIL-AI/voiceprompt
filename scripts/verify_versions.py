"""The Python project version is canonical; reject stale release metadata."""
import json
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if sys.version_info < (3, 11):
    raise SystemExit('Python 3.11 or newer is required for the patched build dependencies.')
version = re.search(r'^version = "([^"]+)"', (root / 'pyproject.toml').read_text(), re.M)[1]
files = {'desktop/package.json': json.loads((root / 'desktop/package.json').read_text())['version'],
         'desktop/src-tauri/tauri.conf.json': json.loads((root / 'desktop/src-tauri/tauri.conf.json').read_text())['version'],
         'desktop/src-tauri/Cargo.toml': re.search(r'^version = "([^"]+)"', (root / 'desktop/src-tauri/Cargo.toml').read_text(), re.M)[1],
         'voiceprompt/__init__.py': re.search(r'__version__ = "([^"]+)"', (root / 'voiceprompt/__init__.py').read_text())[1]}
for name, value in files.items():
    if value != version: raise SystemExit(f'{name}: {value} differs from canonical version {version}')
settings_source = (root / 'desktop/src/pages/Settings.tsx').read_text(encoding='utf-8')
if 'Version {appVersion}' not in settings_source or 'version as appVersion' not in settings_source:
    raise SystemExit('Settings must display the package version, not a hardcoded release number.')
print(f'Build metadata agrees on {version}.')
