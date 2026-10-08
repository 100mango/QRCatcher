"""Execute the actual event collector with real files and public-command doubles.

These are host protocol regressions, not Apple screenshot or export runtime proof.
Run in normal and optimized Python so safety never depends on assert statements.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import runpy
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import vision_runner_binding as lease
from vision_case_contract import select_case, case_identity
import owned_process_barrier as barrier
import vision_failure_diagnostic as failure


def identifier():
    return str(uuid.uuid4()).upper()


class VisionCollectorIntegrationTests(unittest.TestCase):
    def collect(self, mode):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); home = root / 'home'; work = root / 'work'; work.mkdir()
            device, source, nonce, request_id, store = identifier(), 'a' * 40, identifier(), identifier(), identifier()
            parent = home / 'Library/Developer/CoreSimulator/Devices' / device / 'data/Containers/Data/Application'
            runner, app = parent / identifier(), parent / identifier()
            (runner / 'tmp').mkdir(parents=True); app.mkdir()
            info = work / 'build/VisionTests/Build/Products/Debug-xrsimulator/QRCatcherVisionUITests-Runner.app/Info.plist'
            info.parent.mkdir(parents=True); info.write_bytes(plistlib.dumps({'CFBundleIdentifier': lease.RUNNER}))
            out = work / 'build/vision-runtime'; out.mkdir(); (out / 'ui-completed.marker').touch()
            exports = mode not in {'capture', 'wrong-source', 'failed-replacement', 'failure-native', 'failure-observed', 'failure-both'}
            kind = 'png' if mode == 'png' else 'json'
            case = select_case('visionos_photos' if exports else 'visionos_chinese')
            (runner / 'tmp' / f'QRCatcher-runner-{nonce}.json').write_text(json.dumps(
                {'id': nonce, 'runner': lease.RUNNER, 'pid': 12345, 'exports': exports, 'case': case.name}))
            name = ('vision-exported-qr' if kind == 'png' else 'vision-exported-history') if exports else 'vision-chinese-empty'
            if mode.startswith('failure-'): name = 'vision-failure'
            descriptor = {**case_identity(case, source, device), 'id': request_id, 'name': name, 'test_store': store, 'runner': lease.RUNNER,
                          'lease': nonce, 'pid': 12345, 'source_commit': source, 'device': device}
            if mode == 'wrong-source': descriptor['source_commit'] = 'b' * 40
            if mode == 'invalid-store': descriptor['test_store'] = '../foreign'
            if mode == 'lowercase-store': descriptor['test_store'] = store.lower()
            request = runner / 'tmp' / f'QRCatcher-capture-{request_id}.json'
            request.write_text(json.dumps(descriptor))
            log = f'QRCATCHER_VISION_RUNNER_READY:{nonce}\n'
            if mode == 'failed-replacement': log += f'QRCATCHER_VISION_RUNNER_READY:{identifier()}\n'
            if mode != 'failure-observed': log += f'QRCATCHER_VISION_CAPTURE_REQUEST:{request_id}\n'
            if mode in {'failure-observed', 'failure-both'}:
                log += f'error: -[QRCatcherVisionUITests.QRCatcherVisionUITests {case.name}] : failed - observed test issue\n'
            (work / 'run.log').write_text(log)
            if exports:
                receipt_directory = app / 'Documents/QRCatcherExportTestReceipts' / store
                receipt_directory.mkdir(parents=True)
                data = (b'bounded-test-png' if kind == 'png' else json.dumps(
                    {'format': 'QRCatcher.history', 'version': 1, 'records': [{'payload': 'QRCatcher 你好 🌈 123'}]}).encode())
                if mode == 'wrong-payload': data = data.replace(b'123', b'456')
                saved = receipt_directory / ('saved.' + kind); saved.write_bytes(data)
                receipt = {'test_store': store, 'type': kind, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                if mode == 'wrong-receipt': receipt['test_store'] = identifier()
                if mode == 'wrong-hash': receipt['sha256'] = '0' * 64
                receipt_file = receipt_directory / (kind + '.json'); receipt_file.write_text(json.dumps(receipt))
                if mode in {'documents-link', 'receipt-root-link', 'store-link'}:
                    victim = {'documents-link': app / 'Documents', 'receipt-root-link': receipt_directory.parent,
                              'store-link': receipt_directory}[mode]
                    foreign = root / 'foreign'; victim.rename(foreign); victim.symlink_to(foreign, target_is_directory=True)
                if mode in {'receipt-link', 'saved-link', 'receipt-hardlink', 'saved-hardlink'}:
                    victim = receipt_file if mode.startswith('receipt-') else saved
                    foreign = root / 'foreign'; victim.rename(foreign)
                    if mode.endswith('hardlink'): victim.hardlink_to(foreign)
                    else: victim.symlink_to(foreign)
                if mode == 'oversized-receipt': receipt_file.write_bytes(b' ' * 2049)
                if mode == 'oversized-saved': saved.write_bytes(b'x' * (2 * 1024 * 1024 + 1))
                if mode == 'saved-directory': saved.unlink(); saved.mkdir()
            commands = []

            def lookup(arguments, seconds, **kwargs):
                commands.append(('lookup', arguments))
                return 0, str(runner if arguments[-2] == lease.RUNNER else app), {'cleanup_confirmed': True}

            def command(arguments, **kwargs):
                commands.append(('command', arguments))
                if arguments[:3] == ['xcrun', 'simctl', 'io']: Path(arguments[-1]).write_bytes(b'raw-pixels')
                elif arguments[0] == 'sips': Path(arguments[-1]).write_bytes(b'jpeg-pixels')
                elif arguments[:2] == ['xcrun', 'swift']:
                    self.assertEqual(Path(arguments[-1]).read_bytes(), data)
                    self.assertEqual(Path(arguments[-1]).parent, Path('build/vision-runtime'))
                else: self.fail('Unexpected public command: ' + repr(arguments))
                return subprocess.CompletedProcess(arguments, 0, '', '')

            def diagnostic_command(arguments, seconds, **kwargs):
                commands.append(('diagnostic', arguments))
                Path(arguments[-1]).write_bytes(b'raw-pixels' if arguments[0] == 'xcrun' else b'\xff\xd8bounded-jpeg')
                return 0, '', {'state': 'completed', 'leader_reaped': True, 'exit': 0, 'timeout_seconds': seconds}

            code = 0; old = Path.cwd()
            try:
                os.chdir(work)
                with patch.object(Path, 'home', return_value=home), patch.object(lease, 'execute', side_effect=lookup), \
                     patch.object(barrier, 'blocked', return_value=False), patch.object(lease, 'blocked', return_value=False), \
                     patch.object(failure, 'blocked', return_value=False), patch.object(failure, 'execute', side_effect=diagnostic_command), \
                     patch('subprocess.run', side_effect=command), patch.dict(os.environ, {'GITHUB_SHA': source}), \
                     patch.object(sys, 'argv', ['capture_vision_checkpoints.py', device, 'run.log', case.scope]), \
                     contextlib.redirect_stdout(io.StringIO()):
                    try: runpy.run_path(str(SCRIPTS / 'capture_vision_checkpoints.py'), run_name='__main__')
                    except SystemExit as error: code = error.code
            finally:
                os.chdir(old)
            report = json.loads((out / 'checkpoint-captures.json').read_text()) if (out / 'checkpoint-captures.json').exists() else []
            diagnostic = json.loads((out / 'host-failure-capture.json').read_text()) if (out / 'host-failure-capture.json').exists() else None
            acknowledgement = json.loads(request.with_suffix('.ack').read_text()) if request.with_suffix('.ack').exists() else None
            return {'code': code, 'row': report[-1] if report else None, 'ack': acknowledgement, 'commands': commands, 'diagnostic': diagnostic,
                    'export_files': [path.name for path in out.glob('actual-export.*')],
                    'staged_files': [path.name for path in out.glob('*.export.png')]}

    def test_current_capture_and_both_export_protocols_succeed_without_late_discovery(self):
        for mode in ['capture', 'json', 'png']:
            with self.subTest(mode=mode):
                result = self.collect(mode)
                self.assertEqual(result['code'], 0); self.assertTrue(result['row']['success']); self.assertTrue(result['ack']['success'])
                self.assertEqual(sum(kind == 'lookup' for kind, _ in result['commands']), 1 if mode == 'capture' else 2)
                self.assertEqual(result['export_files'], [] if mode == 'capture' else ['actual-export.' + mode])
                self.assertEqual(result['staged_files'], [])

    def test_source_mismatch_and_failed_rebinding_forbid_capture_and_success_ack(self):
        for mode in ['wrong-source', 'failed-replacement']:
            with self.subTest(mode=mode): self.require_rejected(self.collect(mode))

    def test_observed_and_native_failure_share_one_diagnostic_and_remain_red(self):
        for mode in ['failure-observed', 'failure-native', 'failure-both']:
            with self.subTest(mode=mode):
                result = self.collect(mode)
                self.assertNotEqual(result['code'], 0)
                self.assertFalse(result['diagnostic']['success'])
                self.assertTrue(result['diagnostic']['diagnostic_only'])
                self.assertTrue(result['diagnostic']['pixels_retained'])
                self.assertEqual(len([c for c in result['commands'] if c[0] == 'diagnostic']), 2)
                self.assertEqual([c for c in result['commands'] if c[0] == 'command'], [])
                self.assertEqual(result['export_files'], [])
                if mode == 'failure-observed': self.assertIsNone(result['ack'])
                else:
                    self.assertFalse(result['ack']['success'])
                    self.assertTrue(result['ack']['diagnostic_only'])

    def test_every_export_ancestor_and_leaf_link_forbids_evidence_ack_and_commands(self):
        for mode in ['documents-link', 'receipt-root-link', 'store-link', 'receipt-link', 'saved-link',
                     'receipt-hardlink', 'saved-hardlink']:
            with self.subTest(mode=mode): self.require_rejected(self.collect(mode))

    def test_export_identity_size_and_contents_fail_closed_before_capture(self):
        for mode in ['invalid-store', 'lowercase-store', 'wrong-receipt', 'wrong-hash', 'wrong-payload',
                     'oversized-receipt', 'oversized-saved', 'saved-directory']:
            with self.subTest(mode=mode): self.require_rejected(self.collect(mode))

    def require_rejected(self, result):
        self.assertNotEqual(result['code'], 0); self.assertFalse(result['row']['success'])
        self.assertFalse(result['ack'] and result['ack'].get('success'))
        self.assertEqual(result['export_files'], []); self.assertEqual(result['staged_files'], [])
        self.assertEqual([arguments for kind, arguments in result['commands'] if kind == 'command'], [])


if __name__ == '__main__':
    unittest.main()
