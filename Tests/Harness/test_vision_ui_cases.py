"""Command-routing tests only; these do not execute an Apple app or simulator."""
import contextlib, io, json, os, runpy, subprocess, sys, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

class Capture:
    def __init__(self, mode):
        self.mode = mode
        self.waits = []
        self.terminated = False
        self.killed = False
    def wait(self, timeout):
        self.waits.append(timeout)
        if self.mode == 'timeout' and not self.terminated:
            raise subprocess.TimeoutExpired('owned capture helper', timeout)
        return 1 if self.mode == 'failure' else 0
    def terminate(self): self.terminated = True
    def kill(self): self.killed = True

class VisionRoutingTests(unittest.TestCase):
    def setUp(self):
        isolation=patch.dict(os.environ);isolation.start();self.addCleanup(isolation.stop)
        for key in ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED','QRCATCHER_OWNED_PROCESS_BARRIER','GITHUB_ENV','GITHUB_WORKSPACE']:os.environ.pop(key,None)
    def exercise(self, failed_case=None, capture_mode='success',unknown_at=None,missing=False):
        calls = []
        def execute(command, seconds):
            calls.append((command, seconds))
            selector = next((v for v in command if v.startswith('-only-testing:')), None)
            code = 124 if selector and failed_case and failed_case in selector else 0
            detail={'exit':code,'timeout_seconds':seconds,'cleanup_confirmed':True}
            if unknown_at==len(calls):
                code=126;detail.update(exit=126,state='cleanup_unconfirmed',cleanup_confirmed=False)
                if missing:detail.pop('cleanup_confirmed')
            return code, 'bounded diagnostic tail', detail
        worker = types.ModuleType('watch_process')
        worker.execute = execute
        capture = Capture(capture_mode)
        with tempfile.TemporaryDirectory() as directory:
            old = Path.cwd()
            try:
                os.chdir(directory)
                with patch.dict(sys.modules, {'watch_process': worker}), \
                     patch.dict(os.environ, {'GITHUB_SHA': 'a' * 40}), \
                     patch.object(sys, 'argv', ['run_vision_ui_cases.py', '11111111-1111-4111-8111-111111111111']), \
                     patch('subprocess.Popen', return_value=capture) as launch, \
                     patch('owned_process_group.stop_group',return_value=True) as group_cleanup, \
                     patch('run_native_size_case.run_case',return_value=(0,{'status':'largest_ui_passed'})) as largest, \
                     contextlib.redirect_stdout(io.StringIO()):
                    if failed_case or capture_mode != 'success' or unknown_at:
                        with self.assertRaises(SystemExit):
                            runpy.run_path(str(ROOT / 'scripts/run_vision_ui_cases.py'), run_name='__main__')
                    else:
                        runpy.run_path(str(ROOT / 'scripts/run_vision_ui_cases.py'), run_name='__main__')
                report = json.loads(Path('build/vision-runtime/ui-cases.json').read_text())
                self.assertTrue(Path('build/vision-runtime/ui-completed.marker').exists())
                self.assertEqual(launch.call_count, 1)
                self.assertEqual(launch.call_args.args[0][:3], ['python3', '-u', 'scripts/capture_vision_checkpoints.py'])
                group_cleanup.assert_called_once_with(capture)
                if unknown_at:largest.assert_not_called()
                else:largest.assert_called_once_with('vision','11111111-1111-4111-8111-111111111111')
            finally:
                os.chdir(old)
        if unknown_at:
            self.assertEqual(len(calls),unknown_at);self.assertTrue(report['cleanup_unconfirmed'])
            return report,capture
        self.assertEqual(len(calls), 6)
        self.assertEqual([row['state'] for row in report['cases']], ['finished'] * 3)
        self.assertEqual([row['operation']['timeout_seconds'] for row in report['cases']], [600, 300, 300])
        self.assertEqual(len({row['case'] for row in report['cases']}), 3)
        for index in range(0, 6, 2):
            self.assertEqual(calls[index][0], ['xcrun', 'simctl', 'terminate', '11111111-1111-4111-8111-111111111111', '100mango.QRCatcher'])
            self.assertEqual(calls[index][1], 30)
            self.assertEqual(calls[index + 1][0][0], 'xcodebuild')
        return report, capture

    def test_three_distinct_cases_execute_once_in_order(self):
        report, _ = self.exercise()
        self.assertEqual([r['exit'] for r in report['cases']], [0, 0, 0])
    def test_first_case_timeout_preserves_failure_and_runs_distinct_cases(self):
        report, _ = self.exercise(failed_case='testRealPhotosImportCopyAndReopen')
        self.assertEqual([r['exit'] for r in report['cases']], [124, 0, 0])
    def test_capture_failure_keeps_functional_cases_and_fails_gate(self):
        report, _ = self.exercise(capture_mode='failure')
        self.assertEqual(report['capture_process_exit'], 1)
    def test_capture_timeout_terminates_only_owned_helper_and_marks_failure(self):
        report, capture = self.exercise(capture_mode='timeout')
        self.assertEqual(report['capture_process_exit'], 124)
        self.assertTrue(report['capture_cleanup_confirmed']);self.assertEqual(capture.waits,[30])
    def test_unresolved_termination_or_xctest_blocks_every_later_case(self):
        for position in [1,2]:
            for missing in [True,False]:
                os.environ.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED',None)
                with self.subTest(position=position,missing=missing):self.exercise(unknown_at=position,missing=missing)

if __name__ == '__main__': unittest.main()
