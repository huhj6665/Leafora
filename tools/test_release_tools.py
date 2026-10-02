"""Offline regression tests for publication filtering and overwrite protection."""
import tempfile
from pathlib import Path
import unittest

from export_public_source import export
from fix_release_whitespace import normalize
from release_audit import audit, excluded, local_secrets


class ReleaseTests(unittest.TestCase):
    def test_whitespace_normalization_preserves_bom_and_line_endings(self):
        original = b'\xef\xbb\xbfvalue = 1 \t\r\nnext = 2\r\n\r\n'
        expected = b'\xef\xbb\xbfvalue = 1\r\nnext = 2\r\n'
        self.assertEqual(normalize(original), expected)
        self.assertEqual(normalize(expected), expected)

    def test_whitespace_normalization_skips_binary_and_non_utf8(self):
        for data in (b'', b'\x00\x01 \r\n', b'\xff\xfe \r\n'):
            self.assertEqual(normalize(data), data)

    def test_private_paths_are_excluded_but_templates_and_code_stay(self):
        for name in ['.git/config', 'Web/backend/.env', 'TLD_project/runtime/device.env',
                     'Web/local/device_credentials/device.env', 'AGENTS.md',
                     'prompts/WEB_PROMPT.md', 'Web/frontend/node_modules/a.js',
                     'Web/docs/PRIVATE_HANDOFF.md', 'Web/local/broker.crt',
                     'Web/model_service/weights/train_best.pt', 'weixinapp/project.private.config.json']:
            self.assertTrue(excluded(Path(name)), name)
        for name in ['.gitignore', 'Web/backend/.env.example', 'TLD_project/device.env.example',
                     'Web/backend/app/services/assistant_service.py', 'assets/demo-field-a01.jpg']:
            self.assertFalse(excluded(Path(name)), name)

    def test_export_does_not_copy_old_history_or_env_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root, output = base / 'source', base / 'publish'
            root.mkdir()
            (root / 'README.md').write_text('Public source', encoding='utf-8')
            (root / '.env').write_text('PASSWORD=private-placeholder', encoding='utf-8')
            (root / '.git').mkdir()
            (root / '.git/config').write_text('old history', encoding='utf-8')
            export(root, output)
            self.assertTrue((output / 'README.md').exists())
            self.assertFalse((output / '.env').exists())
            self.assertFalse((output / '.git').exists())
            with self.assertRaises(ValueError):
                export(root, output)
            with self.assertRaises(ValueError):
                export(root, root / 'nested')

    def test_local_secret_match_reports_only_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Web/backend').mkdir(parents=True)
            secret = 'synthetic-' + 'private-fingerprint'
            (root / 'Web/backend/.env').write_text('JWT_SECRET_KEY=' + secret, encoding='utf-8')
            (root / 'bad.py').write_text('value="' + secret + '"', encoding='utf-8')
            report = audit(root, local_secrets(root))
            self.assertEqual(report['findings'][0]['rule'], 'local-secret-fingerprint')
            self.assertNotIn(secret, str(report))
            with self.assertRaises(ValueError):
                export(root, root.parent / 'never-export-this')


if __name__ == '__main__':
    unittest.main()
