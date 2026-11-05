"""Sign the reviewed model catalog with the existing release identity."""
import argparse
import base64
import json
from pathlib import Path
import sys
import tempfile

from release_updates import ROOT, run_signer, signing_environment
sys.path.insert(0, str(ROOT))
from voiceprompt.model_library import validate_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'voiceprompt/assets/model-catalog.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'release/model-catalog.json')
    args = parser.parse_args()
    catalog = validate_catalog(json.loads(args.catalog.read_text(encoding='utf-8')))
    catalog['app'] = 'VoicePrompt Models'
    payload = json.dumps(catalog, ensure_ascii=False, separators=(',', ':'))
    if len(payload.encode()) > 120 * 1024:
        raise ValueError('The model catalog exceeds its signed metadata limit.')
    with tempfile.TemporaryDirectory(prefix='catalog-sign-') as temporary:
        path = Path(temporary) / 'catalog.json'
        path.write_text(payload, encoding='utf-8')
        run_signer(['sign', str(path)], signing_environment())
        signature = base64.b64decode(Path(str(path) + '.sig').read_text().strip(), validate=True).decode('utf-8')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'payload': payload, 'signature': signature}), encoding='utf-8')
    print('Signed model catalog prepared. Publishing is a separate release action.')


if __name__ == '__main__': main()
