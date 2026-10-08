"""Owned shell/bootstrap/FD regressions only; no simulator or outside paths."""
import importlib
import json
import os
import signal
import shlex
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import owned_process_barrier as barrier
from owned_process_group import stop_group
import vision_command_fence as fence
from watch_process import execute

FILES = ['run_vision_fenced_command.sh', 'run_vision_fenced_command.py', 'vision_command_fence.py',
         'owned_process_barrier.py', 'atomic_json.py', 'watch_process.py', 'owned_process_group.py', 'run_bounded.py',
         'fixture_query_guard.py', 'stage_owned_import_fixture.py', 'launch_optional_simulator.py',
         'run_vision_ui_cases.py', 'run_native_size_case.py', 'simulator_content_size.py', 'vision_case_contract.py']
DEVICE = '11111111-2222-4333-8444-555555555555'


class VisionFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); (self.root / 'build/vision-runtime').mkdir(parents=True)
        (self.root / 'scripts').mkdir(); (self.root / 'bin').mkdir()
        for name in FILES: shutil.copyfile(ROOT / 'scripts' / name, self.root / 'scripts' / name)
        self.env = {**os.environ, 'GITHUB_WORKSPACE': str(self.root), 'GITHUB_ENV': str(self.root / 'github-env'),
                    'GITHUB_REPOSITORY': '100mango/QRCatcher', 'GITHUB_SHA': 'a' * 40,
                    'PYTHONOPTIMIZE': str(sys.flags.optimize),
                    'VISION_SIMULATOR_ID': DEVICE, 'EVIDENCE_SCOPE': 'visionos_files',
                    'QRCATCHER_OWNED_PROCESS_BARRIER': str(self.root / 'build/owned-process-cleanup.json'),
                    'PATH': str(self.root / 'bin') + os.pathsep + os.environ['PATH']}
        self.env.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED', None)
        self.env.pop('PYTHONPATH', None)
        self.latch = self.root / 'build' / fence.NAME
        self.stub = self.root / 'bin/xcrun'
        self.stub.write_text('#!' + sys.executable + '\nimport json,sys\nfrom pathlib import Path\n'
                             'with Path("calls.jsonl").open("a") as output: output.write(json.dumps(sys.argv[1:])+"\\n")\n'
                             'raise SystemExit(0)\n')
        self.stub.chmod(0o755)
        for name in ['xcodebuild', 'open']:
            target = self.root / 'bin' / name; shutil.copyfile(self.stub, target); target.chmod(0o755)
        (self.root / 'scripts/capture_vision_checkpoints.py').write_text(
            'from pathlib import Path\nPath("capture-must-not-start").touch()\n')

    def shell(self, action='install'):
        return subprocess.run(['bash', '-c', '. scripts/run_vision_fenced_command.sh ' + action],
                              cwd=self.root, env=self.env, capture_output=True, text=True, timeout=10)

    def calls(self):
        path = self.root / 'calls.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def assert_later_blocked(self):
        before = len(self.calls()); result = self.shell('shutdown')
        self.assertEqual(result.returncode, 126, result.stdout + result.stderr)
        self.assertEqual(len(self.calls()), before)
        self.assertNotIn('VISION_FENCE_PYTHON_ENTRY', result.stdout)
        # Each entrypoint runs in a fresh process. Timeout cases never import
        # GITHUB_ENV: the durable latch alone must deny all device work.
        commands = [
            [sys.executable, 'scripts/run_bounded.py', '2', 'xcrun', 'simctl', 'shutdown', DEVICE],
            [sys.executable, 'scripts/run_bounded.py', '2', 'xcrun', 'simctl', 'get_app_container', DEVICE, '100mango.QRCatcher', 'app'],
            [sys.executable, 'scripts/run_bounded.py', '2', 'xcodebuild', 'test-without-building'],
            [sys.executable, 'scripts/stage_owned_import_fixture.py', DEVICE],
            [sys.executable, 'scripts/run_vision_ui_cases.py', DEVICE, 'visionos_files'],
            [sys.executable, 'scripts/launch_optional_simulator.py', DEVICE],
        ]
        for command in commands:
            with self.subTest(later=command):
                result = subprocess.run(command, cwd=self.root, env=self.env,
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 126, result.stdout + result.stderr)
                self.assertEqual(len(self.calls()), before)
                self.assertFalse((self.root / 'capture-must-not-start').exists())

    def assert_timeout_retained(self, result, command_exit=124, state='completed'):
        self.assertEqual(result.returncode, 126, result.stdout + result.stderr)
        self.assertTrue(self.latch.is_file()); self.assertEqual(len(self.calls()), 1)
        self.assertNotIn('VISION_FENCE_CLEARED_CONFIRMED', result.stdout)
        self.assertIn('VISION_FENCE_DEVICE_UNCERTAINTY_RETAINED', result.stdout)
        receipt = json.loads((self.root / 'build/vision-runtime/fenced-install.json').read_text())
        self.assertEqual(receipt['command_exit'], command_exit)
        self.assertEqual(receipt['operation']['exit'], command_exit)
        self.assertEqual(receipt['operation']['state'], state)
        self.assertTrue(receipt['cleanup_confirmed']); self.assertTrue(receipt['operation']['cleanup_confirmed'])
        self.assertFalse(receipt['device_command_completion_confirmed'])
        self.assertEqual(receipt['operation']['timeout_seconds'], 90)
        self.assertEqual(json.loads(self.latch.read_text())['state'], 'claimed')
        self.assert_later_blocked()
        return receipt

    def test_child_124_with_confirmed_host_cleanup_never_clears_device_uncertainty(self):
        self.stub.write_text(self.stub.read_text().replace('raise SystemExit(0)', 'raise SystemExit(124)'))
        self.assert_timeout_retained(self.shell())

    def test_output_limit_exit_is_not_device_completion(self):
        self.stub.write_text(self.stub.read_text().replace('raise SystemExit(0)', 'raise SystemExit(125)'))
        self.assert_timeout_retained(self.shell(), command_exit=125)

    def test_owned_timeout_with_confirmed_host_cleanup_never_clears_device_uncertainty(self):
        self.stub.write_text(self.stub.read_text().replace('raise SystemExit(0)',
                             'import time\nPath("timeout-child-started").touch()\ntime.sleep(10)'))
        source = self.root / 'scripts/watch_process.py'
        # Advance only this fixture's command clock after its real owned child
        # starts. Production still executes exactly one command at its 90 cap.
        source.write_text(source.read_text() + '\nimport types\nfrom pathlib import Path\n'
            '_real_time = time\ndef command_clock():\n'
            ' return _real_time.monotonic() + (91 if Path("timeout-child-started").exists() else 0)\n'
            'time = types.SimpleNamespace(monotonic=command_clock)\n')
        receipt = self.assert_timeout_retained(self.shell(), state='timed_out')
        self.assertGreater(receipt['operation']['elapsed_seconds'], 90)

    def test_late_completed_zero_beyond_original_cap_keeps_uncertainty(self):
        source = self.root / 'scripts/watch_process.py'
        source.write_text(source.read_text() + '\n_original_execute = execute\n'
            'def execute(*args, **kwargs):\n code, tail, operation = _original_execute(*args, **kwargs)\n'
            ' operation["elapsed_seconds"] = 93.20\n return code, tail, operation\n')
        self.assert_timeout_retained(self.shell(), command_exit=0)

    def test_workflow_marker_write_failure_does_not_erase_timeout_latch(self):
        self.stub.write_text(self.stub.read_text().replace('raise SystemExit(0)', 'raise SystemExit(124)'))
        (self.root / 'github-env').mkdir()
        result = self.shell()
        self.assertIn('VISION_FENCE_ENV_PROPAGATION_FAILED_LATCH_RETAINED', result.stdout)
        self.assert_timeout_retained(result)

    def test_claim_marker_write_failure_prevents_even_the_first_device_command(self):
        source = self.root / 'scripts/vision_command_fence.py'
        source.write_text(source.read_text() + '\ndef failed_write(*args):\n raise OSError("injected claim write failure")\nos.write = failed_write\n')
        result = self.shell()
        self.assertEqual(result.returncode, 126, result.stdout + result.stderr)
        self.assertTrue(self.latch.is_file()); self.assertEqual(self.calls(), [])
        self.assertNotIn('BOUNDED_COMMAND_START', result.stdout)
        self.assert_later_blocked()

    def test_receipt_write_failure_after_timeout_retains_original_failure_and_latch(self):
        self.stub.write_text(self.stub.read_text().replace('raise SystemExit(0)', 'raise SystemExit(124)'))
        # Only the offline receipt destination fails; dispatch and cleanup run.
        (self.root / 'build/vision-runtime').rmdir()
        (self.root / 'build/vision-runtime').write_text('injected unavailable receipt directory')
        result = self.shell()
        self.assertEqual(result.returncode, 126, result.stdout + result.stderr)
        operation = json.loads(result.stdout.split('BOUNDED_COMMAND_END ', 1)[1].splitlines()[0])
        self.assertEqual(operation['exit'], 124); self.assertTrue(operation['cleanup_confirmed'])
        self.assertTrue(self.latch.is_file()); self.assertEqual(len(self.calls()), 1)
        self.assertNotIn('VISION_FENCE_CLEARED_CONFIRMED', result.stdout)
        self.assert_later_blocked()

    def test_same_parent_controller_reload_cannot_reclaim_consumed_nonce(self):
        self.stub.write_text(self.stub.read_text().replace('raise SystemExit(0)', 'raise SystemExit(124)'))
        # Both controllers receive the exact nonce and original parent PID.
        # The second must reject the consumed descriptor even without GITHUB_ENV.
        producer = ('import json, os; from pathlib import Path; '
                    'p = Path("build/vision-command-inflight.json"); '
                    'p.write_text(json.dumps({"version": 1, "source": "a" * 40, '
                    '"device": "' + DEVICE + '", "scope": "visionos_files", '
                    '"action": "install", "owner_pid": os.getppid(), "nonce": "12-34-56"})); p.chmod(0o600)')
        command = (shlex.quote(sys.executable) + ' -c ' + shlex.quote(producer) + '; '
                   'python3 -u scripts/run_vision_fenced_command.py install 12-34-56; '
                   'printf "FIRST_EXIT=%s\\n" "$?"; '
                   'python3 -u scripts/run_vision_fenced_command.py install 12-34-56; '
                   'status=$?; exit "$status"')
        result = subprocess.run(['bash', '-c', command], cwd=self.root, env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 126, result.stdout + result.stderr)
        self.assertIn('FIRST_EXIT=126', result.stdout)
        self.assertEqual(result.stdout.count('VISION_FENCE_CHILD_STARTED'), 1)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn('VISION_FENCE_CONTROLLER_UNCONFIRMED ValueError', result.stdout)
        self.assert_later_blocked()

    def test_confirmed_install_and_distinct_shutdown_clear_only_their_own_latch(self):
        for action, seconds in [('install', 90), ('shutdown', 45)]:
            result = self.shell(action)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(self.latch.exists())
            receipt = json.loads((self.root / 'build/vision-runtime' / ('fenced-' + action + '.json')).read_text())
            self.assertTrue(receipt['cleanup_confirmed']); self.assertEqual(receipt['operation']['timeout_seconds'], seconds)
            self.assertEqual(receipt['operation']['command'][:4], ['xcrun', 'simctl', action, DEVICE])
            for name in ['SHELL_ENTRY', 'BEFORE_PYTHON', 'PYTHON_ENTRY', 'IMPORTS_READY', 'CHILD_STARTED', 'CLEARED_CONFIRMED', 'AFTER_PYTHON']:
                self.assertIn('VISION_FENCE_' + name, result.stdout)
        self.assertEqual(len(self.calls()), 2)
        result = self.shell('install'); self.assertEqual(result.returncode, 126)
        self.assertEqual(len(self.calls()), 2)

    def test_completed_nonzero_command_remains_failed_but_has_confirmed_cleanup(self):
        self.stub.write_text(self.stub.read_text().replace('raise SystemExit(0)', 'raise SystemExit(7)'))
        result = self.shell()
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertFalse(self.latch.exists()); self.assertEqual(len(self.calls()), 1)
        receipt = json.loads((self.root / 'build/vision-runtime/fenced-install.json').read_text())
        self.assertEqual(receipt['command_exit'], 7); self.assertTrue(receipt['cleanup_confirmed'])

    def test_pre_python_failure_leaves_durable_latch_and_no_later_command(self):
        python = self.root / 'bin/python3'; python.write_text('#!/bin/sh\nexit 73\n'); python.chmod(0o755)
        result = self.shell()
        self.assertEqual(result.returncode, 126); self.assertTrue(self.latch.exists())
        self.assertEqual(self.calls(), []); self.assertNotIn('VISION_FENCE_PYTHON_ENTRY', result.stdout)
        self.assert_later_blocked()

    def test_outer_stop_during_bootstrap_preserves_the_latch(self):
        python = self.root / 'bin/python3'
        python.write_text('#!/bin/sh\nprintf "BOOTSTRAP_ENTERED\\n"\nsleep 10\n'); python.chmod(0o755)
        output = self.root / 'bootstrap.log'
        with output.open('w') as stream:
            process = subprocess.Popen(['bash', '-c', '. scripts/run_vision_fenced_command.sh install'],
                                       cwd=self.root, env=self.env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and 'BOOTSTRAP_ENTERED' not in output.read_text(): time.sleep(.02)
                self.assertIn('BOOTSTRAP_ENTERED', output.read_text())
                self.assertTrue(self.latch.exists())
            finally:
                stop_group(process); process.wait(timeout=3)
        self.assertEqual(self.calls(), []); self.assert_later_blocked()

    def test_unknown_group_cleanup_never_clears_or_allows_shutdown(self):
        source = self.root / 'scripts/watch_process.py'
        source.write_text(source.read_text() + '\nstop_group = lambda process: False\n')
        result = self.shell()
        self.assertEqual(result.returncode, 126, result.stdout + result.stderr)
        self.assertTrue(self.latch.exists()); self.assertEqual(len(self.calls()), 1)
        self.assertTrue((self.root / 'build/owned-process-cleanup.json').exists())
        self.assert_later_blocked()

    def test_outer_stop_after_owned_child_spawn_keeps_uncertainty(self):
        self.stub.write_text('#!' + sys.executable + '\nimport os,time\nfrom pathlib import Path\n'
                             'Path("owned-child.pid").write_text(str(os.getpid()))\ntime.sleep(10)\n')
        output = self.root / 'child-stop.log'; child_pid = None
        with output.open('w') as stream:
            process = subprocess.Popen(['bash', '-c', '. scripts/run_vision_fenced_command.sh install'],
                                       cwd=self.root, env=self.env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                deadline = time.monotonic() + 3; pid_file = self.root / 'owned-child.pid'
                while time.monotonic() < deadline and not pid_file.exists(): time.sleep(.02)
                self.assertTrue(pid_file.exists()); child_pid = int(pid_file.read_text())
                stop_group(process); process.wait(timeout=3)
                self.assertTrue(self.latch.exists()); self.assert_later_blocked()
            finally:
                stop_group(process)
                # This is the exact still-sleeping process created by our own
                # fixture, in its deliberately separate owned session.
                if child_pid:
                    try: os.killpg(child_pid, signal.SIGKILL)
                    except ProcessLookupError: pass

    def test_existing_partial_or_complete_unknown_latch_is_never_overwritten(self):
        for data in [b'', b'{"unknown":true}']:
            self.latch.write_bytes(data); result = self.shell()
            self.assertEqual(result.returncode, 126); self.assertEqual(self.latch.read_bytes(), data)
            self.assertEqual(self.calls(), []); self.latch.unlink()

    def descriptor(self):
        value = {'version': 1, 'source': 'a' * 40, 'device': DEVICE, 'scope': 'visionos_files',
                 'action': 'install', 'owner_pid': os.getppid(), 'nonce': '12-34-56'}
        self.latch.write_text(json.dumps(value)); self.latch.chmod(0o600)
        return value

    def test_only_exact_command_is_admitted_and_changed_identity_stays_blocked(self):
        self.descriptor(); previous = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, self.env, clear=True):
                claim = fence.VisionCommandFence('install', '12-34-56')
                try:
                    claim.activate()
                    self.assertFalse(barrier.blocked(claim.command()))
                    self.assertTrue(barrier.blocked()); self.assertTrue(barrier.blocked(['xcrun', 'simctl', 'shutdown', DEVICE]))
                    self.latch.write_text('{}')
                    self.assertTrue(barrier.blocked(claim.command()))
                    with self.assertRaises(ValueError): claim.clear_confirmed({'cleanup_confirmed': True})
                    self.assertTrue(self.latch.exists())
                finally: claim.close()
        finally: os.chdir(previous)

    def test_timeout_is_sticky_before_propagation_and_after_module_reload(self):
        self.descriptor(); previous = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, self.env, clear=True):
                claim = fence.VisionCommandFence('install', '12-34-56')
                try:
                    claim.activate()
                    operation = {'command': claim.command(), 'timeout_seconds': 90,
                                 'state': 'timed_out', 'exit': 124, 'elapsed_seconds': 93.2,
                                 'cleanup_confirmed': True}
                    self.assertFalse(claim.observe(operation, 124))
                    self.assertTrue(barrier.blocked(claim.command()))
                    late = {**operation, 'state': 'completed', 'exit': 0, 'elapsed_seconds': 1}
                    self.assertFalse(claim.observe(late, 0))
                    with self.assertRaises(ValueError): claim.clear_confirmed(late)
                    self.assertTrue(self.latch.is_file())
                    # Module reload loses every Python singleton. Existing
                    # claimed bytes still forbid reloading the original grant.
                    importlib.reload(fence); importlib.reload(barrier)
                    self.assertTrue(barrier.blocked(claim.command()))
                    with self.assertRaises(ValueError): fence.VisionCommandFence('install', '12-34-56')
                    code, _, result = execute(claim.command(), 90)
                    self.assertEqual(code, 126); self.assertFalse(result['cleanup_confirmed'])
                    self.assertEqual(self.calls(), [])
                finally: claim.close()
        finally: os.chdir(previous)
        self.assert_later_blocked()

    def test_partial_claim_write_and_fsync_failure_fail_closed_before_spawn(self):
        original = (ROOT / 'scripts/vision_command_fence.py').read_text()
        injections = [
            '\n_real_write = os.write\ndef partial_write(fd, data):\n'
            ' _real_write(fd, data[:8]); raise OSError("injected partial claim write")\nos.write = partial_write\n',
            '\ndef failed_sync(fd):\n raise OSError("injected claim fsync failure")\nos.fsync = failed_sync\n',
        ]
        for injection in injections:
            with self.subTest(injection=injection):
                (self.root / 'scripts/vision_command_fence.py').write_text(original + injection)
                result = self.shell()
                self.assertEqual(result.returncode, 126, result.stdout + result.stderr)
                self.assertTrue(self.latch.is_file()); self.assertEqual(self.calls(), [])
                self.assertNotIn('BOUNDED_COMMAND_START', result.stdout)
                self.assert_later_blocked()
                self.latch.unlink()  # Isolate the next synthetic fault case.

    def test_wrong_nonce_parent_source_or_mode_is_not_claimed(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, self.env, clear=True):
                for key, value in [('source', 'b' * 40), ('owner_pid', 0), ('nonce', '99-88-77')]:
                    data = self.descriptor(); data[key] = value; self.latch.write_text(json.dumps(data))
                    with self.subTest(key=key), self.assertRaises(ValueError): fence.VisionCommandFence('install', '12-34-56')
                self.descriptor(); self.latch.chmod(0o644)
                with self.assertRaises(ValueError): fence.VisionCommandFence('install', '12-34-56')
        finally: os.chdir(previous)

    def lost_active_identity(self, replace_parent):
        self.descriptor(); previous = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, self.env, clear=True):
                claim = fence.VisionCommandFence('install', '12-34-56')
                try:
                    claim.activate()
                    if replace_parent:
                        (self.root/'build').rename(self.root/'old-build'); (self.root/'build').mkdir()
                    else: self.latch.unlink()
                    with self.assertRaises((OSError, ValueError)): claim.current()
                    self.assertTrue(barrier.blocked()); self.assertTrue(barrier.blocked(claim.command()))
                    code, _, operation = execute(claim.command(), 2)
                    self.assertEqual(code, 126); self.assertFalse(operation['cleanup_confirmed'])
                    self.assertEqual(self.calls(), [])
                finally: claim.close()
        finally: os.chdir(previous)

    def test_missing_active_latch_never_spawns_a_command(self):
        self.lost_active_identity(False)

    def test_replaced_empty_active_parent_never_spawns_a_command(self):
        self.lost_active_identity(True)

    def controller_identity_loss(self, mode):
        source = self.root/'scripts/vision_command_fence.py'
        if mode=='constructor':
            injected = '\n_original_init = VisionCommandFence.__init__\ndef lose(self, action, nonce):\n Path("build/vision-command-inflight.json").unlink()\n _original_init(self, action, nonce)\nVisionCommandFence.__init__ = lose\n'
        else:
            change = ('(self.parent / NAME).unlink()' if mode=='latch' else 'self.parent.rename(self.parent.with_name("old-build")); self.parent.mkdir()')
            injected = '\n_original_activate = VisionCommandFence.activate\ndef lose(self):\n _original_activate(self)\n '+change+'\nVisionCommandFence.activate = lose\n'
        source.write_text(source.read_text()+injected)
        env_file=self.root/'github-env'; env_file.write_text('OWNED_SENTINEL=preserved\n')
        result=self.shell()
        self.assertEqual(result.returncode,126,result.stdout+result.stderr)
        self.assertIn('VISION_FENCE_CONTROLLER_UNCONFIRMED',result.stdout)
        self.assertFalse(self.latch.exists()); self.assertEqual(self.calls(),[])
        self.assertEqual(env_file.read_text(),'OWNED_SENTINEL=preserved\nQRCATCHER_OWNED_CLEANUP_UNCONFIRMED=true\n')
        # GitHub propagates this exact flag to the next independent step. Check
        # a fresh interpreter and fresh shell, not the now-exited controller.
        self.env['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED']='true'
        self.assert_later_blocked()

    def test_constructor_identity_failure_persists_workflow_uncertainty(self):
        self.controller_identity_loss('constructor')

    def test_controller_latch_disappearance_blocks_a_fresh_later_step(self):
        self.controller_identity_loss('latch')

    def test_controller_empty_parent_replacement_blocks_a_fresh_later_step(self):
        self.controller_identity_loss('parent')

    def test_owned_link_or_replaced_parent_is_not_admitted(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, self.env, clear=True):
                self.descriptor(); owned = self.root / 'owned-marker'; self.latch.rename(owned)
                self.latch.symlink_to(owned)
                with self.assertRaises((OSError, ValueError)): fence.VisionCommandFence('install', '12-34-56')
                self.latch.unlink(); self.latch.hardlink_to(owned)
                with self.assertRaises(ValueError): fence.VisionCommandFence('install', '12-34-56')
                self.latch.unlink(); owned.unlink(); self.descriptor()
                claim = fence.VisionCommandFence('install', '12-34-56')
                try:
                    (self.root / 'build').rename(self.root / 'old-build'); (self.root / 'build').mkdir()
                    with self.assertRaises(ValueError): claim.current()
                finally: claim.close()
        finally: os.chdir(previous)

    def test_workflow_sources_shell_without_duplicate_python_precheck_or_new_limits(self):
        source = (ROOT / '.github/workflows/apple-platforms.yml').read_text()
        for title, action, minutes in [('Install the exact built Vision app before any fixtures', 'install', 2),
                                       ('Stop the Vision simulator before other platform tests', 'shutdown', 1)]:
            step = source.split('- name: ' + title, 1)[1].split('    - name:', 1)[0]
            self.assertIn('. scripts/run_vision_fenced_command.sh ' + action, step)
            self.assertIn('timeout-minutes: ' + str(minutes), step)
            self.assertNotIn('python3 scripts/owned_process_barrier.py --check', step)
        controller = (ROOT / 'scripts/run_vision_fenced_command.py').read_text()
        self.assertLess(controller.index("print('VISION_FENCE_PYTHON_ENTRY'"), controller.index('import json'))
        self.assertIn("seconds = 90 if action == 'install' else 45", controller)
        self.assertEqual(controller.count('execute(command,'), 1)


if __name__ == '__main__': unittest.main()
