import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('frozen_sources', Path(__file__).resolve().parents[1] / 'scripts/check_frozen_sources.py')
sources = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sources)


class FrozenSourceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / 'voiceprompt').mkdir()
        self.engine = self.root / 'engine.exe'
        self.engine.write_bytes(b'packaging fixture')
        self.code = {}
        for name in ['model_library'] + [f'module_{n}' for n in range(20)]:
            source = 'def run():\n    return "current"\n'
            (self.root / f'voiceprompt/{name}.py').write_text(source)
            self.code['voiceprompt.' + name] = compile(source, 'different/build/path.py', 'exec')
        self.archive = Mock(toc=self.code, extract=lambda name: self.code[name])

    def check(self):
        with patch.object(sources, 'ROOT', self.root), patch.object(sources, 'CArchiveReader') as reader:
            reader.return_value.open_embedded_archive.return_value = self.archive
            return sources.verify(self.engine)

    def test_current_code_passes_independent_of_build_paths(self):
        self.assertTrue(self.check()['passed'])

    def test_stale_nested_function_is_reported(self):
        self.code['voiceprompt.model_library'] = compile('def run():\n    return "stale"\n', 'old.py', 'exec')
        result = self.check()
        self.assertFalse(result['passed'])
        self.assertEqual(result['mismatches'], ['voiceprompt.model_library'])

    def test_unknown_application_code_is_rejected(self):
        self.code['voiceprompt.unknown'] = compile('pass', 'unknown.py', 'exec')
        with self.assertRaisesRegex(ValueError, 'unknown source module'):
            self.check()
