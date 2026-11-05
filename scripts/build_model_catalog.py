"""Build a pinned catalog from verified local caches; no weights are downloaded.

New architectures require an app adapter. Review licenses and run recognition
acceptance before publishing this data with sign_model_catalog.py.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def main():
    from huggingface_hub import scan_cache_dir
    from moonshine_voice import download as moon, ModelArch
    from moonshine_voice.download_file import get_cache_dir
    repos = {r.repo_id: r for r in scan_cache_dir().repos}
    models = []
    specs = [
        ('whisper-tiny-en', 'Whisper Tiny English', 'whisper', 'Systran/faster-whisper-tiny.en', 'tiny.en', 'MIT'),
        ('whisper-base-en', 'Whisper Base English', 'whisper', 'Systran/faster-whisper-base.en', 'base.en', 'MIT'),
        ('whisper-small', 'Whisper Small Multilingual', 'whisper', 'Systran/faster-whisper-small', 'small', 'MIT'),
        ('whisper-distil-small-en', 'Distil Whisper Small English', 'whisper', 'Systran/faster-distil-whisper-small.en', 'Systran/faster-distil-whisper-small.en', 'MIT'),
        ('parakeet-v2-int8', 'Parakeet v2 INT8', 'parakeet', 'csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8', '', 'CC-BY-4.0'),
        ('nemotron-q8', 'Nemotron Streaming Q8', 'nemotron', 'nvidia/nemotron-speech-streaming-en-0.6b', '', 'NVIDIA Open Model License'),
    ]
    for model_id, name, engine, repo_id, variant, license_name in specs:
        repo = repos[repo_id]
        revision = max(repo.revisions, key=lambda r: r.last_modified)
        files = []
        for file in sorted(revision.files, key=lambda f: f.file_name):
            files.append({'name': file.file_name, 'url': f'https://huggingface.co/{repo_id}/resolve/{revision.commit_hash}/{file.file_name}',
                          'size': file.size_on_disk, 'sha256': digest(file.file_path)})
        if engine == 'whisper' and not any(f['name'] == 'model.bin' for f in files):
            raise ValueError(f'{name} is not complete in this cache')
        models.append({'id': model_id, 'name': name, 'engine': engine, 'variant': variant, 'revision': revision.commit_hash,
                       'repo': repo_id, 'languages': ['multilingual'] if model_id == 'whisper-small' else ['en'],
                       'license': license_name, 'source': f'https://huggingface.co/{repo_id}', 'files': files})
    for variant, arch in [('tiny', ModelArch.TINY_STREAMING), ('small', ModelArch.SMALL_STREAMING)]:
        info = moon.find_model_info('en', arch)
        group = moon._primary_stt_group(info, include_word_timestamps=False)
        cached = get_cache_dir() / group['base_url'].removeprefix('https://')
        files = [{'name': f['name'], 'url': f['url'], 'size': f['size'], 'sha256': digest(cached / f['name'])} for f in group['files']]
        models.append({'id': 'moonshine-' + variant, 'name': 'Moonshine ' + variant.title() + ' English',
                       'engine': 'moonshine', 'variant': variant, 'revision': group['base_url'].rsplit('/', 1)[1],
                       'languages': ['en'], 'license': 'MIT', 'source': 'https://github.com/moonshine-ai/moonshine',
                       'legacy_url': group['base_url'], 'files': files})
    for model in models:
        model.update(min_app='0.6.3', ram_mb=None, performance='Not benchmarked on this computer')
    destination = ROOT / 'voiceprompt/assets/model-catalog.json'
    destination.write_text(json.dumps({'app': 'VoicePrompt Models', 'schema': 1, 'version': 1, 'models': models}, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(models)} pinned models; verify recognition and licensing before publication.')


if __name__ == '__main__':
    main()
