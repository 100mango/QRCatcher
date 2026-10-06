"""Fixed missing-case identity/render and hosted receipt contracts; no Apple run."""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import re
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
        route.WORKFLOW.write_text(route.render_legacy_workflow(Path(original.CANONICAL).read_text()))
        (self.root/'build').mkdir()
        self.env={'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_SHA':SHA,'GITHUB_WORKFLOW_SHA':SHA,
            'GITHUB_REF':route.REF,'GITHUB_WORKFLOW_REF':route.WORKFLOW_REF,'GITHUB_EVENT_NAME':'push',
            'GITHUB_RUN_ID':'9','GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'platform','EVIDENCE_SCOPE':'iphone_pro',
            'RUNNER_OS':'macOS','RUNNER_ARCH':'ARM64','IOS_FIRST_RELEASE_CANDIDATE_ONLY':'true',
            'QRCATCHER_IOS_SUPPLEMENT_ONLY':'true','GITHUB_WORKSPACE':str(self.root),
            'SIMULATOR_ID':DEVICE,
            'QRCATCHER_OWNED_PROCESS_BARRIER':str(self.root/'build/owned-process-cleanup.json')}
        self.environment=patch.dict(os.environ,self.env,clear=True);self.environment.start()
    def use_phone_workflow(self):
        route.WORKFLOW.write_text(route.render_workflow(Path(original.CANONICAL).read_text()))
        os.environ['PHONE_COMPLETION_ONLY']='true'
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
    def test_current_default_render_and_write_select_exact_two_phones_with_required_flag(self):
        canonical=Path(original.CANONICAL).read_text()
        legacy=route.render_legacy_workflow(canonical);current=route.render_workflow(canonical)
        self.assertEqual(legacy,route.WORKFLOW.read_text())
        self.assertNotIn('PHONE_COMPLETION_ONLY',legacy)
        self.assertEqual(current.count("  PHONE_COMPLETION_ONLY: 'true'\n"),1)
        self.assertEqual(current.split('      matrix:\n',1)[1].split("'on':",1)[0],
                         '        scope:\n        - iphone_pro\n        - iphone_se3\n')
        self.assertEqual(legacy.split('      matrix:\n',1)[1].split("'on':",1)[0],
                         '        scope:\n        - iphone_pro\n        - iphone_se3\n        - ipad_pro\n        - ipad_mini\n')
        self.assertEqual(hashlib.sha256(legacy.encode()).hexdigest(),'f30964f861d2885ba705bf3044bef60536ddbad2d234bc604c739cc610e3fea7')
        command=[sys.executable]+(['-O'] if not __debug__ else [])+[str(ROOT/'scripts/ios_original_supplement_route.py'),'write']
        result=subprocess.run(command,capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertEqual(route.WORKFLOW.read_text(),current)
        os.environ['PHONE_COMPLETION_ONLY']='true'
        for scope in route.PHONE_SCOPES:
            with patch.dict(os.environ,{'EVIDENCE_SCOPE':scope}):
                identity=route.current_identity()
                self.assertTrue(identity['phone_completion_only'])
                self.assertEqual(identity['selected_scopes'],['iphone_pro','iphone_se3'])
                self.assertEqual(identity,original.current_identity())
        with patch.dict(os.environ,{'GITHUB_JOB':'preflight','EVIDENCE_SCOPE':''}):
            self.assertEqual(route.current_identity()['selected_scopes'],['iphone_pro','iphone_se3'])
    def test_current_phone_workflow_rejects_missing_false_foreign_flags_refs_and_pad_mini_before_any_process(self):
        self.use_phone_workflow()
        for value in (None,'false','True','TRUE','','1','true\n'):
            with self.subTest(flag=value),patch.dict(os.environ),patch('watch_process.execute') as execute:
                if value is None:os.environ.pop('PHONE_COMPLETION_ONLY',None)
                else:os.environ['PHONE_COMPLETION_ONLY']=value
                with self.assertRaises(ValueError):route.current_identity()
                execute.assert_not_called()
        variants=[{'EVIDENCE_SCOPE':'ipad_pro'},{'EVIDENCE_SCOPE':'ipad_mini'},
                  {'GITHUB_REF':original.REF},{'GITHUB_WORKFLOW_REF':original.WORKFLOW_REF},
                  {'GITHUB_WORKFLOW_SHA':'e'*40},{'GITHUB_EVENT_NAME':'workflow_dispatch'}]
        for change in variants:
            with self.subTest(change=change),patch.dict(os.environ,change),patch('watch_process.execute') as execute:
                with self.assertRaises(ValueError):route.current_identity()
                execute.assert_not_called()
        text=route.WORKFLOW.read_text()
        for before,after in [("  PHONE_COMPLETION_ONLY: 'true'\n",''),
            ("  PHONE_COMPLETION_ONLY: 'true'\n","  PHONE_COMPLETION_ONLY: 'false'\n"),
            ('        - iphone_se3\n','        - iphone_se3\n        - ipad_pro\n'),
            ('        - iphone_se3\n','        - iphone_se3\n        - ipad_mini\n'),
            ('        - iphone_pro\n','        - iphone_se3\n'),
            ('        - iphone_se3\n','')]:
            route.WORKFLOW.write_text(text.replace(before,after,1))
            with self.subTest(before=before,after=after),patch('watch_process.execute') as execute:
                with self.assertRaises(ValueError):route.current_identity()
                execute.assert_not_called()
        route.WORKFLOW.write_text(text)
    def test_legacy_four_scope_profile_is_explicit_and_rejects_inherited_completion_flag(self):
        self.assertEqual(route.current_identity()['selected_scopes'],list(route.SCOPES))
        self.assertNotIn('phone_completion_only',route.current_identity())
        for value in ('true','false',''):
            with self.subTest(flag=value),patch.dict(os.environ,{'PHONE_COMPLETION_ONLY':value}),patch('watch_process.execute') as execute:
                with self.assertRaises(ValueError):route.current_identity()
                execute.assert_not_called()
    def test_current_phone_source_receipts_remain_bounded_with_maximum_ids(self):
        self.use_phone_workflow()
        for scope in route.PHONE_SCOPES:
            with patch.dict(os.environ,{'EVIDENCE_SCOPE':scope,'GITHUB_RUN_ID':'9'*20,'GITHUB_RUN_ATTEMPT':'9'*20}):
                value=route.current_identity();value.update(tested_tree='e'*40,source_readback_phase='bounded initial original iOS HEAD/tree/diff/status',
                    retention_verification={'initial_receipt_sha256':'e'*64,'device_barrier_observed':False,
                        'fresh_source_readback_performed':False,'qualification':'Initial prepare proof only; final managed source/post actions are separate'})
                self.assertLessEqual(len((json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()),4096)
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
                       'retain-hosted "$SIMULATOR_ID" "$UNIT_EXIT" "$HOSTED_STARTED"','-only-testing:QRCatcherTests']:
            self.assertIn(clause,text)
        self.assertNotIn('workflow_dispatch:',text)
        self.assertNotIn('larger',text)
        self.assertIn('no original full-row or release pass',text)
        hosted=text[text.index('    - name: Run iOS codec'):text.index('    - name: Run large-phone UI')]
        self.assertLess(hosted.index('HOSTED_STARTED='),hosted.index('owned_process_barrier.py --check'))
        self.assertLess(hosted.index('HOSTED_STARTED='),hosted.index('simctl boot'))
        self.assertEqual(hosted.count('HOSTED_STARTED='),1)
        reporting=text[text.index('    - name: Summarize executed evidence'):text.index('    - name: Verify final Mini source')]
        self.assertIn('scripts/ios_original_supplement_route.py summary-retained',reporting)
        self.assertNotIn('xcresulttool',reporting);self.assertNotIn('for RESULT in',reporting)
        for old,new in [('max-parallel: 1','max-parallel: 2'),('needs: preflight','needs: different'),
                        (route.BRANCH,'codex/open-ref'),('timeout-minutes: 37','timeout-minutes: 38')]:
            route.WORKFLOW.write_text(text.replace(old,new,1))
            with self.assertRaises(ValueError):route.current_identity()
        route.WORKFLOW.write_text(text)
    def test_provenance_remains_within_original4096_byte_bound_with_long_ids(self):
        for scope in route.SCOPES:
            with self.subTest(scope=scope),patch.dict(os.environ,{'GITHUB_RUN_ID':'9'*20,'GITHUB_RUN_ATTEMPT':'9'*20,'EVIDENCE_SCOPE':scope}):
                identity=route.current_identity()
                identity.update(tested_tree='e'*40,source_readback_phase='existing bounded managed Mini prepare HEAD/tree/diff'
                                if scope=='ipad_mini' else 'bounded initial original iOS HEAD/tree/diff/status')
                self.assertLessEqual(len((json.dumps(identity,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()),4096)
                identity['retention_verification']={'initial_receipt_sha256':'e'*64,'device_barrier_observed':False,
                    'fresh_source_readback_performed':False,'qualification':'Initial prepare proof only; final managed source/post actions are separate'}
                self.assertLessEqual(len((json.dumps(identity,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()),4096)
    def hosted_fixture(self, exit_code=0):
        self.phase_start=time.monotonic()
        for path in Path('build').glob('iOSUnitResults-*.json'):path.unlink()
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
            self.assertEqual(cap,30);self.assertTrue(Path('build/iOSUnitResults-command.json').is_file())
            raw=json.dumps(summary)
            return 0,raw,{'command':command,'timeout_seconds':cap,'exit':0,'state':'completed','cleanup_confirmed':True,
                          'elapsed_seconds':4.66,'output_bytes':len(raw.encode())}
        return operation,summary,execute
    def test_actual_hosted_command_binding_retains_completed_pass_or_failure_before_later_work(self):
        for exit_code in (0,65):
            operation,summary,executor=self.hosted_fixture(exit_code)
            with patch('watch_process.execute',side_effect=executor) as execute:value=route.retain_hosted(DEVICE,exit_code,self.phase_start)
            self.assertEqual(execute.call_count,1)
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
                with self.assertRaises(ValueError):route.retain_hosted(DEVICE,0,self.phase_start)
                execute.assert_not_called()
    def test_hosted_summary_mismatch_retains_raw_bytes_but_cannot_qualify(self):
        for change in [{'totalTestCount':29},{'skippedTests':1},{'runtimeWarnings':['warning']},
                       {'devicesAndConfigurations':[{'device':{'deviceId':'wrong'}}]}, {'result':'Failed'}]:
            operation,summary,executor=self.hosted_fixture();summary.update(change)
            with patch('watch_process.execute',side_effect=executor),patch('owned_process_barrier.mark_unconfirmed'):
                with self.assertRaises(ValueError):route.retain_hosted(DEVICE,0,self.phase_start)
            self.assertEqual(json.loads(Path('build/iOSUnitResults-summary.json').read_text()),summary)
    def test_first_readers_only_get30_and_all_full_reserves_use_original_phase_start(self):
        rows=[('iphone_pro','iOSUnitResults.xcresult',30,900),
              ('iphone_pro','PhoneUIResults.xcresult',10,1200),
              ('iphone_pro','PhoneUIResults-files.xcresult',10,1200),
              ('iphone_pro','PhoneUIResults-imports.xcresult',10,1200),
              ('iphone_se3','CompactPhoneUIResults.xcresult',30,1320),
              ('iphone_se3','CompactPhoneUIResults-files.xcresult',10,1320),
              ('iphone_se3','CompactPhoneUIResults-imports.xcresult',10,1320),
              ('ipad_pro','PadUIResults-layout.xcresult',30,1080),
              ('ipad_pro','PadUIResults-files.xcresult',10,1080),
              ('ipad_pro','PadUIResults.xcresult',10,1080)]
        for scope,result,cap,seconds in rows:
            with self.subTest(scope=scope,result=result):
                started=1000.;required=cap+2+20;deadline=started+seconds
                admission=route.summary_admission(scope,result,started,deadline-required)
                self.assertEqual(admission['phase_started_monotonic'],started)
                self.assertEqual(admission['phase_deadline_monotonic'],deadline)
                self.assertEqual(admission['required_seconds'],required)
                self.assertEqual(admission['summary_seconds'],cap)
                with self.assertRaises(ValueError):route.summary_admission(scope,result,started,deadline-required+.001)
                # A reader-local start would admit this exhausted original stage.
                with self.assertRaises(ValueError):route.summary_admission(scope,result,started,deadline-1)
        for scope,result,start,now in [('ipad_mini','MiniUIResults-warmup.xcresult',1000,1001),
            ('iphone_pro','CompactPhoneUIResults.xcresult',1000,1001),('ipad_pro','PadUIResults-other.xcresult',1000,1001),
            ('iphone_pro','iOSUnitResults.xcresult',True,1001),('iphone_pro','iOSUnitResults.xcresult',float('nan'),1001),
            ('iphone_pro','iOSUnitResults.xcresult',1002,1001),('iphone_pro','iOSUnitResults.xcresult',0,1001),
            ('iphone_pro','iOSUnitResults.xcresult',1000,float('inf'))]:
            with self.subTest(scope=scope,result=result,start=start,now=now),self.assertRaises(ValueError):
                route.summary_admission(scope,result,start,now)
    def test_hosted_uses_old_phase_clock_and_rechecks_full_reserve_before_dispatch(self):
        for clocks in ([2000.], [2000.,2049.]):
            operation,summary,executor=self.hosted_fixture()
            start=1149. if len(clocks)==1 else 1200.
            with patch('watch_process.execute') as execute,patch('owned_process_barrier.mark_unconfirmed'):
                with patch.object(route.time,'monotonic',side_effect=clocks):
                    with self.assertRaises(ValueError):route.retain_hosted(DEVICE,0,start)
                execute.assert_not_called()
            self.assertTrue(Path('build/iOSUnitResults-command.json').exists())
            self.assertFalse(Path('build/iOSUnitResults-summary.json').exists())
    def test_hosted_summary_wrong_late_unclean_or_old_timeout_retains_raw_without_retry(self):
        changes=[{'timeout_seconds':10},{'elapsed_seconds':32},{'cleanup_confirmed':False},{'state':'unknown'},
                 {'state':'timed_out','exit':124,'elapsed_seconds':10.05,'timeout_seconds':10}]
        for change in changes:
            operation,summary,executor=self.hosted_fixture()
            def altered(command,cap,**kwargs):
                code,raw,receipt=executor(command,cap,**kwargs);receipt.update(change)
                return receipt['exit'],raw,receipt
            with self.subTest(change=change),patch('watch_process.execute',side_effect=altered) as execute,patch('owned_process_barrier.mark_unconfirmed'):
                with self.assertRaises(ValueError):route.retain_hosted(DEVICE,0,self.phase_start)
                self.assertEqual(execute.call_count,1)
            self.assertEqual(json.loads(Path('build/iOSUnitResults-summary.json').read_text()),summary)
            self.assertEqual(json.loads(Path('build/iOSUnitResults-summary-command.json').read_text())['timeout_seconds'],change.get('timeout_seconds',30))
    def test_hosted_observed_late_return_or_borrowed_cleanup_tail_cannot_qualify_receipt(self):
        for clocks in ([2000.,2000.,2000.,2032.], [2000.,2000.,2000.,2031.,2033.]):
            operation,summary,executor=self.hosted_fixture()
            with self.subTest(clocks=clocks),patch('watch_process.execute',side_effect=executor) as execute,patch('owned_process_barrier.mark_unconfirmed'):
                with patch.object(route.time,'monotonic',side_effect=clocks):
                    with self.assertRaises(ValueError):route.retain_hosted(DEVICE,0,1152.)
                self.assertEqual(execute.call_count,1)
            self.assertEqual(json.loads(Path('build/iOSUnitResults-summary.json').read_text()),summary)
    def test_hosted_summary_retry_or_wrong_selected_device_never_dispatches(self):
        operation,summary,executor=self.hosted_fixture()
        with patch('watch_process.execute',side_effect=executor):route.retain_hosted(DEVICE,0,self.phase_start)
        with patch('watch_process.execute') as execute,patch('owned_process_barrier.mark_unconfirmed'):
            with self.assertRaises(ValueError):route.retain_hosted(DEVICE,0,time.monotonic())
            execute.assert_not_called()
        self.hosted_fixture()
        with patch.dict(os.environ,{'SIMULATOR_ID':'11111111-2222-4333-8444-555555555555'}),patch('watch_process.execute') as execute:
            with self.assertRaises(ValueError):route.retain_hosted(DEVICE,0,self.phase_start)
            execute.assert_not_called()
    def test_final_reporting_reads_exact_fixed_bounded_files_without_any_reader_call_or_case_qualification(self):
        profiles={'iphone_pro':['iOSUnitResults','PhoneUIResults','PhoneUIResults-files','PhoneUIResults-imports'],
                  'iphone_se3':['CompactPhoneUIResults','CompactPhoneUIResults-files','CompactPhoneUIResults-imports'],
                  'ipad_pro':['PadUIResults-layout','PadUIResults-files','PadUIResults']}
        from ios_import_continuation import read_regular
        for scope,stems in profiles.items():
            for path in Path('build').glob('*'):path.unlink()
            raw='{"result":"Passed","totalTestCount":999}\n' # Raw text never becomes a case pass.
            for stem in stems:
                Path('build',stem+'-summary.json').write_text(raw)
                command=['xcrun','xcresulttool','get','test-results','summary','--path',stem+'.xcresult']
                cap=30 if stem in ('iOSUnitResults','CompactPhoneUIResults','PadUIResults-layout') else 10
                Path('build',stem+'-summary-command.json').write_text(json.dumps({'command':command,'timeout_seconds':cap,
                    'exit':0,'state':'completed','cleanup_confirmed':True,'elapsed_seconds':1,'output_bytes':len(raw.encode())}))
            Path('build/Unselected-summary.json').write_text('must not read this')
            before={str(path):path.read_bytes() for path in Path('build').glob('*')};output=io.StringIO()
            with self.subTest(scope=scope),patch.dict(os.environ,{'EVIDENCE_SCOPE':scope}),patch('watch_process.execute') as execute,patch.object(original,'execute') as old_execute,patch('ios_import_continuation.read_regular',wraps=read_regular) as reader,contextlib.redirect_stdout(output):
                reports=route.report_retained_summaries()
            execute.assert_not_called();old_execute.assert_not_called()
            self.assertEqual([item['result'] for item in reports],[stem+'.xcresult' for stem in stems])
            self.assertTrue(all(item['state']=='retained_raw_not_requalified' and item['acceptance'] is False for item in reports))
            self.assertTrue(all('counts' not in item and 'native_outcome' not in item for item in reports))
            self.assertEqual([(str(call.args[0]),call.args[1]) for call in reader.call_args_list],
                [(str(Path('build')/(stem+suffix)),cap) for stem in stems for suffix,cap in [('-summary.json',65536),('-summary-command.json',16384)]])
            self.assertEqual(output.getvalue().count(raw),len(stems));self.assertNotIn('must not read this',output.getvalue())
            self.assertEqual({str(path):path.read_bytes() for path in Path('build').glob('*')},before)
    def test_final_reporting_labels_old_timeout_raw_and_missing_evidence_without_postqualification(self):
        stem='CompactPhoneUIResults';raw='{"result":"Failed","totalTestCount":2,"passedTests":1,"failedTests":1}'
        Path('build',stem+'-summary.json').write_text(raw)
        Path('build',stem+'-summary-command.json').write_text(json.dumps({'command':['xcrun','xcresulttool','get','test-results','summary','--path',stem+'.xcresult'],
            'timeout_seconds':10,'exit':124,'state':'timed_out','cleanup_confirmed':True,'elapsed_seconds':10.05,'output_bytes':len(raw.encode())}))
        before={str(path):path.read_bytes() for path in Path('build').glob('*')};output=io.StringIO()
        with patch.dict(os.environ,{'EVIDENCE_SCOPE':'iphone_se3'}),patch('watch_process.execute') as execute,contextlib.redirect_stdout(output):
            reports=route.report_retained_summaries()
        execute.assert_not_called()
        self.assertEqual(reports[0]['state'],'unqualified_retained_raw');self.assertEqual(reports[0]['reader_receipt'],'unqualified')
        self.assertTrue(all(item['acceptance'] is False for item in reports))
        self.assertEqual([item['state'] for item in reports[1:]],['missing','missing'])
        self.assertIn(raw,output.getvalue())
        self.assertEqual({str(path):path.read_bytes() for path in Path('build').glob('*')},before)
    def test_final_reporting_refuses_wrong_source_checkout_or_scope_before_any_reader(self):
        changes=[{'GITHUB_WORKFLOW_SHA':'b'*40},{'GITHUB_REF':original.REF},{'GITHUB_WORKFLOW_REF':original.WORKFLOW_REF},
                 {'GITHUB_WORKSPACE':str(self.root/'build')},{'EVIDENCE_SCOPE':'ipad_mini'},
                 {'GITHUB_JOB':'preflight','EVIDENCE_SCOPE':''}]
        for change in changes:
            with self.subTest(change=change),patch.dict(os.environ,change),patch('watch_process.execute') as execute,patch('ios_import_continuation.read_regular') as reader,contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(ValueError):route.report_retained_summaries()
                execute.assert_not_called();reader.assert_not_called();self.assertEqual(output.getvalue(),'')
    def test_final_reporting_never_reads_unbounded_redirected_or_shared_summary_bytes(self):
        path=Path('build/iOSUnitResults-summary.json')
        for kind in ('oversized','symlink','hardlink'):
            path.unlink(missing_ok=True);target=Path('foreign-summary.json');target.unlink(missing_ok=True)
            if kind=='oversized':path.write_text('sensitive raw overflow'+('x'*65536))
            elif kind=='symlink':target.write_text('sensitive redirected raw');path.symlink_to(target.resolve())
            else:target.write_text('sensitive shared raw');os.link(target,path)
            with self.subTest(kind=kind),patch('watch_process.execute') as execute,contextlib.redirect_stdout(io.StringIO()) as output:
                reports=route.report_retained_summaries()
            execute.assert_not_called();self.assertEqual(reports[0]['state'],'unqualified_unreadable')
            self.assertNotIn('sensitive',output.getvalue())

class ProductClosureTests(unittest.TestCase):
    def test_debug_observation_preserves_original_shipping_controller_and_consumers_bound(self):
        project=ROOT/'QRCatcher-iOS-Only.xcodeproj/project.pbxproj'
        objects=parse_project(project)['objects'];targets={v['name']:v for v in objects.values() if v.get('isa')=='PBXNativeTarget'}
        app=paths_in_phase(objects,targets['QRCatcher'],'PBXSourcesBuildPhase')
        self.assertIn('QRCatcher/QRPrivacyViewController.m',app)
        self.assertNotIn('QRCatcherTests/QRCatcherTests.m',app);self.assertNotIn('QRCatcherUITests/QRCatcherUITests.m',app)
        from test_ios_offline_privacy import restore_privacy_policy_parent, release_preprocessed
        source=(ROOT/'QRCatcher/QRPrivacyViewController.m').read_text()
        parent=restore_privacy_policy_parent(source)
        self.assertEqual(hashlib.sha256(parent.encode()).hexdigest(),
                         '4303215922f7e1a72a1c535eb3d757d785601d296b54034717de7046936a1fe3')
        self.assertEqual(release_preprocessed(source),release_preprocessed(parent))

if __name__=='__main__':unittest.main()
