"""Owned shell/bootstrap/FD regressions only; no simulator or outside paths."""
import json
import os
import signal
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
         'owned_process_barrier.py', 'atomic_json.py', 'watch_process.py', 'owned_process_group.py', 'run_bounded.py']
DEVICE = '11111111-2222-4333-8444-555555555555'


class VisionFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); (self.root / 'build/vision-runtime').mkdir(parents=True)
        (self.root / 'scripts').mkdir(); (self.root / 'bin').mkdir()
        for name in FILES: shutil.copyfile(ROOT / 'scripts' / name, self.root / 'scripts' / name)
        self.env = {**os.environ, 'GITHUB_WORKSPACE': str(self.root), 'GITHUB_ENV': str(self.root / 'github-env'),
                    'GITHUB_REPOSITORY': '100mango/QRCatcher', 'GITHUB_SHA': 'a' * 40,
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
        result = subprocess.run([sys.executable, 'scripts/run_bounded.py', '2', 'xcrun', 'simctl', 'shutdown', DEVICE],
                                cwd=self.root, env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 126, result.stdout + result.stderr)
        self.assertEqual(len(self.calls()), before)

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
