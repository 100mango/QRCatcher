"""Bounded failure-preserving import scheduling; command doubles, not app proof."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import ios_import_continuation as gate

DEVICE = '11111111-2222-4333-8444-555555555555'
SOURCE = 'a' * 40


def summary(now):
    return {'result': 'Failed', 'totalTestCount': 9, 'passedTests': 8, 'failedTests': 1,
            'skippedTests': 0, 'expectedFailures': 0, 'startTime': now - 500, 'finishTime': now - 1,
            'testFailures': [{'targetName': 'QRCatcherUITests', 'testIdentifierString': 'QRCatcherUITests/testProductionCameraAllowThenResetAndDeny',
                              'failureText': gate.CAMERA_TIMEOUT}],
            'devicesAndConfigurations': [{'device': {'deviceId': DEVICE, 'platform': 'iOS Simulator'}}]}


def operation():
    return {'command': gate.expected_command(DEVICE), 'timeout_seconds': 570, 'state': 'completed',
            'exit': 65, 'cleanup_confirmed': True, 'elapsed_seconds': 511.68}


class ContinuationGateTests(unittest.TestCase):
    def test_complete_camera_failure_is_eligible_without_clearing_it(self):
        gate.validate_finalization(operation(), summary(10000), DEVICE, 10000)
        self.assertEqual(operation()['exit'], 65)

    def test_timeout_unknown_cleanup_wrong_command_and_duration_fail_closed(self):
        for mutation in [{'state': 'timed_out'}, {'exit': 124}, {'exit': 126}, {'cleanup_confirmed': False},
                         {'cleanup_confirmed': None}, {'elapsed_seconds': 900}, {'timeout_seconds': 600},
                         {'command': ['xcodebuild', 'other']}, {'elapsed_seconds': None}]:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                gate.validate_finalization({**operation(), **mutation}, summary(10000), DEVICE, 10000)

    def test_partial_stale_wrong_device_or_different_failure_summary_is_ineligible(self):
        mutations = [{'totalTestCount': 8}, {'passedTests': 7}, {'skippedTests': 1}, {'result': 'Passed'},
                     {'finishTime': None}, {'finishTime': 9900}, {'startTime': 8000}, {'finishTime': 10010},
                     {'testFailures': []}, {'testFailures': [{'targetName': 'other', 'testIdentifierString': 'QRCatcherUITests/testProductionCameraAllowThenResetAndDeny'}]},
                     {'devicesAndConfigurations': []}, {'devicesAndConfigurations': [{'device': {'deviceId': 'wrong', 'platform': 'iOS Simulator'}}]}]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                gate.validate_finalization(operation(), {**summary(10000), **mutation}, DEVICE, 10000)
        for text in [None, '', 'XCTAssertTrue failed', 'Test exceeded execution time allowance of 4 minutes']:
            value = summary(10000)
            if text is None: value['testFailures'][0].pop('failureText')
            else: value['testFailures'][0]['failureText'] = text
            with self.subTest(failureText=text), self.assertRaises(ValueError):
                gate.validate_finalization(operation(), value, DEVICE, 10000)

    def test_budget_admits_full_existing_allowances_and_reserve_only(self):
        for phase, cost in gate.BUDGETS.items():
            required = cost + 90; now = 10000
            self.assertTrue(gate.budget(now - (1200 - required), phase, now)['admitted'])
            self.assertFalse(gate.budget(now - (1200 - required + .001), phase, now)['admitted'])
        self.assertTrue(gate.budget(1000, 'files', 1512)['admitted'])
        self.assertFalse(gate.budget(1000, 'seed-and-photos', 1700)['admitted'])
        for start in [float('nan'), float('inf'), -1, 10001]:
            with self.assertRaises(ValueError): gate.budget(start, 'files', 10000)

    def test_wrong_identity_and_barrier_prevent_all_new_commands(self):
        env = {'GITHUB_SHA': SOURCE, 'GITHUB_REPOSITORY': '100mango/QRCatcher', 'GITHUB_REF': 'refs/heads/codex/apple-platforms',
               'EVIDENCE_SCOPE': 'iphone_pro', 'SIMULATOR_ID': DEVICE}
        with patch.dict(os.environ, env):
            self.assertEqual(gate.identity(DEVICE, gate.RESULT), SOURCE)
            for key, value in [('GITHUB_SHA', 'bad'), ('GITHUB_REPOSITORY', 'other/repo'), ('GITHUB_REF', 'refs/heads/main'),
                               ('EVIDENCE_SCOPE', 'iphone_se3'), ('SIMULATOR_ID', 'wrong')]:
                with self.subTest(key=key), patch.dict(os.environ, {key: value}), self.assertRaises(ValueError): gate.identity(DEVICE, gate.RESULT)
        with patch.object(gate, 'blocked', return_value=True), patch.object(gate, 'execute') as command:
            self.assertEqual(gate.main(['admit', DEVICE, gate.RESULT, '1000']), 126); command.assert_not_called()

    def test_owned_check_commands_require_completed_and_confirmed_cleanup(self):
        for code, record in [(124, {'state': 'timed_out', 'cleanup_confirmed': True}),
                             (0, {'state': 'completed', 'cleanup_confirmed': False}),
                             (0, {'state': 'missing', 'cleanup_confirmed': True})]:
            with patch.object(gate, 'execute', return_value=(code, '{}', record)), self.assertRaises(RuntimeError): gate.checked(['read-only'], 5)


class ContinuationShellTests(unittest.TestCase):
    def run_shell(self, mode):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve(); (work / 'scripts').mkdir(); (work / 'bin').mkdir()
            for name in ['run_ios_platform_ui.sh', 'run_bounded.py', 'watch_process.py', 'owned_process_group.py', 'owned_process_barrier.py',
                         'atomic_json.py', 'stage_owned_import_fixture.py', 'ios_import_continuation.py']:
                shutil.copyfile(ROOT / 'scripts' / name, work / 'scripts' / name)
            products = work / 'build/iOS/Build/Products/Debug-iphonesimulator'
            app = products / 'QRCatcher.app'; runner = products / 'QRCatcherUITests-Runner.app'; app.mkdir(parents=True); runner.mkdir()
            (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': '100mango.QRCatcher', 'UIFileSharingEnabled': True, 'LSSupportsOpeningDocumentsInPlace': True}))
            (runner / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': '100mango.QRCatcherUITests.xctrunner'}))
            data = work / 'synthetic-data'; data.mkdir(); fixture = work / 'Tests/Fixtures/unicode.png'; fixture.parent.mkdir(parents=True); fixture.write_bytes(b'synthetic-routing-only')
            stub = '''#!/usr/bin/env python3
import json,os,sys,time,plistlib
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:];mode=os.environ['MODE']
record=Path('calls.json');rows=json.loads(record.read_text()) if record.exists() else [];rows.append([name,args]);record.write_text(json.dumps(rows))
if name=='git':
 if args==['rev-parse','HEAD']:print(os.environ['GITHUB_SHA'] if mode!='wrong-head' else 'b'*40)
 if mode=='source-change-after-files' and args[0]=='diff' and any(tool=='xcodebuild' and any('testRealFilesImportAndReopen' in a for a in command) for tool,command in rows):raise SystemExit(1)
 raise SystemExit(1 if mode=='dirty-source' and args[0]=='diff' else 0)
if name=='xcodebuild':
 if any('testRealFilesImportAndReopen' in arg for arg in args):
  if mode=='files-barrier':Path(os.environ['QRCATCHER_OWNED_PROCESS_BARRIER']).write_text('{"blocked":true}')
  if mode=='metadata-change-after-files':
   p=Path(os.environ['APP'])/'Info.plist';v=plistlib.loads(p.read_bytes());v['fixture_revision']='changed';p.write_bytes(plistlib.dumps(v))
  raise SystemExit(65 if mode=='files-failure' else 0)
 if any('testRealPhotosImportAndReopen' in arg for arg in args):raise SystemExit(0)
 print('** TEST EXECUTE FAILED **');raise SystemExit(65)
if args[:2]==['xcresulttool','get']:
 now=time.time();value={'result':'Failed','totalTestCount':9,'passedTests':8,'failedTests':1,'skippedTests':0,'expectedFailures':0,'startTime':now-1,'finishTime':now-.1,
 'testFailures':[{'targetName':'QRCatcherUITests','testIdentifierString':'QRCatcherUITests/testProductionCameraAllowThenResetAndDeny','failureText':'Test exceeded execution time allowance of 3 minutes'}],
 'devicesAndConfigurations':[{'device':{'deviceId':os.environ['SIMULATOR_ID'],'platform':'iOS Simulator'}}]}
 if mode=='partial-summary':value['totalTestCount']=8
 if mode=='different-failure':value['testFailures'][0]['failureText']='XCTAssertTrue failed'
 if mode=='missing-failure':value['testFailures'][0].pop('failureText')
 print(json.dumps(value));raise SystemExit(0)
if len(args)>1 and args[1]=='get_app_container':
 print(os.environ['APP' if args[-1]=='app' else 'DATA'])
 if mode=='metadata-change-during-setup' and args[-1]=='data':
  p=Path(os.environ['APP'])/'Info.plist';v=plistlib.loads(p.read_bytes());v['fixture_revision']='changed';p.write_bytes(plistlib.dumps(v))
if len(args)>1 and args[1]=='addmedia':raise SystemExit(13 if mode=='seed-failure' else 0)
'''
            for name in ['xcrun', 'xcodebuild', 'git']:
                path = work / 'bin' / name; path.write_text(stub); path.chmod(0o755)
            # Only the shell's initial clock read is doubled; every gate still
            # executes its actual monotonic-budget implementation unchanged.
            interpreter = work / 'bin/python3'
            interpreter.write_text('#!' + sys.executable + '\nimport os,sys,time\n'
                'if sys.argv[1:]==["-c","import time;print(time.monotonic())"]:\n'
                ' print(time.monotonic()-({"no-files-budget":800,"files-only-budget":600}.get(os.environ["MODE"],0)))\n'
                'else:os.execv(' + repr(sys.executable) + ',[' + repr(sys.executable) + ']+sys.argv[1:])\n')
            interpreter.chmod(0o755)
            env = {**os.environ, 'GITHUB_SHA': SOURCE, 'GITHUB_REPOSITORY': '100mango/QRCatcher', 'GITHUB_REF': 'refs/heads/codex/apple-platforms',
                   'EVIDENCE_SCOPE': 'iphone_pro', 'SIMULATOR_ID': DEVICE, 'GITHUB_WORKSPACE': str(work), 'GITHUB_ENV': str(work / 'github-env'),
                   'QRCATCHER_OWNED_PROCESS_BARRIER': str(work / 'build/owned-process-cleanup.json'), 'MODE': mode,
                   'APP': str(app), 'DATA': str(data), 'PATH': str(work / 'bin') + ':' + os.environ['PATH'],
                   'PYTHONOPTIMIZE': str(sys.flags.optimize)}
            env.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED', None)
            result = subprocess.run(['bash', 'scripts/run_ios_platform_ui.sh', DEVICE, gate.RESULT, 'QRCatcherUITests'], cwd=work, env=env, capture_output=True, text=True, timeout=15)
            if not (work / 'build/ios-platform-setup.json').exists(): self.fail(result.stdout + result.stderr)
            setup = json.loads((work / 'build/ios-platform-setup.json').read_text()); calls = json.loads((work / 'calls.json').read_text())
            return result, setup, calls

    def test_completed_original_failure_remains_red_after_fresh_distinct_imports(self):
        for mode in ['normal', 'files-failure']:
            with self.subTest(mode=mode):
                result, setup, calls = self.run_shell(mode)
                self.assertEqual(result.returncode, 65, result.stdout + result.stderr)
                self.assertEqual(setup['layout_and_real_picker_cancel_exit'], 65)
                self.assertEqual(setup['real_files_case_exit'], 65 if mode == 'files-failure' else 0)
                self.assertEqual(setup['real_photo_case_exit'], 0)
                commands = [args for name, args in calls if name == 'xcodebuild']; self.assertEqual(len(commands), 3)
                self.assertEqual(setup['seed_attempts'], 1)
                self.assertEqual(len(setup['independent_import_continuation']['budget_checks']), 4)

    def test_source_summary_seed_and_cleanup_failures_do_not_become_passes(self):
        for mode, expected, count in [('wrong-head', 65, 1), ('dirty-source', 65, 1), ('partial-summary', 65, 1),
                                      ('different-failure', 65, 1), ('missing-failure', 65, 1),
                                      ('metadata-change-during-setup', 65, 1), ('metadata-change-after-files', 65, 2), ('source-change-after-files', 65, 2),
                                      ('files-barrier', 126, 2), ('seed-failure', 13, 2)]:
            with self.subTest(mode=mode):
                result, setup, calls = self.run_shell(mode)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                self.assertEqual(setup['layout_and_real_picker_cancel_exit'], 65)
                self.assertEqual(setup['real_photo_case_exit'], -1)
                self.assertEqual(sum(name == 'xcodebuild' for name, _ in calls), count)

    def test_actual_remaining_budget_marks_unexecuted_imports_without_reruns(self):
        for mode, count, files_exit in [('no-files-budget', 1, -1), ('files-only-budget', 2, 0)]:
            with self.subTest(mode=mode):
                result, setup, calls = self.run_shell(mode)
                self.assertEqual(result.returncode, 65, result.stdout + result.stderr)
                self.assertEqual(setup['layout_and_real_picker_cancel_exit'], 65)
                self.assertEqual(setup['real_files_case_exit'], files_exit)
                self.assertEqual(setup['real_photo_case_exit'], -1)
                self.assertEqual(setup['seed_attempts'], 0)
                self.assertFalse(setup['independent_import_continuation']['allowed'])
                self.assertEqual(sum(name == 'xcodebuild' for name, _ in calls), count)


if __name__ == '__main__':
    unittest.main()
