import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('native_licenses', Path(__file__).resolve().parents[1] / 'scripts/collect_native_licenses.py')
licenses = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(licenses)


class NativeLicenseTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / 'desktop/src-tauri').mkdir(parents=True)
        (self.root / 'desktop/src-tauri/Cargo.lock').write_text('fixture lock')
        self.crate = self.root / 'crate'
        self.crate.mkdir()
        (self.crate / 'Cargo.toml').write_text('fixture manifest')
        self.overrides = self.root / 'overrides'
        self.overrides.mkdir()
        (self.overrides / 'SOURCES.json').write_text('[]')
        self.package = {'id':'fixture','name':'fixture','version':'1.0.0','manifest_path':str(self.crate / 'Cargo.toml'), 'license':'MPL-2.0', 'source':'registry+fixture', 'repository':'https://example.com/source'}
        self.metadata = {'packages':[self.package], 'resolve':{'nodes':[{'id':'fixture'}], 'root':'application'}}

    def collect(self):
        with patch.object(licenses,'ROOT',self.root), patch.object(licenses,'OVERRIDES',self.overrides):
            return licenses.collect(self.metadata, self.root / 'output')

    def test_notice_inventory_includes_unmodified_mpl_source(self):
        (self.crate / 'LICENSE').write_text('License fixture')
        (self.crate / 'lib.rs').write_text('pub fn fixture() {}')
        self.assertEqual(self.collect(),1)
        self.assertEqual((self.root / 'output/fixture-1.0.0/source/lib.rs').read_text(),'pub fn fixture() {}')
        report=json.loads((self.root / 'output/inventory.json').read_text())
        self.assertIn('fixture-1.0.0.crate',report['packages'][0]['source'])

    def test_missing_notice_blocks_packaging(self):
        with self.assertRaisesRegex(ValueError,'pin upstream'):
            self.collect()

    def test_license_file_cannot_escape_the_dependency(self):
        (self.root / 'outside').write_text('outside data')
        self.package['license_file']='../outside'
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            self.collect()
