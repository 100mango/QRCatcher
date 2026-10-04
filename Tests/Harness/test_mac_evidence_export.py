"""Exporter contract tests with command/file doubles, not app-runtime evidence."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/export_mac_screenshots.py'
CONTROLS = ['mac-before-resize', 'mac-minimum-window', 'mac-before-export', 'mac-pasted-url']


class MacEvidenceExportTests(unittest.TestCase):
    def export(self, names, *, same_pixels=(), allocation=3_000_000):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'scripts').mkdir()
            (root / 'scripts/evidence-allocation.json').write_text(json.dumps({'scope_limits_bytes': {'macos': allocation}}))
            (root / 'MacSandboxResults.xcresult').mkdir()
            (root / 'MacSandboxResults.xcresult/Info.plist').write_text('fixture')

            def output(command, **kwargs):
                if command == ['git', 'rev-parse', 'HEAD']: return 'a' * 40 + '\n'
                if command == ['git', 'rev-parse', 'HEAD^{tree}']: return 'b' * 40 + '\n'
                if command == ['xcodebuild', '-version']: return 'Xcode fixture\n'
                if command == ['uname', '-m']: return 'arm64\n'
                raise AssertionError(command)

            def run(command, **kwargs):
                if command[1:5] == ['xcresulttool', 'get', 'test-results', 'summary']:
                    return subprocess.CompletedProcess(command, 0, json.dumps({'runtimeWarnings': []}), '')
                if command[1:4] == ['xcresulttool', 'export', 'attachments']:
                    destination = root / command[-1]
                    destination.mkdir(parents=True, exist_ok=True)
                    entries = []
                    for number, name in enumerate(names):
                        filename = f'{number}.jpg'
                        # Only the exporter's byte-budget/retention contract is
                        # tested here. No synthetic bytes qualify as app pixels.
                        payload = b'\xff\xd8' + (b'same' if name in same_pixels else name.encode())
                        (destination / filename).write_bytes(payload)
                        entries.append({'name': name, 'exportedFileName': filename})
                    (destination / 'manifest.json').write_text(json.dumps(entries))
                    return subprocess.CompletedProcess(command, 0, '', '')
                raise AssertionError(command)

            previous = os.getcwd()
            try:
                os.chdir(root)
                with patch('subprocess.check_output', output), patch('subprocess.run', run), contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(str(SCRIPT), run_name='__main__')
                manifest = json.loads((root / 'build/mac-evidence/screenshots.json').read_text())
                size = sum(p.stat().st_size for p in (root / 'build/mac-evidence').iterdir())
                return manifest, size
            finally:
                os.chdir(previous)

    def test_all_four_control_checkpoints_are_retained(self):
        manifest, size = self.export(CONTROLS)
        self.assertEqual(len(manifest), 4)
        self.assertLessEqual(size, 3_000_000)

    def test_missing_control_fails_closed(self):
        with self.assertRaisesRegex(SystemExit, 'mac-before-export'):
            self.export([x for x in CONTROLS if x != 'mac-before-export'])

    def test_identical_bytes_preserve_checkpoint_alias(self):
        manifest, _ = self.export(CONTROLS, same_pixels=['mac-before-resize', 'mac-minimum-window'])
        self.assertEqual(len(manifest), 3)
        self.assertTrue(any('mac-before-resize' in x.get('additional_checkpoint_names', []) for x in manifest))

    def test_byte_cap_cannot_silently_drop_control(self):
        with self.assertRaisesRegex(SystemExit, 'Required fixed-state Mac control evidence missing'):
            self.export(CONTROLS, allocation=256 * 1024)

    def test_fourteen_image_cap_preserves_photos_and_controls(self):
        names = ['mac-failure', 'mac-system-picker-before-selection', 'mac-system-picker-after-selection',
                 'mac-real-photos-import', 'mac-sandbox-legacy-reopened', 'mac-chinese-policy',
                 'mac-english-policy', 'mac-reopened-history', 'mac-camera-unavailable', 'mac-pasted-url',
                 'mac-chinese-reopened', 'mac-minimum-window', 'mac-before-resize', 'mac-before-export',
                 'mac-imported-unicode']
        manifest, size = self.export(names)
        self.assertEqual(len(manifest), 14)
        for name in names[1:4] + CONTROLS:
            self.assertTrue(any(name in x['name'] for x in manifest), name)
        self.assertLessEqual(size, 3_000_000)


if __name__ == '__main__':
    unittest.main()
