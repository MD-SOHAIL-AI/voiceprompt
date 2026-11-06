import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('catalog_publication', Path(__file__).resolve().parents[1] / 'scripts/publish_model_catalog.py')
publication = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publication)


class CatalogPublicationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.catalog = self.root / 'model-catalog.json'
        self.catalog.write_text('signed new catalog')
        self.calls = []

    def test_native_rejection_blocks_catalog_use(self):
        with patch.object(publication.subprocess, 'run', return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(ValueError, 'signature'):
                publication.verify(self.catalog, self.root / 'native.exe')

    def simulate(self, *, old_version=None, changed=False, corrupt=False):
        def check(args):
            self.calls.append(args)
            if args[1] == 'list':
                return json.dumps([] if old_version is None else [{'tagName': 'model-catalog', 'isDraft': False}])
            if args[1] == 'view':
                return json.dumps({'assets': [{'name': 'model-catalog.json'}]})
            if args[1] == 'download':
                folder = Path(args[args.index('--dir') + 1])
                (folder / 'model-catalog.json').write_text('previous' if folder.name == 'previous' else ('corrupt' if corrupt else self.catalog.read_text()))
            return ''
        def verify(path, native):
            return {'version': old_version if path.parent.name == 'previous' else 2,
                    'models': ['old' if changed and path.parent.name == 'previous' else 'model']}
        return patch.object(publication, 'check', side_effect=check), patch.object(publication, 'verify', side_effect=verify)

    def test_first_publication_promotes_only_after_download_verification(self):
        check, verify = self.simulate()
        with check, verify, patch.object(publication, 'ROOT', self.root), patch.object(publication.subprocess, 'check_output', return_value='commit'):
            self.assertTrue(publication.publish(self.catalog, 'native')['published'])
        actions = [call[1] for call in self.calls]
        self.assertLess(actions.index('download'), actions.index('edit'))
        self.assertIn('--draft', self.calls[1])

    def test_lower_version_never_replaces_published_catalog(self):
        check, verify = self.simulate(old_version=3)
        with check, verify, patch.object(publication, 'ROOT', self.root):
            with self.assertRaisesRegex(ValueError, 'rollback'):
                publication.publish(self.catalog, 'native')
        self.assertFalse(any(call[1] == 'upload' for call in self.calls))

    def test_changed_same_version_never_replaces_published_catalog(self):
        check, verify = self.simulate(old_version=2, changed=True)
        with check, verify, patch.object(publication, 'ROOT', self.root):
            with self.assertRaisesRegex(ValueError, 'new catalog version'):
                publication.publish(self.catalog, 'native')
        self.assertFalse(any(call[1] == 'upload' for call in self.calls))

    def test_failed_hosted_verification_restores_previous_catalog(self):
        check, verify = self.simulate(old_version=1, corrupt=True)
        with check, verify, patch.object(publication, 'ROOT', self.root):
            with self.assertRaisesRegex(ValueError, 'bytes'):
                publication.publish(self.catalog, 'native')
        uploads = [call for call in self.calls if call[1] == 'upload']
        self.assertEqual(len(uploads), 2)
        self.assertIn('previous', uploads[-1][3])
        self.assertFalse((self.root / 'build/catalog-publication.json').exists())
