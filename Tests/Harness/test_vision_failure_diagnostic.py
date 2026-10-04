"""Failure-only command routing with owned synthetic files; no Apple runtime proof."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import vision_failure_diagnostic as failure
import vision_runner_binding as binding
from vision_case_contract import select_case


class VisionFailureDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.device, self.nonce = str(uuid.uuid4()).upper(), str(uuid.uuid4()).upper()
        self.case = select_case('visionos_chinese')
        devices = self.root / 'Devices'
        self.container = devices / self.device / 'data/Containers/Data/Application' / str(uuid.uuid4()).upper()
        (self.container / 'tmp').mkdir(parents=True)
        self.out = self.root / 'output'; self.out.mkdir()
        self.value = {'id': self.nonce, 'runner': binding.RUNNER, 'pid': 12345,
                      'exports': False, 'case': self.case.name}
        self.nonce_file = self.container / 'tmp' / ('QRCatcher-runner-' + self.nonce + '.json')
        self.nonce_file.write_text(json.dumps(self.value))
        self.bound = binding.RunnerBinding(self.device, binding.RUNNER, 'a' * 40, self.case,
                                           devices, lambda _: str(self.container))
        for module in [binding, failure]:
            guard = patch.object(module, 'blocked', return_value=False); guard.start(); self.addCleanup(guard.stop)
        self.bound.prime(self.nonce)
        self.diagnostic = failure.FailureDiagnostic(self.bound, self.out)
        self.calls = []

    def execute(self, args, seconds, **kwargs):
        self.calls.append((args, seconds))
        Path(args[-1]).write_bytes(b'raw' if args[0] == 'xcrun' else b'\xff\xd8bounded-owned-jpeg')
        return 0, '', {'state': 'completed', 'leader_reaped': True, 'exit': 0, 'timeout_seconds': seconds}

    def capture(self, callback=None):
        with patch.object(failure, 'execute', side_effect=callback or self.execute):
            return self.diagnostic.capture('matching XCTest failure')

    def test_one_failure_image_is_bound_and_never_success_or_ack(self):
        row = self.capture()
        self.assertFalse(row['success']); self.assertTrue(row['diagnostic_only'])
        self.assertTrue(row['capture_success']); self.assertTrue(row['pixels_retained'])
        for key, value in self.bound.case_identity.items(): self.assertEqual(row[key], value)
        self.assertEqual(row['lease'], self.nonce)
        data = (self.out / row['file']).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
        self.assertEqual([seconds for _, seconds in self.calls], [20, 12])
        self.assertEqual(self.diagnostic.capture('native failure request'), row)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(list(self.out.glob('*.ack')), [])
        self.assertEqual(list(self.out.glob('*.raw.png')), [])

    def test_only_exact_selected_error_triggers_one_attempt(self):
        with patch.object(failure, 'execute', side_effect=self.execute):
            self.diagnostic.observe('error: -[QRCatcherVisionUITests.QRCatcherVisionUITests testRealFilesImportAndReopen] : failed')
            self.diagnostic.observe('Test Case ordinary progress')
            self.assertFalse(self.diagnostic.attempted)
            line = 'error: -[QRCatcherVisionUITests.QRCatcherVisionUITests ' + self.case.name + '] : failed'
            self.diagnostic.observe(line); self.diagnostic.observe(line)
            self.diagnostic.capture('native failure teardown request')
        self.assertEqual(len(self.calls), 2)

    def test_missing_or_changed_current_lease_never_runs_command(self):
        for missing in [False, True]:
            self.nonce_file.write_text(json.dumps({**self.value, 'pid': 45678}))
            if missing: self.bound.bound = None
            self.diagnostic = failure.FailureDiagnostic(self.bound, self.out)
            row = self.capture()
            self.assertFalse(row['pixels_retained']); self.assertEqual(self.calls, [])
            self.assertFalse(row['success'])

    def test_existing_diagnostic_output_is_preserved_without_any_command(self):
        target = self.out / 'vision-host-failure.jpg'
        target.write_bytes(b'previous-owned-fixture')
        row = self.capture()
        self.assertFalse(row['pixels_retained']); self.assertEqual(self.calls, [])
        self.assertEqual(target.read_bytes(), b'previous-owned-fixture')

    def test_lease_change_during_screenshot_prevents_conversion_and_retention(self):
        def execute(args, seconds, **kwargs):
            result = self.execute(args, seconds, **kwargs)
            self.nonce_file.write_text(json.dumps({**self.value, 'pid': 45678}))
            return result
        row = self.capture(execute)
        self.assertFalse(row['pixels_retained']); self.assertEqual(len(self.calls), 1)
        self.assertEqual(list(self.out.glob('*.jpg')), [])

    def test_unconfirmed_cleanup_prevents_conversion(self):
        def execute(args, seconds, **kwargs):
            self.execute(args, seconds, **kwargs)
            return 126, '', {'cleanup_confirmed': False, 'exit': 126}
        row = self.capture(execute)
        self.assertFalse(row['pixels_retained']); self.assertEqual(len(self.calls), 1)

    def test_timeout_pixels_are_diagnostic_only_and_no_retry(self):
        def execute(args, seconds, **kwargs):
            result = self.execute(args, seconds, **kwargs)
            return (124, '', {'cleanup_confirmed': True, 'exit': 124}) if args[0] == 'xcrun' else result
        row = self.capture(execute)
        self.assertFalse(row['pixels_retained']); self.assertFalse(row['capture_success'])
        self.assertFalse(row['success']); self.assertEqual(len(self.calls), 1)
        self.capture(); self.assertEqual(len(self.calls), 1)

    def test_missing_or_oversized_pixels_fail_without_replacing_success_frame(self):
        for oversized in [False, True]:
            self.diagnostic = failure.FailureDiagnostic(self.bound, self.out)
            def execute(args, seconds, **kwargs):
                if oversized:
                    result = self.execute(args, seconds, **kwargs)
                    if args[0] == 'sips': Path(args[-1]).write_bytes(b'\xff\xd8' + b'x' * (160 * 1024))
                    return result
                self.calls.append((args, seconds))
                return 1, '', {'cleanup_confirmed': True, 'exit': 1}
            row = self.capture(execute)
            self.assertFalse(row['pixels_retained']); self.assertFalse(row['success'])
            self.assertEqual(list(self.out.glob('*.jpg')), [])


class VisionTeardownMarkerContracts(unittest.TestCase):
    def test_flushed_markers_and_cached_store_have_no_new_ax_query(self):
        source = (ROOT / 'QRCatcherVisionUITests/QRCatcherVisionUITests.swift').read_text()
        self.assertIn('private func tracePhase(_ message: String) { print(message); fflush(stdout) }', source)
        teardown = source.split('override func tearDown()', 1)[1].split('private func bindCaptureRunner()', 1)[0]
        self.assertLess(teardown.index('VISION_TEARDOWN_ENTRY_BEFORE_FAILURE_COUNT'), teardown.index('testRun?.failureCount'))
        self.assertLess(teardown.index('VISION_TEARDOWN_BEFORE_APP_TERMINATE'), teardown.index('app.terminate()'))
        capture = source.split('private func capture(', 1)[1].split('private func revealPolicyEnding()', 1)[0]
        self.assertNotIn('launchEnvironment', capture); self.assertNotIn('testRun', capture)
        self.assertIn('"test_store": captureStoreName', capture)
        self.assertIn('VISION_FAILURE_CAPTURE_BEFORE_REQUEST_WRITE', capture)
        self.assertIn('ContinuousClock.now.advanced(by: .seconds(100))', capture)

    def test_swift_binds_actual_method_and_exact_case_result_before_ui(self):
        source = (ROOT / 'QRCatcherVisionUITests/QRCatcherVisionUITests.swift').read_text()
        bind = source.split('private func bindCaptureRunner()', 1)[1].split('private func capture(', 1)[0]
        self.assertIn('name == "-[QRCatcherVisionUITests.QRCatcherVisionUITests \\(method)]"', bind)
        self.assertIn('"case": actualMethod', bind)
        self.assertIn('scopes[scope] == [actualMethod, resultName]', bind)
        for field in ['case', 'scope', 'result']:
            self.assertIn('XCTAssertEqual(result?["' + field + '"]', source)


class VisionInheritedCommandTests(unittest.TestCase):
    def test_normal_child_inherits_collector_group_and_defers_group_cleanup(self):
        with patch.object(failure, 'blocked', return_value=False), patch.object(failure, 'mark_unconfirmed') as barrier:
            code, text, row = failure.execute([sys.executable, '-c', 'import os;print(os.getpgrp())'], 2)
        self.assertEqual(code, 0); self.assertEqual(int(text.strip()), os.getpgrp())
        self.assertTrue(row['leader_reaped']); self.assertTrue(row['cleanup_deferred_to_collector'])
        self.assertNotIn('cleanup_confirmed', row); barrier.assert_not_called()

    def test_timeout_and_output_limit_reap_own_leader_and_set_barrier(self):
        for code, command, seconds, limit in [(124, 'import time;time.sleep(2)', .1, 4096),
                                               (125, 'print("x"*4096)', 2, 128)]:
            with self.subTest(code=code), patch.object(failure, 'blocked', return_value=False), patch.object(failure, 'mark_unconfirmed') as barrier:
                actual, text, row = failure.execute([sys.executable, '-c', command], seconds, output_limit=limit, tail_limit=64)
            self.assertEqual(actual, code); self.assertTrue(row['leader_reaped'])
            self.assertFalse(row['cleanup_confirmed']); self.assertLessEqual(len(text), 64)
            self.assertEqual(row['cleanup_owner'], 'collector_process_group')
            barrier.assert_called_once_with(row)

    def test_cleanup_barrier_forbids_new_child(self):
        with patch.object(failure, 'blocked', return_value=True), patch.object(failure.subprocess, 'Popen') as spawn:
            code, _, row = failure.execute([sys.executable, '-c', 'pass'], 2)
        self.assertEqual(code, 126); spawn.assert_not_called()

    def test_bounded_descriptor_read_checks_actual_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); path = root / 'owned'; path.write_bytes(b'1234')
            directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                self.assertEqual(failure.bounded_bytes(path, 4, directory)[0], b'1234')
                with self.assertRaises(ValueError): failure.bounded_bytes(path, 3, directory)
            finally: os.close(directory)


if __name__ == '__main__':
    unittest.main()
