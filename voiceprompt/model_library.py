"""A local inventory of pinned weights; catalog data never introduces code."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import threading
import time
import urllib.request
from dataclasses import replace
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from platformdirs import user_cache_dir

from voiceprompt.config import config_dir

BUNDLED_CATALOG = Path(__file__).parent / 'assets/model-catalog.json'
ENGINES = {'whisper', 'moonshine', 'parakeet', 'nemotron'}


def moonshine_cache():
    # Pinned SDK cache convention, without importing its native DLL into the
    # controller. Recognition libraries belong only in the isolated worker.
    return Path(os.environ.get('MOONSHINE_VOICE_CACHE', user_cache_dir('moonshine_voice')))


def file_hash(path, before_chunk=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            if before_chunk is not None:
                before_chunk()
            digest.update(chunk)
    return digest.hexdigest()


def safe_url(value):
    parsed = urlsplit(value)
    host = parsed.hostname or ''
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Model downloads require an approved HTTPS address.')
    if not (host in {'huggingface.co', 'download.moonshine.ai', 'github.com', 'release-assets.githubusercontent.com'} or host.endswith(('.hf.co', '.huggingface.co'))):
        raise ValueError('This model download host is not supported.')
    return value


def validate_catalog(catalog):
    if not isinstance(catalog, dict) or catalog.get('schema') != 1 or type(catalog.get('version')) is not int or catalog['version'] < 1:
        raise ValueError('Unsupported model catalog.')
    models = catalog.get('models')
    if not isinstance(models, list) or not 1 <= len(models) <= 200:
        raise ValueError('Invalid model catalog size.')
    ids = set()
    for model in models:
        if not isinstance(model, dict) or not isinstance(model.get('id'), str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', model['id']) or model['id'] in ids:
            raise ValueError('Invalid or repeated model identity.')
        ids.add(model['id'])
        if not isinstance(model.get('engine'), str) or model['engine'] not in ENGINES or not isinstance(model.get('revision'), str) or not re.fullmatch(r'[a-zA-Z0-9._-]{1,80}', model['revision']):
            raise ValueError('This catalog requires an unsupported engine.')
        for key in ('name', 'license', 'source', 'min_app'):
            if not isinstance(model.get(key), str) or not 1 <= len(model[key]) <= 512:
                raise ValueError('Model metadata is incomplete.')
        if not re.fullmatch(r'\d+\.\d+\.\d+', model['min_app']):
            raise ValueError('Invalid model compatibility version.')
        languages = model.get('languages')
        if not isinstance(languages, list) or not 1 <= len(languages) <= 64 or any(not isinstance(v, str) or not 1 <= len(v) <= 64 for v in languages):
            raise ValueError('Model languages are invalid.')
        if model.get('performance') is not None and (not isinstance(model['performance'], str) or len(model['performance']) > 512):
            raise ValueError('Model performance information is invalid.')
        if model.get('ram_mb') is not None and (type(model['ram_mb']) is not int or not 0 < model['ram_mb'] <= 1048576):
            raise ValueError('Model memory estimate is invalid.')
        if model['engine'] == 'whisper' and (not isinstance(model.get('variant'), str) or not 1 <= len(model['variant']) <= 512):
            raise ValueError('Whisper model identity is missing.')
        if model.get('repo') is not None and (not isinstance(model['repo'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', model['repo'])):
            raise ValueError('Invalid model repository.')
        if model['engine'] == 'moonshine' and model.get('variant') not in {'tiny', 'small'}:
            raise ValueError('This Moonshine architecture needs an app update.')
        files = model.get('files')
        if not isinstance(files, list) or not 1 <= len(files) <= 40:
            raise ValueError('Model artifacts are missing.')
        names = set()
        for file in files:
            if not isinstance(file, dict) or not isinstance(file.get('name'), str):
                raise ValueError('Invalid model artifact.')
            name = file.get('name', '')
            path = PurePosixPath(name)
            if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or name.casefold() in names:
                raise ValueError('Unsafe model artifact path.')
            if path.suffix.lower() not in {'.bin', '.gguf', '.onnx', '.ort', '.json', '.txt'}:
                raise ValueError('Model catalogs cannot install executable code.')
            names.add(name.casefold())
            if type(file.get('size')) is not int or not 0 < file['size'] <= 10 * 1024**3 or not isinstance(file.get('sha256'), str) or not re.fullmatch('[a-f0-9]{64}', file['sha256']):
                raise ValueError('Model artifact verification data is invalid.')
            if not isinstance(file.get('url'), str):
                raise ValueError('Model artifact address is missing.')
            safe_url(file['url'])
        required = {'whisper': {'model.bin', 'config.json', 'tokenizer.json'},
                    'parakeet': {'encoder.int8.onnx', 'decoder.int8.onnx', 'joiner.int8.onnx', 'tokens.txt'},
                    'nemotron': {'nemotron-speech-streaming-en-0.6b.q8_0.gguf'}, 'moonshine': {'streaming_config.json'}}
        if not required[model['engine']].issubset(names):
            raise ValueError('The model does not match its engine format.')
    return catalog


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ModelLibrary:
    def __init__(self, directory=None, *, busy=lambda: False, catalog=None, opener=None):
        self.root = (Path(directory) if directory else config_dir() / 'models/library').resolve()
        self.storage_warning = ''
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.storage_warning = 'Model storage is read-only. Existing cached models can still be used.'
        self.busy = busy
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.job = {'state': 'idle'}
        self.thread = None
        self.verified = {}
        self.opener = opener or urllib.request.build_opener(_Redirects()).open
        self.catalog = validate_catalog(catalog or json.loads(BUNDLED_CATALOG.read_text(encoding='utf-8')))
        self.records = {}
        self.inventory_invalid = False
        try:
            data = json.loads((self.root / 'inventory.json').read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('installed'), dict):
                raise ValueError('Invalid model inventory')
            self.records = {key: record for key, record in data['installed'].items()
                            if isinstance(record, dict) and isinstance(record.get('path'), str)
                            and record.get('ownership') in {'owned', 'shared'}}
        except (OSError, ValueError, KeyError, TypeError):
            self.inventory_invalid = (self.root / 'inventory.json').exists()
        self._discover()

    def _save(self):
        path = self.root / 'inventory.json'
        if self.inventory_invalid and path.exists():
            backup = path.with_suffix('.unreadable.bak')
            if not backup.exists(): shutil.copy2(path, backup)
            self.inventory_invalid = False
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'version': 1, 'installed': self.records}), encoding='utf-8')
        temporary.replace(path)

    def model(self, model_id):
        model = next((m for m in self.catalog['models'] if m['id'] == model_id), None)
        if model is None:
            raise ValueError('This model is no longer in the catalog. Refresh the model list.')
        return model

    def _compatible(self, model):
        from voiceprompt import __version__
        current = re.match(r'(\d+)\.(\d+)\.(\d+)', __version__)
        return tuple(map(int, current.groups())) >= tuple(map(int, model['min_app'].split('.')))

    def _owned(self, path):
        path = Path(path)
        if path.is_symlink() or not path.resolve().is_relative_to(self.root) or path.resolve() == self.root:
            raise ValueError('The model path is outside VoicePrompt storage.')
        return path

    def _paths(self, model, record):
        folder = Path(record['path'])
        if record.get('ownership') == 'owned':
            self._owned(folder)
        return [(folder / file['name'], file) for file in model['files']]

    def _complete(self, model, record):
        try:
            return all(path.is_file() and path.stat().st_size == file['size'] for path, file in self._paths(model, record))
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def _discover(self):
        # No scans of unrelated repositories, downloads, copying, or deletion.
        from huggingface_hub import try_to_load_from_cache
        for model in self.catalog['models']:
            record = self.records.get(model['id'])
            if record and self._complete(model, record):
                continue
            owned = {'path': str(self.root / model['id'] / model['revision']), 'ownership': 'owned'}
            if Path(owned['path']).exists():
                self.records[model['id']] = owned
                continue
            if os.environ.get('VOICEPROMPT_ACCEPTANCE_DIR'):
                continue
            if model.get('repo'):
                first = try_to_load_from_cache(model['repo'], model['files'][0]['name'], revision=model['revision'])
                if not isinstance(first, str):
                    continue
                snapshot = Path(first)
                for _ in PurePosixPath(model['files'][0]['name']).parts:
                    snapshot = snapshot.parent
                record = {'path': str(snapshot), 'ownership': 'shared', 'kind': 'huggingface',
                          'repo': model['repo'], 'revision': model['revision']}
            elif model.get('legacy_url'):
                record = {'path': str(moonshine_cache() / model['legacy_url'].removeprefix('https://')),
                          'ownership': 'shared', 'kind': 'moonshine'}
            if record and Path(record['path']).is_dir():
                self.records[model['id']] = record

    def snapshot(self, selected):
        with self.lock:
            rows = []
            for model in self.catalog['models']:
                row = {k: v for k, v in model.items() if k not in {'files', 'legacy_url'}}
                record = self.records.get(model['id'])
                installed = bool(record and self._complete(model, record))
                disk_bytes = 0
                if record:
                    try:
                        disk_bytes = sum(path.stat().st_size for path, _ in self._paths(model, record) if path.is_file())
                    except (OSError, ValueError, KeyError):
                        pass
                staging = self._owned(self.root / '.staging' / model['id'])
                partial_bytes = sum(p.stat().st_size for p in staging.rglob('*') if p.is_file()) if staging.exists() else 0
                row.update(installed=installed, ownership=record.get('ownership') if installed else None,
                           downloadBytes=sum(f['size'] for f in model['files']),
                           diskBytes=disk_bytes + partial_bytes, hasFiles=bool(disk_bytes or partial_bytes),
                           selected=model['id'] == selected, compatible=self._compatible(model))
                if record and disk_bytes:
                    row['ownership'] = record.get('ownership')
                measurement = record.get('measurement') if record else None
                row['measurement'] = {key: value for key, value in measurement.items()
                                      if key in {'peakRamMb', 'lastFinishSeconds'} and type(value) in (int, float) and math.isfinite(value) and value >= 0} if isinstance(measurement, dict) else None
                rows.append(row)
            return {'models': rows, 'operation': dict(self.job), 'catalogVersion': self.catalog['version'], 'storageWarning': self.storage_warning}

    def observe(self, model_id, metrics):
        with self.lock:
            record = self.records.get(model_id)
            if not record:
                return
            measurement = dict(record.get('measurement', {}))
            for source, target in [('worker_peak_mb', 'peakRamMb'), ('release_to_final_seconds', 'lastFinishSeconds')]:
                value = metrics.get(source)
                if type(value) in (int, float) and value >= 0:
                    measurement[target] = round(value, 2)
            if measurement:
                record['measurement'] = measurement
                self._save()

    def apply_catalog(self, catalog):
        validate_catalog(catalog)
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('Finish the model download before refreshing the catalog.')
            if catalog['version'] < self.catalog['version']:
                raise ValueError('The catalog is older than the installed catalog.')
            # Installed revisions stay usable even if a newer catalog drops them.
            ids = {m['id'] for m in catalog['models']}
            retained = [m for m in self.catalog['models'] if m['id'] in self.records and m['id'] not in ids]
            for model in catalog['models']:
                old = next((m for m in self.catalog['models'] if m['id'] == model['id']), None)
                pinned = ('engine', 'variant', 'revision', 'files', 'repo', 'legacy_url')
                if old and model['id'] in self.records and any(old.get(k) != model.get(k) for k in pinned):
                    raise ValueError('Publish a new model identity for a changed installed revision.')
            self.catalog = copy.deepcopy(catalog)
            self.catalog['models'].extend(retained)
            self._discover()

    def runtime_settings(self, settings, *, verify=False):
        result = copy.deepcopy(settings)
        model_id = settings.selected_model_id
        if model_id == 'none':
            raise ValueError('Download and select a model in Settings → Models before dictating.')
        if model_id == 'legacy':
            return result
        model = self.model(model_id)
        if not self._compatible(model):
            raise ValueError('Update VoicePrompt to use this model.')
        record = self.records.get(model_id)
        if not record or not self._complete(model, record):
            if verify:
                raise ValueError(f"Download {model['name']} in Settings → Models, then prepare it.")
            return result
        if verify:
            for path, file in self._paths(model, record):
                key = (str(path), path.stat().st_size, path.stat().st_mtime_ns, file['sha256'])
                if key not in self.verified:
                    if file_hash(path) != file['sha256']:
                        raise ValueError('Model verification failed. Delete and download this model again.')
                    self.verified[key] = True
        result.backend = model['engine']
        result.model_directory = record['path']  # Worker-only attribute; never persisted.
        if result.backend == 'whisper':
            result.model = record['path']
        elif result.backend == 'moonshine':
            result.streaming_model = model['variant']
        return result

    def download(self, model_id):
        with self.lock:
            model = copy.deepcopy(self.model(model_id))
            if not self._compatible(model):
                raise ValueError('Update VoicePrompt to download this model.')
            if self.thread and self.thread.is_alive():
                raise ValueError('Finish or cancel the current model download first.')
            if self.records.get(model_id) and self._complete(model, self.records[model_id]):
                return
            self.cancelled.clear()
            self.job = {'state': 'downloading', 'id': model_id, 'completed': 0, 'total': sum(f['size'] for f in model['files'])}
            self.thread = threading.Thread(target=self._download, args=(model,), name='model-download', daemon=True)
            self.thread.start()

    def _wait(self):
        while self.busy():
            self.job['state'] = 'paused'
            if self.cancelled.wait(.1):
                raise InterruptedError
        if self.cancelled.is_set():
            raise InterruptedError
        self.job['state'] = 'downloading'

    def cancel(self):
        if self.thread and self.thread.is_alive() and self.job.get('state') in {'downloading', 'paused'}:
            self.job['state'] = 'cancelling'
        self.cancelled.set()

    def _download(self, model):
        staging = self._owned(self.root / '.staging' / model['id'])
        try:
            staging.mkdir(parents=True, exist_ok=True)
            missing = sum(max(0, f['size'] - min(f['size'], (staging / f['name']).stat().st_size if (staging / f['name']).exists() else 0)) for f in model['files'])
            if shutil.disk_usage(self.root).free < missing + 16 * 1024**2:
                raise ValueError('Not enough disk space. Delete an installed model and retry.')
            completed = 0
            for file in model['files']:
                self._wait()
                path = self._owned(staging / file['name'])
                path.parent.mkdir(parents=True, exist_ok=True)
                size = path.stat().st_size if path.exists() else 0
                if size != file['size'] or file_hash(path, self._wait) != file['sha256']:
                    offset = size if size < file['size'] else 0
                    headers = {'User-Agent': 'VoicePrompt', 'Accept-Encoding': 'identity'}
                    if offset:
                        headers['Range'] = f'bytes={offset}-'
                    request = urllib.request.Request(safe_url(file['url']), headers=headers)
                    with self.opener(request, timeout=30) as source:
                        safe_url(source.geturl())
                        if getattr(source, 'status', 200) != 206:
                            offset = 0
                        with path.open('ab' if offset else 'wb') as output:
                            current = offset
                            while True:
                                self._wait()
                                chunk = source.read(256 * 1024)
                                if not chunk:
                                    break
                                current += len(chunk)
                                if current > file['size']:
                                    raise ValueError('The model download exceeded its verified size.')
                                output.write(chunk)
                                self.job.update(completed=completed + current, name=file['name'])
                    if path.stat().st_size != file['size'] or file_hash(path, self._wait) != file['sha256']:
                        path.unlink(missing_ok=True)
                        raise ValueError('Model download verification failed. Retry the download.')
                completed += file['size']
                self.job['completed'] = completed
            self._wait()
            destination = self._owned(self.root / model['id'] / model['revision'])
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise ValueError('An incomplete installation exists. Delete it before retrying.')
            os.replace(staging, destination)
            with self.lock:
                self.records[model['id']] = {'path': str(destination), 'ownership': 'owned'}
                self._save()
                self.job['state'] = 'complete'
        except InterruptedError:
            self.job['state'] = 'cancelled'
        except Exception as exc:
            self.job.update(state='error', error=str(exc) if isinstance(exc, ValueError) else 'The download was interrupted. Check your connection and retry.')

    def delete(self, model_id, *, allow_shared=False):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('Cancel the model download before deleting files.')
            model = self.model(model_id)
            record = self.records.get(model_id)
            freed = 0
            if record:
                if record.get('ownership') == 'shared' and not allow_shared:
                    raise ValueError('These cached files may be used by other apps. Confirm shared-cache removal first.')
                if record.get('kind') == 'huggingface':
                    from huggingface_hub import scan_cache_dir, try_to_load_from_cache
                    first = try_to_load_from_cache(model['repo'], model['files'][0]['name'], revision=model['revision'])
                    snapshot = Path(first) if isinstance(first, str) else None
                    if snapshot is not None:
                        for _ in PurePosixPath(model['files'][0]['name']).parts:
                            snapshot = snapshot.parent
                    if snapshot is None or snapshot.resolve() != Path(record['path']).resolve():
                        raise ValueError('The shared cache changed. Refresh before deleting.')
                    snapshot = snapshot.resolve()
                    repository = snapshot.parent.parent
                    if snapshot.name != model['revision'] or snapshot.parent.name != 'snapshots' or repository.name != 'models--' + model['repo'].replace('/', '--'):
                        raise ValueError('The shared cache layout changed. Refresh before deleting.')
                    cache = scan_cache_dir(repository.parent)
                    selected = [repo for repo in cache.repos if repo.repo_id == model['repo'] and repo.repo_type == 'model' and repo.repo_path.resolve() == repository]
                    if len(selected) != 1:
                        raise ValueError('The selected shared repository could not be verified.')
                    # Revision identities can be retained by forks. A global
                    # hash lookup can otherwise plan deletion of another repo.
                    strategy = replace(cache, repos=frozenset(selected)).delete_revisions(model['revision'])
                    paths = strategy.repos | strategy.snapshots | strategy.refs | strategy.blobs
                    if not paths or any(not path.resolve().is_relative_to(repository.resolve()) for path in paths):
                        raise ValueError('The cache deletion plan leaves the selected repository.')
                    if any(path.resolve() != repository for path in strategy.repos) or any(path.resolve() != snapshot for path in strategy.snapshots):
                        raise ValueError('The cache deletion plan includes another model revision.')
                    freed = strategy.expected_freed_size
                    strategy.execute()
                    if any(path.exists() for path, _ in self._paths(model, record)):
                        raise ValueError('The shared cache could not be completely removed. Close other apps using it and retry.')
                elif record.get('kind') == 'moonshine':
                    expected = moonshine_cache() / model['legacy_url'].removeprefix('https://')
                    if Path(record['path']).resolve() != expected.resolve():
                        raise ValueError('The shared cache path changed.')
                    for path, file in self._paths(model, record):
                        if path.is_symlink() or not path.resolve().is_relative_to(expected.resolve()):
                            raise ValueError('Unsafe shared-cache path.')
                        if path.exists():
                            freed += path.stat().st_size
                            path.unlink()
                else:
                    folder = self._owned(record['path'])
                    freed = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file()) if folder.exists() else 0
                    if folder.exists():
                        shutil.rmtree(folder, ignore_errors=False)
                self.records.pop(model_id, None)
                self._save()
            staging = self._owned(self.root / '.staging' / model_id)
            if staging.exists():
                freed += sum(p.stat().st_size for p in staging.rglob('*') if p.is_file())
                shutil.rmtree(staging)
            self.job = {'state': 'deleted', 'id': model_id, 'freedBytes': freed}
            return freed

    def close(self):
        self.cancelled.set()
