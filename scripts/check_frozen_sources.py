"""Reject a frozen engine containing stale application bytecode."""
import argparse
import hashlib
import json
from pathlib import Path
import types
from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]


def normalized(code):
    return code.replace(co_filename='', co_consts=tuple(normalized(value) if isinstance(value, types.CodeType) else value for value in code.co_consts))


def verify(engine):
    archive = CArchiveReader(str(engine)).open_embedded_archive('PYZ.pyz')
    checked, mismatches = [], []
    digest = hashlib.sha256()
    for name in sorted(archive.toc):
        if name != 'voiceprompt' and not name.startswith('voiceprompt.'):
            continue
        path = ROOT / (name.replace('.', '/') + '.py')
        if not path.is_file():
            path = ROOT / name.replace('.', '/') / '__init__.py'
        if not path.is_file():
            raise ValueError('The frozen application contains an unknown source module: ' + name)
        source = path.read_bytes()
        expected = compile(source, str(path), 'exec', dont_inherit=True, optimize=0)
        if normalized(archive.extract(name)) != normalized(expected):
            mismatches.append(name)
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(source)
        checked.append(name)
    if 'voiceprompt.model_library' not in checked or len(checked) < 20:
        raise ValueError('The frozen application source inventory is incomplete.')
    return {'passed': not mismatches, 'checked_modules': len(checked), 'mismatches': mismatches,
            'packaged_python_source_sha256': digest.hexdigest(), 'engine_sha256': hashlib.sha256(engine.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/frozen-source-check.json')
    args = parser.parse_args()
    result = verify(args.engine)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    if not result['passed']:
        raise SystemExit('Packaged bytecode differs from the current source. Rebuild before packaging.')
