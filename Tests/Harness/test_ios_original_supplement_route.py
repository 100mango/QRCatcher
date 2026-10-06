"""Fixed missing-case identity/render and hosted receipt contracts; no Apple run."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import ios_original_release_route as original
import ios_original_supplement_route as route
from test_ios_only_project import parse_project, paths_in_phase

SHA = 'f'*40
DEVICE = 'ABCDEF12-3456-4789-ABCD-EF0123456789'

class SupplementRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.previous=Path.cwd();os.chdir(self.root)
        for rel in [original.CANONICAL,original.WORKFLOW,route.WORKFLOW]:
            dst=self.root/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,dst)
        (self.root/'build').mkdir()
        self.env={'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_SHA':SHA,'GITHUB_WORKFLOW_SHA':SHA,
            'GITHUB_REF':route.REF,'GITHUB_WORKFLOW_REF':route.WORKFLOW_REF,'GITHUB_EVENT_NAME':'push',
            'GITHUB_RUN_ID':'9','GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'platform','EVIDENCE_SCOPE':'iphone_pro',
            'RUNNER_OS':'macOS','RUNNER_ARCH':'ARM64','IOS_FIRST_RELEASE_CANDIDATE_ONLY':'true',
            'QRCATCHER_IOS_SUPPLEMENT_ONLY':'true','GITHUB_WORKSPACE':str(self.root),
            'QRCATCHER_OWNED_PROCESS_BARRIER':str(self.root/'build/owned-process-cleanup.json')}
        self.environment=patch.dict(os.environ,self.env,clear=True);self.environment.start()
    def tearDown(self):
        self.environment.stop();os.chdir(self.previous);self.temp.cleanup()
    def test_exact_new_identity_and_unchanged_old_generated_workflow(self):
        identity=route.current_identity()
        self.assertTrue(identity['diagnostic_only']);self.assertFalse(identity['release_qualification'])
        self.assertFalse(identity['full_original_row_qualification'])
        self.assertEqual(identity['required_phone_cases'],{'ordinary':2,'files':1,'photos':1})
        self.assertEqual(len(identity['selected_cases']),4)
        self.assertEqual(original.current_identity(),identity)
        self.assertEqual(Path(original.WORKFLOW).read_text(),original.render_workflow(Path(original.CANONICAL).read_text()))
        self.assertEqual(hashlib.sha256(Path(original.WORKFLOW).read_bytes()).hexdigest(),'f11c3a0b0282c597e9903cc0f45a47cad67e9cc005a895b6b51614fb15ed1698')
        self.assertEqual(hashlib.sha256(Path(original.CANONICAL).read_bytes()).hexdigest(),original.CANONICAL_SHA256)
    def test_wrong_ref_flags_workflow_scope_runner_and_source_fail_without_process(self):
        variants=[('GITHUB_REF',original.REF),('GITHUB_WORKFLOW_REF',original.WORKFLOW_REF),
            ('QRCATCHER_IOS_SUPPLEMENT_ONLY','false'),('IOS_FIRST_RELEASE_CANDIDATE_ONLY','false'),
            ('GITHUB_EVENT_NAME','workflow_dispatch'),('EVIDENCE_SCOPE','macos'),('RUNNER_ARCH','X64'),
            ('GITHUB_WORKFLOW_SHA','e'*40),('GITHUB_REPOSITORY','other/QRCatcher'),('GITHUB_RUN_ATTEMPT','0')]
        for key,value in variants:
            with self.subTest(key=key),patch.dict(os.environ,{key:value}),patch('watch_process.execute') as execute:
                with self.assertRaises(ValueError):route.current_identity()
                execute.assert_not_called()
    def test_every_scope_has_closed_case_inventory_and_original_caps(self):
        for scope,count in [('iphone_pro',4),('iphone_se3',4),('ipad_pro',4),('ipad_mini',2)]:
            with patch.dict(os.environ,{'EVIDENCE_SCOPE':scope}):
                value=route.current_identity();self.assertEqual(len(value['selected_cases']),count)
                self.assertEqual(value['mini_row_seconds'],2220);self.assertEqual(value['mini_job_seconds'],3000)
                self.assertEqual(value['first_mini_bootstrap_caps'],{'precheck':30,'boot':30,'bootstatus':210})
        with self.assertRaises(ValueError):route.selected_cases('dynamic')
    def test_workflow_limits_same_source_preflight_and_single_push_are_closed(self):
        text=route.WORKFLOW.read_text()
        for clause in ['needs: preflight','max-parallel: 1','cancel-in-progress: false','contents: read',
                       'python3 -u scripts/compile_ios_original_preflight.py',route.BRANCH,
                       'retain-hosted "$SIMULATOR_ID" "$UNIT_EXIT"','-only-testing:QRCatcherTests']:
            self.assertIn(clause,text)
        self.assertNotIn('workflow_dispatch:',text)
        self.assertNotIn('larger',text)
        self.assertIn('no original full-row or release pass',text)
        for old,new in [('max-parallel: 1','max-parallel: 2'),('needs: preflight','needs: different'),
                        (route.BRANCH,'codex/open-ref'),('timeout-minutes: 37','timeout-minutes: 38')]:
            route.WORKFLOW.write_text(text.replace(old,new,1))
            with self.assertRaises(ValueError):route.current_identity()
        route.WORKFLOW.write_text(text)
    def test_provenance_remains_within_original4096_byte_bound_with_long_ids(self):
        with patch.dict(os.environ,{'GITHUB_RUN_ID':'9'*20,'GITHUB_RUN_ATTEMPT':'9'*20,'EVIDENCE_SCOPE':'ipad_mini'}):
            identity=route.current_identity()
            identity.update(tested_tree='e'*40,source_readback_phase='existing bounded managed Mini prepare HEAD/tree/diff')
            self.assertLessEqual(len(json.dumps(identity).encode()),4096)
    def hosted_fixture(self, exit_code=0):
        line=next(line for line in route.WORKFLOW.read_text().splitlines() if 'scripts/run_bounded.py 855 xcodebuild' in line)
        command=shlex.split(line.split('| tee')[0].strip())[4:]
        command=[value.replace('$SIMULATOR_ID',DEVICE) for value in command]
        operation={'command':command,'timeout_seconds':855,'state':'completed','exit':exit_code,
                   'cleanup_confirmed':True,'elapsed_seconds':260.63,'output_bytes':123}
        text='BOUNDED_COMMAND_START '+json.dumps({'seconds':855,'command':command})+'\n'+'native selected output\n'+'BOUNDED_COMMAND_END '+json.dumps(operation)+'\n'
        Path('ios-unit.log').write_text(text)
        summary={'totalTestCount':30,'passedTests':30 if exit_code==0 else 29,'failedTests':0 if exit_code==0 else 1,
                 'skippedTests':0,'expectedFailures':0,'devicesAndConfigurations':[{'device':{'deviceId':DEVICE}}],
                 'runtimeWarnings':[],'result':'Passed' if exit_code==0 else 'Failed','testFailures':[] if exit_code==0 else[{'testName':'fixed'}]}
        def execute(command,cap,**kwargs):
            self.assertEqual(cap,10);self.assertTrue(Path('build/iOSUnitResults-command.json').is_file())
            raw=json.dumps(summary)
            return 0,raw,{'command':command,'timeout_seconds':cap,'exit':0,'state':'completed','cleanup_confirmed':True,
                          'elapsed_seconds':4.66,'output_bytes':len(raw.encode())}
        return operation,summary,execute
    def test_actual_hosted_command_binding_retains_completed_pass_or_failure_before_later_work(self):
        for exit_code in (0,65):
            operation,summary,executor=self.hosted_fixture(exit_code)
            with patch('watch_process.execute',side_effect=executor):value=route.retain_hosted(DEVICE,exit_code)
            self.assertEqual(value['counts']['totalTestCount'],30)
            self.assertEqual(json.loads(Path('build/iOSUnitResults-summary.json').read_text()),summary)
            self.assertEqual(json.loads(Path('build/iOSUnitResults-command.json').read_text()),operation)
    def test_hosted_late_or_foreign_command_never_queries_summary(self):
        for key,value in [('state','timed_out'),('cleanup_confirmed',False),('elapsed_seconds',857),('timeout_seconds',854)]:
            operation,summary,executor=self.hosted_fixture()
            operation[key]=value
            lines=Path('ios-unit.log').read_text().splitlines();lines[-1]='BOUNDED_COMMAND_END '+json.dumps(operation)
            Path('ios-unit.log').write_text('\n'.join(lines)+'\n')
            with patch('watch_process.execute') as execute,patch('owned_process_barrier.mark_unconfirmed'):
                with self.assertRaises(ValueError):route.retain_hosted(DEVICE,0)
                execute.assert_not_called()
    def test_hosted_summary_mismatch_retains_raw_bytes_but_cannot_qualify(self):
        for change in [{'totalTestCount':29},{'skippedTests':1},{'runtimeWarnings':['warning']},
                       {'devicesAndConfigurations':[{'device':{'deviceId':'wrong'}}]}, {'result':'Failed'}]:
            operation,summary,executor=self.hosted_fixture();summary.update(change)
            with patch('watch_process.execute',side_effect=executor),patch('owned_process_barrier.mark_unconfirmed'):
                with self.assertRaises(ValueError):route.retain_hosted(DEVICE,0)
            self.assertEqual(json.loads(Path('build/iOSUnitResults-summary.json').read_text()),summary)

class ProductClosureTests(unittest.TestCase):
    def test_three_test_path_changes_leave_shipping_controller_and_consumers_bound(self):
        project=ROOT/'QRCatcher-iOS-Only.xcodeproj/project.pbxproj'
        objects=parse_project(project)['objects'];targets={v['name']:v for v in objects.values() if v.get('isa')=='PBXNativeTarget'}
        app=paths_in_phase(objects,targets['QRCatcher'],'PBXSourcesBuildPhase')
        self.assertIn('QRCatcher/QRPrivacyViewController.m',app)
        self.assertNotIn('QRCatcherTests/QRCatcherTests.m',app);self.assertNotIn('QRCatcherUITests/QRCatcherUITests.m',app)
        self.assertEqual(hashlib.sha256((ROOT/'QRCatcher/QRPrivacyViewController.m').read_bytes()).hexdigest(),
                         '4303215922f7e1a72a1c535eb3d757d785601d296b54034717de7046936a1fe3')

if __name__=='__main__':unittest.main()
