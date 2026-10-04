"""Real temporary-file lease/identity contracts with public command doubles."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import vision_runner_binding as lease


class VisionRunnerBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'Devices'
        self.device = str(uuid.uuid4()).upper(); self.source = 'a' * 40
        parent = self.root / self.device / 'data/Containers/Data/Application'
        self.container = parent / str(uuid.uuid4()).upper()
        self.app = parent / str(uuid.uuid4()).upper()
        (self.container / 'tmp').mkdir(parents=True); self.app.mkdir()
        self.lookup = Mock(side_effect=lambda bundle: str(self.container if bundle == lease.RUNNER else self.app))
        self.barrier = patch.object(lease, 'blocked', return_value=False)
        self.barrier.start(); self.addCleanup(self.barrier.stop)
        self.binding = lease.RunnerBinding(self.device, lease.RUNNER, self.source, self.root, self.lookup)
        self.identifier = str(uuid.uuid4()).upper()
        self.request_id = str(uuid.uuid4()).upper()
        self.descriptor = {'id': self.identifier, 'runner': lease.RUNNER, 'pid': 12345, 'exports': False}
        self.lease_file = self.container / 'tmp' / ('QRCatcher-runner-' + self.identifier + '.json')
        self.lease_file.write_text(json.dumps(self.descriptor))

    def prime(self, exports=False):
        self.descriptor['exports'] = exports
        self.lease_file.write_text(json.dumps(self.descriptor))
        return self.binding.prime(self.identifier)

    def request(self, **overrides):
        data = {'id': self.request_id, 'runner': lease.RUNNER, 'lease': self.identifier,
                'pid': 12345, 'source_commit': self.source, 'device': self.device,
                'name': 'vision-chinese-empty', 'test_store': str(uuid.uuid4()).upper()}
        data.update(overrides)
        path = self.container / 'tmp' / ('QRCatcher-capture-' + self.request_id + '.json')
        path.write_text(json.dumps(data))
        return path

    def test_pre_ui_bind_then_repeated_capture_has_no_late_lookup(self):
        result = self.prime(); self.request()
        self.assertEqual(json.loads(self.lease_file.with_suffix('.ack').read_text()), result)
        self.assertEqual(result['source_commit'], self.source)
        self.assertEqual(result['device'], self.device)
        for _ in range(3):
            descriptor, acknowledgement = self.binding.request(self.request_id, {'vision-chinese-empty'})
            self.binding.acknowledge(self.request_id, {'vision-chinese-empty'}, {'id': self.request_id, 'success': False})
            self.assertEqual(json.loads(acknowledgement.read_text())['success'], False)
        self.lookup.assert_called_once_with(lease.RUNNER)

    def test_export_case_binds_own_app_before_ui_and_never_rediscovers(self):
        self.prime(exports=True); self.request(name='vision-exported-qr')
        self.binding.request(self.request_id, {'vision-exported-qr'})
        self.assertEqual(self.binding.app_container(), self.app)
        self.assertEqual([c.args for c in self.lookup.call_args_list], [(lease.RUNNER,), (lease.APP,)])

    def test_capture_only_binding_cannot_read_export_container(self):
        self.prime(); self.request(name='vision-exported-qr')
        with self.assertRaises(ValueError): self.binding.request(self.request_id, {'vision-exported-qr'})
        with self.assertRaises(ValueError): self.binding.app_container()
        self.lookup.assert_called_once()

    def test_wrong_source_runner_or_noncanonical_uuid_rejected(self):
        for runner, source, device in [('unrelated.runner', self.source, self.device),
                                      (lease.RUNNER, 'not-a-commit', self.device),
                                      (lease.RUNNER, self.source, self.device.lower())]:
            with self.assertRaises(ValueError): lease.RunnerBinding(device, runner, source, self.root, self.lookup)
        self.lookup.assert_not_called()

    def test_wrong_device_root_rejects_container(self):
        other = str(uuid.uuid4()).upper()
        (self.root / other / 'data/Containers/Data/Application').mkdir(parents=True)
        binding = lease.RunnerBinding(other, lease.RUNNER, self.source, self.root, self.lookup)
        with self.assertRaises(ValueError): binding.prime(self.identifier)
        self.assertIsNone(binding.bound)
        self.assertFalse(self.lease_file.with_suffix('.ack').exists())

    def test_symlink_container_and_tmp_are_rejected(self):
        alias = self.container.with_name(str(uuid.uuid4()).upper()); alias.symlink_to(self.container, target_is_directory=True)
        self.lookup.return_value = str(alias); self.lookup.side_effect = None
        with self.assertRaises(ValueError): self.binding.prime(self.identifier)
        self.lookup.side_effect = lambda _: str(self.container)
        temporary = self.container / 'tmp'; temporary.rename(self.container / 'real-tmp'); temporary.symlink_to(self.container / 'real-tmp', target_is_directory=True)
        with self.assertRaises(ValueError): self.binding.prime(self.identifier)

    def test_nonce_runner_pid_and_scope_must_match_schema(self):
        for key, bad in [('id', str(uuid.uuid4()).upper()), ('runner', 'wrong.runner'), ('pid', 0), ('pid', True), ('exports', 1)]:
            data = {**self.descriptor, key: bad}; self.lease_file.write_text(json.dumps(data))
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError): self.binding.prime(self.identifier)
            self.assertIsNone(self.binding.bound)

    def test_request_file_links_and_oversized_data_are_rejected(self):
        self.prime(); path = self.request()
        path.unlink(); path.symlink_to(self.lease_file)
        with self.assertRaises(ValueError): self.binding.request(self.request_id, {'vision-chinese-empty'})
        path.unlink(); path.hardlink_to(self.lease_file)
        with self.assertRaises(ValueError): self.binding.request(self.request_id, {'vision-chinese-empty'})
        path.unlink(); path.write_text('x' * 1025)
        with self.assertRaises(ValueError): self.binding.request(self.request_id, {'vision-chinese-empty'})

    def test_changed_missing_or_replaced_lease_has_no_late_discovery_or_ack(self):
        self.prime(); path = self.request()
        self.lease_file.write_text(json.dumps({**self.descriptor, 'pid': 23456}))
        with self.assertRaises(ValueError): self.binding.request(self.request_id, {'vision-chinese-empty'})
        self.lease_file.unlink()
        with self.assertRaises(ValueError): self.binding.acknowledge(self.request_id, {'vision-chinese-empty'}, {'success': False})
        self.assertFalse(path.with_suffix('.ack').exists()); self.lookup.assert_called_once()

    def test_replaced_container_or_tmp_inode_is_rejected(self):
        for temporary_only in [False, True]:
            self.prime()
            target = self.container / 'tmp' if temporary_only else self.container
            old = target.with_name(target.name + '-old'); target.rename(old); target.mkdir()
            if not temporary_only: (target / 'tmp').mkdir()
            self.lease_file.write_text(json.dumps(self.descriptor))
            with self.assertRaisesRegex(ValueError, 'identity changed'): self.binding.current()
            # Restore only this owned fixture for the second branch.
            self.lease_file.unlink()
            if not temporary_only: (target / 'tmp').rmdir()
            target.rmdir(); old.rename(target)

    def test_capture_identity_mismatch_never_acknowledges(self):
        self.prime()
        for key, bad in [('source_commit', 'b' * 40), ('device', str(uuid.uuid4()).upper()),
                         ('runner', 'wrong.runner'), ('lease', str(uuid.uuid4()).upper()), ('pid', 12346), ('name', 'not-a-checkpoint')]:
            path = self.request(**{key: bad})
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.binding.acknowledge(self.request_id, {'vision-chinese-empty'}, {'success': True})
            self.assertFalse(path.with_suffix('.ack').exists())
        self.lookup.assert_called_once()

    def test_app_inode_replacement_rejects_export_readback(self):
        self.prime(exports=True); self.app.rename(self.app.with_name(self.app.name + '-old')); self.app.mkdir()
        with self.assertRaisesRegex(ValueError, 'app container identity changed'): self.binding.app_container()
        self.assertEqual(self.lookup.call_count, 2)

    def test_failed_new_bind_discards_previous_cache(self):
        self.prime(); self.lookup.side_effect = TimeoutError('bounded lookup timeout')
        with self.assertRaises(TimeoutError): self.binding.prime(str(uuid.uuid4()).upper())
        with self.assertRaisesRegex(ValueError, 'No verified'): self.binding.current()

    def test_cleanup_barrier_forbids_new_lookup(self):
        with patch.object(lease, 'blocked', return_value=True), self.assertRaises(RuntimeError): self.binding.prime(self.identifier)
        self.lookup.assert_not_called(); self.assertIsNone(self.binding.bound)

    def test_ack_symlink_cannot_publish_binding_or_overwrite_target(self):
        target = Path(self.temp.name) / 'sentinel'; target.write_text('unchanged')
        self.lease_file.with_suffix('.ack').symlink_to(target)
        with self.assertRaises(ValueError): self.binding.prime(self.identifier)
        self.assertIsNone(self.binding.bound); self.assertEqual(target.read_text(), 'unchanged')

    def test_default_lookup_uses_same_twenty_second_owned_process_bound(self):
        binding = lease.RunnerBinding(self.device, lease.RUNNER, self.source, self.root)
        with patch.object(lease, 'execute', return_value=(0, str(self.container), {'cleanup_confirmed': True})) as call:
            binding.prime(self.identifier)
        self.assertEqual(call.call_args.args, (['xcrun', 'simctl', 'get_app_container', self.device, lease.RUNNER, 'data'], 20))
        for code, operation in [(124, {'cleanup_confirmed': True}), (0, {'cleanup_confirmed': False}), (0, {})]:
            with patch.object(lease, 'execute', return_value=(code, str(self.container), operation)), self.assertRaises(RuntimeError):
                binding.prime(self.identifier)
            self.assertIsNone(binding.bound)


class VisionBindingSourceContracts(unittest.TestCase):
    def test_binding_precedes_app_launch_and_failed_setup_cannot_use_app(self):
        source = (ROOT / 'QRCatcherVisionUITests/QRCatcherVisionUITests.swift').read_text()
        setup = source.split('override func setUp() async throws {', 1)[1].split('override func tearDown()', 1)[0]
        self.assertLess(setup.index('app = nil'), setup.index('try await bindCaptureRunner()'))
        self.assertLess(setup.index('try await bindCaptureRunner()'), setup.index('app = XCUIApplication()'))
        self.assertLess(setup.index('try await bindCaptureRunner()'), setup.index('app.launch()'))
        teardown = source.split('override func tearDown()', 1)[1].split('private func bindCaptureRunner()', 1)[0]
        self.assertIn('if let app {', teardown)
        self.assertIn('captureLease != nil', teardown)
        self.assertIn('captureLease = nil; captureSource = nil; captureDevice = nil', teardown)

    def test_new_setup_bounds_cover_only_exact_export_scope_and_leave_capture_bound(self):
        source = (ROOT / 'QRCatcherVisionUITests/QRCatcherVisionUITests.swift').read_text()
        binding = source.split('private func bindCaptureRunner()', 1)[1].split('private func capture(', 1)[0]
        self.assertIn('name.contains("testRealPhotosImportCopyAndReopen")', binding)
        self.assertIn('let seconds = exports ? 60 : 30', binding)
        self.assertIn('try await Task.sleep', binding)
        self.assertNotIn('Thread.sleep', binding)
        self.assertIn('if !accepted { try? FileManager.default.removeItem(at: request) }', binding)
        self.assertIn('ContinuousClock.now.advanced(by: .seconds(100))', source)
        for field in ['lease', 'source_commit', 'device', 'pid', 'runner']:
            self.assertIn('"' + field + '"', source)

    def test_event_collector_preserves_order_and_never_discovers_late(self):
        source = (ROOT / 'scripts/capture_vision_checkpoints.py').read_text()
        self.assertIn('(RUNNER_READY|CAPTURE_REQUEST)', source)
        self.assertIn('if (event,request_id) in seen:continue', source)
        self.assertIn('binding.prime(request_id)', source)
        self.assertIn('binding.request(request_id,names)', source)
        self.assertIn('binding.export_bytes(test_store,kind)', source)
        self.assertIn('binding.acknowledge(request_id,names,row)', source)
        self.assertNotIn("'get_app_container'", source)
        self.assertNotIn('subprocess.check_output', source)
        self.assertIn("any(not row['success'] for row in bindings)", source)
        self.assertIn("any(not row['success'] for row in report)", source)
        self.assertIn("if len(seen)>=64:raise SystemExit", source)

    def test_cleanup_is_rechecked_before_each_capture_command(self):
        source = (ROOT / 'scripts/capture_vision_checkpoints.py').read_text()
        for command in ["result=subprocess.run(['xcrun','simctl','io'", "subprocess.run(['sips'", "subprocess.run(['xcrun','swift'"]:
            prior = source.split(command, 1)[0].rstrip().splitlines()[-1]
            self.assertIn('if blocked():raise RuntimeError', prior)


if __name__ == '__main__':
    unittest.main()
