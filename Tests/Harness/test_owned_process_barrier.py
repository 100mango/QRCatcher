"""Actual local process/shell negatives; never an Apple app or permission action."""
import contextlib,io,json,os,runpy,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from watch_process import execute

class OwnedBarrierTests(unittest.TestCase):
    def setUp(self):
        isolation=patch.dict(os.environ);isolation.start();self.addCleanup(isolation.stop)
        for key in ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED','QRCATCHER_OWNED_PROCESS_BARRIER','GITHUB_ENV','GITHUB_WORKSPACE']:os.environ.pop(key,None)
    def env(self,folder):
        # macOS exposes /var/folders through /private/var/folders. Use the same
        # canonical owned root for both values; the production guard stays exact.
        folder=folder.resolve()
        fixture=dict(os.environ,GITHUB_WORKSPACE=str(folder),GITHUB_ENV=str(folder/'github-env'),QRCATCHER_OWNED_PROCESS_BARRIER=str(folder/'build/owned-process-cleanup.json'),GITHUB_REF='refs/heads/codex/apple-platforms')
        for key in ('IOS_FIRST_RELEASE_CANDIDATE_ONLY','QRCATCHER_IOS_SUPPLEMENT_ONLY','PHONE_COMPLETION_ONLY','EVIDENCE_SCOPE'):
            fixture.pop(key,None)
        return fixture
    def test_fixture_root_canonicalizes_system_temp_directory_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owned=root/'owned';owned.mkdir();alias=root/'alias';alias.symlink_to(owned,target_is_directory=True)
            env=self.env(alias)
            self.assertEqual(env['GITHUB_WORKSPACE'],str(owned.resolve()))
            self.assertEqual(env['QRCATCHER_OWNED_PROCESS_BARRIER'],str(owned.resolve()/'build/owned-process-cleanup.json'))
    def test_default_fixture_selection_preserves_inherited_uncertainty_and_caller(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                'GITHUB_REF':'refs/heads/codex/ios-original-supplement','IOS_FIRST_RELEASE_CANDIDATE_ONLY':'true',
                'QRCATCHER_IOS_SUPPLEMENT_ONLY':'true','EVIDENCE_SCOPE':'ipad_mini','QRCATCHER_OWNED_CLEANUP_UNCONFIRMED':'true'}):
            before=dict(os.environ);fixture=self.env(Path(directory))
            self.assertEqual(dict(os.environ),before)
            self.assertEqual(fixture['GITHUB_REF'],'refs/heads/codex/apple-platforms')
            self.assertTrue(all(key not in fixture for key in ('IOS_FIRST_RELEASE_CANDIDATE_ONLY','QRCATCHER_IOS_SUPPLEMENT_ONLY','EVIDENCE_SCOPE')))
            self.assertEqual(fixture['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED'],'true')
    def test_exit_two_unknown_cleanup_is_durable_and_blocks_fresh_process(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);env=self.env(folder)
            with patch.dict(os.environ,env),patch('watch_process.stop_group',return_value=False):
                code,_,operation=execute([sys.executable,'-c','raise SystemExit(2)'],3,echo=False)
            self.assertEqual(code,126);self.assertEqual(operation['original_exit'],2)
            marker=json.loads((folder/'build/owned-process-cleanup.json').read_text());self.assertTrue(marker['blocked'])
            self.assertIn('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED=true',(folder/'github-env').read_text())
            sentinel=folder/'must-not-exist'
            result=subprocess.run([sys.executable,str(ROOT/'scripts/run_bounded.py'),'3',sys.executable,'-c','from pathlib import Path; Path('+repr(str(sentinel))+').touch()'],cwd=folder,env=env,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,126,result.stdout+result.stderr);self.assertFalse(sentinel.exists())
    def test_nested_unknown_exit_is_not_erased_by_clean_wrapper(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,self.env(Path(directory))):
            code,_,operation=execute([sys.executable,'-c','raise SystemExit(126)'],3,echo=False)
            self.assertEqual(code,126);self.assertFalse(operation['cleanup_confirmed'])
            self.assertTrue(Path(os.environ['QRCATCHER_OWNED_PROCESS_BARRIER']).exists())
    def test_completed_child_exit_two_keeps_independent_work_available(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,self.env(Path(directory))):
            code,_,operation=execute([sys.executable,'-c','raise SystemExit(2)'],3,echo=False)
            self.assertEqual(code,2);self.assertTrue(operation['cleanup_confirmed'])
            self.assertFalse(Path(os.environ['QRCATCHER_OWNED_PROCESS_BARRIER']).exists())
    def test_mac_exit_cleanup_trap_preserves_boundary_fixture_after_unknown_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'scripts').mkdir();(folder/'build').mkdir()
            for name in ['owned_process_barrier.py','atomic_json.py']:shutil.copyfile(ROOT/'scripts'/name,folder/'scripts'/name)
            (folder/'build/owned-process-cleanup.json').write_text('{"blocked":true}')
            boundary=folder/'synthetic-boundary.txt';boundary.write_text('must survive until disposable VM teardown')
            text=(ROOT/'scripts/run_mac_sandbox.sh').read_text();trap=text.split('<<"CLEANUP"\n',1)[1].split('\nCLEANUP',1)[0]
            result=subprocess.run([sys.executable,'-c',trap],cwd=folder,env=self.env(folder),capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,126,result.stdout+result.stderr);self.assertTrue(boundary.exists())
    def test_nested_watch_diagnostics_propagates_missing_or_false_cleanup(self):
        for missing in [False,True]:
            with tempfile.TemporaryDirectory() as directory:
                folder=Path(directory);old=Path.cwd();operation={'exit':126,'cleanup_confirmed':False,'state':'cleanup_unconfirmed'}
                if missing:operation.pop('cleanup_confirmed')
                try:
                    os.chdir(folder)
                    with patch.dict(os.environ,self.env(folder)),patch('watch_process.execute',return_value=(126,'',operation)),patch.object(Path,'home',return_value=folder),patch.object(sys,'argv',['diagnostics','11111111-2222-4333-8444-555555555555']),contextlib.redirect_stdout(io.StringIO()):
                        with self.assertRaises(SystemExit) as error:runpy.run_path(str(ROOT/'scripts/collect_watch_startup_diagnostics.py'),run_name='__main__')
                        self.assertEqual(error.exception.code,126)
                    self.assertTrue(json.loads((folder/'build/watch-runtime/hosted-startup-diagnostics.json').read_text())['cleanup_unconfirmed'])
                finally:os.chdir(old)
    def test_watch_owner_stops_before_device_creation_on_unresolved_first_command(self):
        for missing in [False,True]:
            with tempfile.TemporaryDirectory() as directory:
                folder=Path(directory);old=Path.cwd();detail={'exit':126,'cleanup_confirmed':False}
                if missing:detail.pop('cleanup_confirmed')
                try:
                    os.chdir(folder)
                    with patch.dict(os.environ,dict(self.env(folder),GITHUB_SHA='a'*40)),patch('watch_process.execute',return_value=(126,'',detail)) as runner,contextlib.redirect_stdout(io.StringIO()):
                        with self.assertRaises(RuntimeError):runpy.run_path(str(ROOT/'scripts/run_watch_platform_tests.py'),run_name='__main__')
                        self.assertEqual(runner.call_count,1)
                    self.assertTrue((folder/'build/owned-process-cleanup.json').exists())
                finally:os.chdir(old)
    def shell_negative(self,stage):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);scripts=folder/'scripts';scripts.mkdir();binary=folder/'bin';binary.mkdir()
            for name in ['run_tv_platform_tests.sh','run_ios_platform_ui.sh','run_bounded.py','watch_process.py','owned_process_group.py','owned_process_barrier.py','atomic_json.py']:
                shutil.copyfile(ROOT/'scripts'/name,scripts/name)
            # Only this disposable command owner is fault-injected. The actual
            # shell and wrapper still propagate the real exit/status metadata.
            prefix='import os,watch_process\n_original=watch_process.stop_group\ndef injected(process):\n args=process.args\n stage=os.environ["NEGATIVE_STAGE"]\n chosen=(stage=="tv-test" and args[0]=="xcodebuild") or (stage=="tv-size" and "scripts/run_native_size_case.py" in args) or (stage=="ios-boot" and "boot" in args)\n return False if chosen else _original(process)\nwatch_process.stop_group=injected\n'
            script=scripts/'run_bounded.py';script.write_text(prefix+script.read_text())
            (scripts/'run_native_size_case.py').write_text('raise SystemExit(2)\n')
            stub='''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:];log=Path(os.environ['COMMAND_LOG'])
with log.open('a') as output:output.write(json.dumps([name]+args)+'\\n')
if name=='xcrun' and args[:4]==['simctl','list','devices','available']:
 print(json.dumps({'devices':{'com.apple.CoreSimulator.SimRuntime.tvOS-27-0':[{'name':'Apple TV 4K','udid':'11111111-2222-4333-8444-555555555555'}]}}))
if name=='xcodebuild' and os.environ['NEGATIVE_STAGE']=='tv-test':raise SystemExit(2)
if name=='xcrun' and 'boot' in args and os.environ['NEGATIVE_STAGE']=='ios-boot':raise SystemExit(2)
'''
            for name in ['xcrun','xcodebuild']:
                p=binary/name;p.write_text(stub);p.chmod(0o755)
            env=dict(self.env(folder),PATH=str(binary)+os.pathsep+os.environ['PATH'],COMMAND_LOG=str(folder/'commands.jsonl'),NEGATIVE_STAGE=stage)
            command=['bash',str(scripts/('run_ios_platform_ui.sh' if stage=='ios-boot' else 'run_tv_platform_tests.sh'))]
            if stage=='ios-boot':command+=['11111111-2222-4333-8444-555555555555','Unused.xcresult','QRCatcherUITests']
            result=subprocess.run(command,cwd=folder,env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,126,result.stdout+result.stderr)
            calls=[json.loads(row) for row in (folder/'commands.jsonl').read_text().splitlines()]
            self.assertFalse(any('privacy' in args or 'terminate' in args for args in calls),calls)
            if stage=='ios-boot':self.assertEqual(len(calls),1);self.assertIn('boot',calls[0])
            else:self.assertEqual(len([args for args in calls if args[0]=='xcodebuild']),1)
            self.assertEqual(json.loads((folder/'build/owned-process-cleanup.json').read_text())['operation']['original_exit'],2)
    def test_tv_normal_and_nested_size_cleanup_unknown_stop_before_permissions_or_more_ui(self):
        for stage in ['tv-test','tv-size']:
            with self.subTest(stage=stage):self.shell_negative(stage)
    def test_ios_boot_unknown_cleanup_cannot_be_swallowed_by_or_true(self):self.shell_negative('ios-boot')

if __name__=='__main__':unittest.main()
