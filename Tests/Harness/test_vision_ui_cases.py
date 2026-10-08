"""Portable command routing only; no Apple execution or fresh-VM proof claimed."""
import contextlib, io, json, os, runpy, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from vision_case_contract import CASES

class Capture:
    def __init__(self,mode):self.mode=mode;self.waits=[]
    def wait(self,timeout):
        self.waits.append(timeout)
        if self.mode=='timeout':raise subprocess.TimeoutExpired('owned capture helper',timeout)
        return int(self.mode=='failure')

class VisionRoutingTests(unittest.TestCase):
    def setUp(self):
        isolation=patch.dict(os.environ);isolation.start();self.addCleanup(isolation.stop)
        for key in ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED','QRCATCHER_OWNED_PROCESS_BARRIER','GITHUB_ENV','GITHUB_OUTPUT','GITHUB_WORKSPACE']:os.environ.pop(key,None)
    def exercise(self,case,failed=False,capture_mode='success',unknown_at=None,missing=False,invalid=None):
        calls=[]
        def execute(command,seconds):
            calls.append((command,seconds));code=124 if failed and command[0]=='xcodebuild' else 0
            detail={'exit':code,'timeout_seconds':seconds,'cleanup_confirmed':True}
            if unknown_at==len(calls):
                code=126;detail.update(exit=126,cleanup_confirmed=False)
                if missing:detail.pop('cleanup_confirmed')
            return code,'bounded diagnostic tail',detail
        capture=Capture(capture_mode);device='11111111-1111-4111-8111-111111111111'
        with tempfile.TemporaryDirectory() as directory:
            old=Path.cwd()
            try:
                os.chdir(Path(directory).resolve())
                if invalid=='prior-report':
                    Path('build/vision-runtime').mkdir(parents=True);Path('build/vision-runtime/ui-cases.json').write_text('{}')
                if invalid=='prior-result':Path('VisionPhotosUIResults.xcresult').mkdir()
                scope='visionos' if invalid=='scope' else case.scope
                environment={'GITHUB_SHA':'a'*40,'EVIDENCE_SCOPE':('visionos_files' if invalid=='mismatch' else scope)}
                argv=['run_vision_ui_cases.py',device,scope]
                if invalid=='missing-selection':argv.pop()
                with patch('watch_process.execute',side_effect=execute),patch.dict(os.environ,environment), \
                     patch.object(sys,'argv',argv),patch('subprocess.Popen',return_value=capture) as launch, \
                     patch('owned_process_group.stop_group',return_value=True) as cleanup, \
                     patch('run_native_size_case.run_case',return_value=(2 if failed else 0,{'status':'failed' if failed else 'largest_ui_passed'})) as largest, \
                     contextlib.redirect_stdout(io.StringIO()):
                    if invalid:
                        with self.assertRaises(ValueError):runpy.run_path(str(ROOT/'scripts/run_vision_ui_cases.py'),run_name='__main__')
                    elif failed or capture_mode!='success' or unknown_at:
                        with self.assertRaises(SystemExit):runpy.run_path(str(ROOT/'scripts/run_vision_ui_cases.py'),run_name='__main__')
                    else:runpy.run_path(str(ROOT/'scripts/run_vision_ui_cases.py'),run_name='__main__')
                if invalid:
                    launch.assert_not_called();self.assertEqual(calls,[]);largest.assert_not_called();return None
                report=json.loads(Path('build/vision-runtime/ui-cases.json').read_text())
                self.assertTrue(Path('build/vision-runtime/ui-completed.marker').exists())
                launch.assert_called_once();self.assertEqual(launch.call_args.args[0],['python3','-u','scripts/capture_vision_checkpoints.py',device,'vision-ui-test.log',case.scope]);cleanup.assert_called_once_with(capture)
                self.assertEqual(len(report['cases']),1)
                for row in [report,report['cases'][0]]:
                    self.assertEqual({k:row[k] for k in ['scope','case','result','source_commit','device']},{'scope':case.scope,'case':case.name,'result':case.result,'source_commit':'a'*40,'device':device})
                if case.scope=='visionos_largest' and not unknown_at:
                    largest.assert_called_once_with('vision',device);self.assertEqual(len(calls),1)
                else:
                    largest.assert_not_called();self.assertEqual(len(calls),unknown_at or 2)
                if len(calls)>1:
                    command,seconds=calls[1]
                    self.assertEqual(seconds,case.seconds)
                    self.assertEqual(command[command.index('-resultBundlePath')+1],case.result)
                    self.assertEqual([v for v in command if v.startswith('-only-testing:')],['-only-testing:QRCatcherVisionUITests/QRCatcherVisionUITests/'+case.name])
                    self.assertEqual(command[command.index('-default-test-execution-time-allowance')+1],str(case.default_seconds))
                    self.assertEqual(command[command.index('-maximum-test-execution-time-allowance')+1],str(case.maximum_seconds))
                return report,capture
            finally:os.chdir(old)
    def test_each_fresh_vm_selects_exactly_one_existing_case_and_result(self):
        for case in CASES:
            with self.subTest(scope=case.scope):self.exercise(case)
    def test_failure_never_retries_or_routes_another_case(self):
        for case in CASES:
            report,_=self.exercise(case,failed=True);self.assertNotEqual(report['cases'][0]['exit'],0)
    def test_capture_failure_and_timeout_keep_gate_red(self):
        for mode in ['failure','timeout']:
            report,capture=self.exercise(CASES[0],capture_mode=mode)
            self.assertEqual(report['capture_process_exit'],124 if mode=='timeout' else 1);self.assertEqual(capture.waits,[30])
    def test_missing_or_false_cleanup_proof_stops_the_only_case(self):
        for position in [1,2]:
            for missing in [True,False]:
                os.environ.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED',None)
                report,_=self.exercise(CASES[0],unknown_at=position,missing=missing);self.assertTrue(report['cleanup_unconfirmed'])
    def test_unknown_missing_mismatched_selection_and_reused_vm_fail_before_any_command(self):
        for invalid in ['scope','missing-selection','mismatch','prior-report','prior-result']:
            with self.subTest(invalid=invalid):self.exercise(CASES[0],invalid=invalid)

if __name__=='__main__':unittest.main()
