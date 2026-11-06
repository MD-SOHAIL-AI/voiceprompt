import copy
import hashlib
import io
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from unittest.mock import patch, Mock

from voiceprompt.config import Settings
from voiceprompt.model_library import ModelLibrary, validate_catalog


def fixture():
    contents = {'model.bin': b'weights' * 100, 'config.json': b'{}', 'tokenizer.json': b'{}'}
    model = {'id': 'test-model', 'name': 'Test model', 'engine': 'whisper', 'variant': 'test', 'revision': 'abc123',
             'min_app': '0.6.3', 'license': 'MIT', 'source': 'https://huggingface.co/test/model', 'languages': ['en'],
             'files': [{'name': name, 'url': 'https://huggingface.co/test/model/resolve/abc123/' + name,
                        'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in contents.items()]}
    return {'schema': 1, 'version': 1, 'models': [model]}, contents


class Response(io.BytesIO):
    status = 200
    def __init__(self, data, address):
        super().__init__(data)
        self.address = address
    def geturl(self): return self.address


class ModelLibraryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.catalog, self.contents = fixture()
        self.requests = []
        def open_file(request, **kwargs):
            self.requests.append(request)
            return Response(self.contents[request.full_url.rsplit('/', 1)[1]], request.full_url)
        self.library = ModelLibrary(Path(self.directory.name) / 'library', catalog=self.catalog, opener=open_file)
        self.addCleanup(self.library.close)

    def finish(self):
        self.library.thread.join(3)
        self.assertFalse(self.library.thread.is_alive())

    def test_install_verify_select_delete_and_rediscover_without_redownload(self):
        self.library.download('test-model')
        self.finish()
        self.assertEqual(self.library.job['state'], 'complete')
        settings = Settings(selected_model_id='test-model')
        runtime = self.library.runtime_settings(settings, verify=True)
        self.assertTrue(Path(runtime.model_directory).is_dir())
        self.assertEqual(settings.model, 'base.en')
        rediscovered = ModelLibrary(self.library.root, catalog=self.catalog)
        self.assertTrue(rediscovered.snapshot('test-model')['models'][0]['installed'])
        freed = self.library.delete('test-model')
        self.assertEqual(freed, sum(map(len, self.contents.values())))
        self.assertFalse(self.library.snapshot('none')['models'][0]['installed'])
        self.assertEqual(len(self.library.catalog['models']), 1)

    def test_corrupt_download_never_becomes_installed(self):
        self.contents['model.bin'] = b'broken'
        self.library.download('test-model')
        self.finish()
        self.assertEqual(self.library.job['state'], 'error')
        self.assertNotIn('test-model', self.library.records)

    def test_interrupted_download_resumes_with_verified_range(self):
        staging = self.library.root / '.staging/test-model'
        staging.mkdir(parents=True)
        (staging / 'model.bin').write_bytes(self.contents['model.bin'][:10])
        def resume(request, **kwargs):
            data = self.contents[request.full_url.rsplit('/', 1)[1]]
            response = Response(data[10:] if request.get_header('Range') else data, request.full_url)
            if request.get_header('Range'): response.status = 206
            self.requests.append(request)
            return response
        self.library.opener = resume
        self.library.download('test-model'); self.finish()
        self.assertEqual(self.requests[0].get_header('Range'), 'bytes=10-')
        self.assertEqual(self.library.job['state'], 'complete')

    def test_pause_during_dictation_and_cancel_without_loading_weights(self):
        self.library.busy = lambda: True
        self.library.download('test-model')
        deadline = time.monotonic() + 1
        while self.library.job['state'] != 'paused' and time.monotonic() < deadline: time.sleep(.01)
        self.assertEqual(self.library.job['state'], 'paused')
        self.assertEqual(self.requests, [])
        self.library.cancelled.set()
        self.finish()
        self.assertEqual(self.library.job['state'], 'cancelled')
        self.library.delete('test-model')
        self.assertFalse((self.library.root / '.staging/test-model').exists())

    def test_cancel_cannot_overwrite_worker_completion_with_stuck_cancelling_state(self):
        library = self.library
        library.thread = SimpleNamespace(is_alive=lambda: True)
        library.job = {'state': 'paused'}
        class WorkerCompletion(threading.Event):
            def set(self):
                super().set()
                library.job['state'] = 'cancelled'
        library.cancelled = WorkerCompletion()
        library.cancel()
        self.assertEqual(library.job['state'], 'cancelled')

    def test_low_storage_is_actionable_and_keeps_other_models(self):
        with patch('voiceprompt.model_library.shutil.disk_usage', return_value=SimpleNamespace(free=1)):
            self.library.download('test-model')
            self.finish()
        self.assertIn('Not enough disk space', self.library.job['error'])

    def test_invalid_inventory_is_preserved_before_regeneration(self):
        path = self.library.root / 'inventory.json'
        path.write_text('[]', encoding='utf-8')
        repaired = ModelLibrary(self.library.root, catalog=self.catalog)
        repaired._save()
        self.assertEqual(path.with_suffix('.unreadable.bak').read_text(), '[]')

    def test_acceptance_profile_never_discovers_user_shared_caches(self):
        catalog = copy.deepcopy(self.catalog)
        catalog['models'][0]['repo'] = 'test/model'
        with patch.dict('os.environ', {'VOICEPROMPT_ACCEPTANCE_DIR': self.directory.name}), patch('huggingface_hub.try_to_load_from_cache') as cache:
            ModelLibrary(self.library.root, catalog=catalog)
        cache.assert_not_called()

    def test_changed_artifact_is_detected_before_loading(self):
        self.library.download('test-model'); self.finish()
        path = Path(self.library.records['test-model']['path']) / 'model.bin'
        path.write_bytes(b'x' * len(self.contents['model.bin']))
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            self.library.runtime_settings(Settings(selected_model_id='test-model'), verify=True)

    def test_delete_cannot_escape_app_storage(self):
        outside = Path(self.directory.name) / 'other-app'
        outside.mkdir()
        (outside / 'keep.txt').write_text('keep')
        self.library.records['test-model'] = {'ownership': 'owned', 'path': str(outside)}
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.library.delete('test-model')
        self.assertTrue((outside / 'keep.txt').exists())

    def test_shared_files_require_explicit_confirmation(self):
        self.library.records['test-model'] = {'ownership': 'shared', 'path': self.directory.name, 'kind': 'huggingface'}
        with self.assertRaisesRegex(ValueError, 'Confirm shared-cache'):
            self.library.delete('test-model')

    def shared_cache(self, revisions):
        hub = Path(self.directory.name) / 'hub'
        revision = 'a' * 40
        self.library.catalog['models'][0].update(repo='test/model', revision=revision)
        for repo_name, hashes in revisions.items():
            repo = hub / ('models--' + repo_name.replace('/', '--'))
            for index, commit in enumerate(hashes):
                snapshot = repo / 'snapshots' / commit
                snapshot.mkdir(parents=True)
                for name, data in self.contents.items(): (snapshot / name).write_bytes(data)
                (repo / 'refs').mkdir(exist_ok=True)
                (repo / 'refs' / ('main' if index == 0 else 'other')).write_text(commit)
        selected = hub / 'models--test--model/snapshots' / revision
        self.library.records['test-model'] = {'ownership': 'shared', 'kind': 'huggingface', 'path': str(selected)}
        return hub, selected

    def test_shared_deletion_is_scoped_when_another_repo_has_the_same_commit(self):
        hub, selected = self.shared_cache({'test/model': ['a' * 40], 'unrelated/fork': ['a' * 40]})
        untouched = hub / 'models--unrelated--fork'
        before = {str(p.relative_to(untouched)): p.read_bytes() for p in untouched.rglob('*') if p.is_file()}
        with patch('huggingface_hub.try_to_load_from_cache', return_value=str(selected / 'model.bin')):
            self.library.delete('test-model', allow_shared=True)
        self.assertFalse(selected.exists())
        self.assertEqual(before, {str(p.relative_to(untouched)): p.read_bytes() for p in untouched.rglob('*') if p.is_file()})

    def test_shared_deletion_preserves_other_revision_and_its_ref(self):
        hub, selected = self.shared_cache({'test/model': ['a' * 40, 'b' * 40]})
        other = selected.parent / ('b' * 40)
        with patch('huggingface_hub.try_to_load_from_cache', return_value=str(selected / 'model.bin')):
            self.library.delete('test-model', allow_shared=True)
        self.assertFalse(selected.exists())
        self.assertTrue((other / 'model.bin').exists())
        self.assertEqual((hub / 'models--test--model/refs/other').read_text(), 'b' * 40)

    def test_shared_deletion_preserves_blobs_referenced_by_another_revision(self):
        from huggingface_hub import scan_cache_dir
        hub, selected = self.shared_cache({'test/model': ['a' * 40, 'b' * 40]})
        blob = selected.parent.parent / 'blobs/shared-weights'
        blob.parent.mkdir()
        blob.write_bytes(self.contents['model.bin'])
        cache = scan_cache_dir(hub)
        # Model real shared-blob references without requiring Windows symlink privileges.
        repos = []
        for repo in cache.repos:
            revisions = []
            for revision in repo.revisions:
                files = frozenset(replace(file, blob_path=blob) if file.file_name == 'model.bin' else file for file in revision.files)
                revisions.append(replace(revision, files=files))
            repos.append(replace(repo, revisions=frozenset(revisions)))
        cache = replace(cache, repos=frozenset(repos))
        with patch('huggingface_hub.scan_cache_dir', return_value=cache), patch('huggingface_hub.try_to_load_from_cache', return_value=str(selected / 'model.bin')):
            self.library.delete('test-model', allow_shared=True)
        self.assertFalse(selected.exists())
        self.assertEqual(blob.read_bytes(), self.contents['model.bin'])
        self.assertTrue((selected.parent / ('b' * 40) / 'model.bin').is_file())

    def test_changed_shared_repository_path_is_rejected_before_deletion(self):
        hub, selected = self.shared_cache({'test/model': ['a' * 40]})
        with patch('huggingface_hub.try_to_load_from_cache', return_value=str(selected / 'model.bin')), patch('huggingface_hub.scan_cache_dir') as scan:
            self.library.catalog['models'][0]['repo'] = 'different/repo'
            with self.assertRaisesRegex(ValueError, 'layout changed'):
                self.library.delete('test-model', allow_shared=True)
        scan.assert_not_called()
        self.assertTrue((selected / 'model.bin').exists())

    def test_shared_deletion_rejects_a_plan_outside_the_selected_repository(self):
        hub, selected = self.shared_cache({'test/model': ['a' * 40]})
        strategy = SimpleNamespace(repos=frozenset({hub / 'unrelated'}), snapshots=frozenset(),
                                   refs=frozenset(), blobs=frozenset(), execute=Mock())
        with patch('huggingface_hub.try_to_load_from_cache', return_value=str(selected / 'model.bin')), patch('huggingface_hub.utils.HFCacheInfo.delete_revisions', return_value=strategy):
            with self.assertRaisesRegex(ValueError, 'leaves the selected repository'):
                self.library.delete('test-model', allow_shared=True)
        strategy.execute.assert_not_called()
        self.assertTrue((selected / 'model.bin').exists())

    def test_failed_shared_deletion_keeps_inventory_for_recovery(self):
        hub, selected = self.shared_cache({'test/model': ['a' * 40]})
        strategy = SimpleNamespace(repos=frozenset({selected.parent.parent}), snapshots=frozenset(),
                                   refs=frozenset(), blobs=frozenset(), expected_freed_size=100,
                                   execute=Mock(side_effect=PermissionError('model in use')))
        with patch('huggingface_hub.try_to_load_from_cache', return_value=str(selected / 'model.bin')), patch('huggingface_hub.utils.HFCacheInfo.delete_revisions', return_value=strategy):
            with self.assertRaises(PermissionError): self.library.delete('test-model', allow_shared=True)
        self.assertIn('test-model', self.library.records)
        self.assertTrue(selected.exists())

    def test_catalog_cannot_traverse_paths_or_introduce_code(self):
        for value in ('../../model.bin', '/model.bin', 'C:/model.bin', 'weights.dll', 'sub\\model.bin'):
            catalog = copy.deepcopy(self.catalog)
            catalog['models'][0]['files'][0]['name'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): validate_catalog(catalog)

    def test_catalog_rejects_unsupported_engine_and_untrusted_host(self):
        for field, value in [('engine', 'python-plugin'), ('revision', '../../outside')]:
            catalog = copy.deepcopy(self.catalog); catalog['models'][0][field] = value
            with self.assertRaises(ValueError): validate_catalog(catalog)
        catalog = copy.deepcopy(self.catalog)
        catalog['models'][0]['files'][0]['url'] = 'https://example.com/weights.bin'
        with self.assertRaises(ValueError): validate_catalog(catalog)

    def test_missing_and_deleted_models_never_download_implicitly(self):
        for model_id in ('test-model', 'none'):
            with self.assertRaises(ValueError): self.library.runtime_settings(Settings(selected_model_id=model_id), verify=True)
        self.assertEqual(self.requests, [])

    def test_shared_snapshot_discovery_handles_nested_model_files(self):
        catalog = copy.deepcopy(self.catalog)
        model = catalog['models'][0]
        model['repo'] = 'test/model'
        nested = dict(model['files'][1], name='weights/metadata.json', url='https://huggingface.co/test/model/resolve/abc123/weights/metadata.json')
        model['files'].insert(0, nested)
        snapshot = Path(self.directory.name) / 'hub/models--test--model/snapshots/abc123'
        (snapshot / 'weights').mkdir(parents=True)
        for file in model['files']:
            (snapshot / file['name']).write_bytes(self.contents.get(Path(file['name']).name, b'{}'))
        with patch('huggingface_hub.try_to_load_from_cache', return_value=str(snapshot / 'weights/metadata.json')):
            discovered = ModelLibrary(self.library.root, catalog=catalog)
        self.addCleanup(discovered.close)
        self.assertEqual(Path(discovered.records['test-model']['path']), snapshot)
        self.assertTrue(discovered.snapshot('test-model')['models'][0]['installed'])

    def test_catalog_refresh_keeps_installed_revision_and_rejects_rollback(self):
        self.library.download('test-model'); self.finish()
        updated = copy.deepcopy(self.catalog); updated['version'] = 2
        updated['models'][0]['id'] = 'new-model'
        self.library.apply_catalog(updated)
        self.assertTrue(self.library.snapshot('test-model')['models'][1]['installed'])
        with self.assertRaisesRegex(ValueError, 'older'): self.library.apply_catalog(self.catalog)
