#!/usr/bin/env python3
"""Source/clock/ownership doubles and real host-prepare integration; no native run.

This is newly authored recovery coverage. The lost historical 37-test file is
not reproduced or represented by this source identity.
"""
from pathlib import Path
import ast,contextlib,copy,fnmatch,hashlib,json,os,plistlib,re,shutil,subprocess,sys,tempfile,time,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import ipad_mini_setup as mini
import owned_process_barrier as barrier
from atomic_json import write_json
from fixture_query_guard import query_guard
SHA='a'*40
DEVICE='ABCDEF12-3456-4789-ABCD-EF0123456789'
RUNTIME='com.apple.CoreSimulator.SimRuntime.iOS-27-0'
TYPE='com.apple.CoreSimulator.SimDeviceType.iPad-mini-A17-Pro'
UNITS=('test_ios_launcher.py','test_watch_process.py','test_required_reason_symbols.py','test_atomic_json.py','test_vision_ui_cases.py','test_embedded_watch_gate.py')


def preflight_contract(text,names=None):
    """Check existing same-workflow dependency/default-success/import semantics.

    This is a source regression fence, not a fabricated runtime receipt.
    GitHub's needs success dependency is the actual admission mechanism.
    """
    def require(value,message):
        if not value:raise ValueError(message)
    match=re.search(r'^  preflight:\n(.*?)^  platform:\n(.*?)^    steps:\n',text,re.M|re.S)
    require(match is not None,'Exact preflight/platform jobs required')
    preflight,platform=match.groups()
    require(platform.count('    needs: preflight\n')==1,'Successful same-workflow preflight dependency required')
    require(re.search(r'^    (if|continue-on-error):',platform,re.M) is None,'Platform must retain default needs-success admission')
    require('continue-on-error:' not in preflight,'Preflight failure cannot be bypassed')
    discovery="        python3 -m unittest discover -s Tests/Harness -p 'test_*.py' -v\n"
    require(preflight.count(discovery)==1,'Original complete discovery command must execute once')
    require('set -euo pipefail' in preflight,'Discovery failure must fail the preflight job')
    for gate in ['test "$GITHUB_WORKFLOW_SHA" = "$GITHUB_SHA"','test "$(git rev-parse HEAD)" = "$GITHUB_SHA"','git diff --exit-code HEAD --','ref: ${{ github.sha }}']:
        require(gate in preflight,'Exact current-head/source gate missing')
    files=set(names if names is not None else (p.name for p in (ROOT/'Tests/Harness').glob('test_*.py')))
    require(all(name in files and fnmatch.fnmatchcase(name,'test_*.py') for name in UNITS),'Required module absent from discovery imports')
    for name in UNITS:
        tree=ast.parse((ROOT/'Tests/Harness'/name).read_text())
        require(not any(isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name=='load_tests' for node in ast.walk(tree)),'Required unit import coverage cannot be overridden')
        if name!='test_ios_launcher.py':
            require(any(isinstance(node,ast.ClassDef) and any(isinstance(base,ast.Attribute) and isinstance(base.value,ast.Name) and base.value.id=='unittest' and base.attr=='TestCase' for base in node.bases) for node in tree.body),'Required unit TestCases missing')
        else:
            require('SHELL_ARGUMENT_ROUTING_PASS' in (ROOT/'Tests/Harness'/name).read_text(),'Original top-level launcher import scenarios missing')
    return True

class Clock:
    def __init__(self,now=.1):self.now=now
    def __call__(self):return self.now

class Fixture:
    def __init__(self,now=.1):
        self.tmp=tempfile.TemporaryDirectory(prefix='qr-mini-source-unit-')
        self.root=Path(self.tmp.name).resolve();(self.root/'build').mkdir();self.temp=self.root/'temp';self.temp.mkdir()
        self.clock=Clock(now);self.cwd=Path.cwd();self.environment=dict(os.environ)
        os.chdir(self.root)
        for key in ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED','MINI_SIMULATOR_ID']:os.environ.pop(key,None)
        os.environ.update(GITHUB_WORKSPACE=str(self.root),GITHUB_SHA=SHA,GITHUB_WORKFLOW_SHA=SHA,
            GITHUB_REPOSITORY='100mango/QRCatcher',GITHUB_REF='refs/heads/codex/apple-platforms',
            GITHUB_EVENT_NAME='push',EVIDENCE_SCOPE='ipad_mini',GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',
            RUNNER_TEMP=str(self.temp),GITHUB_ENV=str(self.root/'env'),GITHUB_OUTPUT=str(self.root/'output'),
            QRCATCHER_OWNED_PROCESS_BARRIER=str(self.root/'build/owned-process-cleanup.json'))
        self.origin=self.temp/'qrcatcher-mini-123-1.json';os.environ['QRCATCHER_MINI_JOB_ORIGIN']=str(self.origin)
        self.origin_value={'version':1,'source':SHA,'workflow_sha':SHA,'run_id':'123','run_attempt':'1','scope':'ipad_mini',
                           'caps':mini.CAPS,'started_monotonic':now}
        write_json(self.origin,self.origin_value,limit=2048)
        self.budget=mini.Budget(self.clock)
        for phase in ['prepare','build']:
            self.budget.enter(phase);self.budget.state['phases'][phase]['status']='completed';self.budget.persist()
        self.calls=[];self.file_exit=0;self.layout_exit=0;self.photo_exit=0;self.seed_exit=0
        self.summary_edit=None;self.operation_edit=None;self.after_command=None;self.inventory_edit=None;self.readback_edit=None
        self.created=DEVICE
    def close(self):
        mini._ACTIVE=None;mini._ROW_LEASE=None;mini._FIXTURE=None
        os.chdir(self.cwd);os.environ.clear();os.environ.update(self.environment);self.tmp.cleanup()
    def executor(self,command,cap,**kwargs):
        self.calls.append((command,cap));self.clock.now+=.01;code=0
        if command==['xcrun','simctl','list','-j']:
            value={'runtimes':[{'identifier':RUNTIME,'isAvailable':True}],
                   'devicetypes':[{'name':'iPad mini (A17 Pro)','identifier':TYPE}], 'devices':{RUNTIME:[]}}
            if self.inventory_edit:self.inventory_edit(value)
            raw=json.dumps(value)
        elif command[:3]==['xcrun','simctl','create']:raw=self.created+'\n'
        elif command==['xcrun','simctl','list','devices','available','-j']:
            value={'devices':{RUNTIME:[{'udid':self.created,'name':'QRCatcher Mini 123-1','deviceTypeIdentifier':TYPE,
                           'isAvailable':True,'state':'Shutdown'}]}}
            if self.readback_edit:self.readback_edit(value)
            raw=json.dumps(value)
        elif command[:3]==['xcrun','xcresulttool','get']:
            result=command[-1];expected=2 if '-layout.' in result else 1
            exit_code=self.layout_exit if '-layout.' in result else self.file_exit if '-files.' in result else self.photo_exit
            value={'totalTestCount':expected,'passedTests':expected if not exit_code else expected-1,
                   'failedTests':int(bool(exit_code)),'skippedTests':0,'expectedFailures':0,
                   'devicesAndConfigurations':[{'device':{'deviceId':DEVICE}}],'runtimeWarnings':[],
                   'result':'Failed' if exit_code else 'Passed','testFailures':[{'failureText':'Synthetic complete failure'}] if exit_code else []}
            if self.summary_edit:self.summary_edit(value,result)
            raw=json.dumps(value)
        elif command[:3]==['xcrun','simctl','addmedia']:code=self.seed_exit;raw='Synthetic returned seed command only'
        elif command[:2]==['xcodebuild','test-without-building']:
            result=command[-1];code=self.layout_exit if '-layout.' in result else self.file_exit if '-files.' in result else self.photo_exit
            raw='Synthetic Xcode command, no app or provider execution'
        else:raise AssertionError(command)
        operation={'state':'completed','exit':code,'cleanup_confirmed':True,'elapsed_seconds':.01}
        if self.operation_edit:self.operation_edit(operation,command)
        if self.after_command:self.after_command(command)
        return code,raw,operation
    def configure(self):
        receipt=mini.configure(self.budget,self.executor);os.environ['MINI_SIMULATOR_ID']=receipt['device'];return receipt
    def stage(self,device):
        for kind in ['app','data']:
            with query_guard(['xcrun','simctl','get_app_container',device,'100mango.QRCatcher',kind]):self.clock.now+=.01
    def row(self,stager=None):
        return mini.row([DEVICE,'MiniUIResults.xcresult','QRCatcherPadUITests'],self.budget,self.executor,stager or self.stage)
    def setup(self):return json.loads((self.root/'build/ios-platform-setup.json').read_text())

class MiniSetupTests(unittest.TestCase):
    def setUp(self):self.f=Fixture()
    def tearDown(self):self.f.close()
    def test_small_nonzero_parent_clock_accepts_owned_full_row(self):
        self.f.configure();self.assertEqual(self.f.row(),0)
        self.assertEqual(self.f.setup()['unexecuted'],[]);self.assertFalse(self.f.setup()['full_job_accepted'])
        self.assertEqual(sum(mini.CAPS.values()),2700)
    def test_zero_negative_future_origins_refused(self):
        for origin in [0,-1,2,float('inf')]:
            with self.subTest(origin=origin):
                value=copy.deepcopy(self.f.origin_value);value['started_monotonic']=origin
                self.f.origin.write_text(json.dumps(value));self.f.origin.chmod(0o600)
                with self.assertRaises(ValueError):mini.Budget(self.f.clock)
    def test_reset_origin_refused(self):
        self.f.clock.now=1;value=copy.deepcopy(self.f.origin_value);value['started_monotonic']=.2
        write_json(self.f.origin,value,limit=2048)
        with self.assertRaises(ValueError):mini.Budget(self.f.clock)
    def test_stale_run_receipt_refused(self):
        self.f.configure();path=self.f.root/'build/ipad-mini-owned-device.json';value=json.loads(path.read_text());value['run_id']='124';write_json(path,value,limit=4096)
        count=len(self.f.calls)
        with self.assertRaises(ValueError):self.f.row()
        self.assertEqual(len(self.f.calls),count)
    def test_reset_row_deadline_refused(self):
        self.f.configure();path=self.f.root/'build/ipad-mini-owned-device.json';value=json.loads(path.read_text());value['row_deadline_monotonic']+=1;write_json(path,value,limit=4096)
        with self.assertRaises(ValueError):self.f.row()
    def test_extended_phase_ledger_refused(self):
        self.f.budget.state['phases']['build']['deadline']+=1;self.f.budget.persist()
        with self.assertRaises(ValueError):mini.Budget(self.f.clock)
    def test_poisoned_workspace_alias_refused(self):
        alias=self.f.root/'alias';alias.symlink_to(self.f.root,target_is_directory=True);os.environ['GITHUB_WORKSPACE']=str(alias)
        with self.assertRaises(ValueError):mini.Budget(self.f.clock)
    def test_poisoned_barrier_path_refused(self):
        os.environ['QRCATCHER_OWNED_PROCESS_BARRIER']=str(self.f.root/'foreign.json')
        with self.assertRaises(ValueError):mini.Budget(self.f.clock)
    def test_true_inherited_uncertainty_before_configuration(self):
        os.environ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED']='true'
        with self.assertRaises(ValueError):self.f.configure()
        self.assertEqual(self.f.calls,[])
    def test_real_inherited_barrier_before_configuration(self):
        (self.f.root/'build/owned-process-cleanup.json').write_text('{}')
        with self.assertRaises(ValueError):self.f.configure()
        self.assertEqual(self.f.calls,[])
    def test_host_marker_blocks_unclaimed_execute(self):
        (self.f.root/'build/ipad-mini-host-inflight.json').write_text('{}')
        self.assertTrue(barrier.blocked());self.assertTrue(barrier.blocked(['true']))
    def test_exact_480_plus_20_window_admitted(self):
        self.f.configure();deadline=self.f.budget.state['phases']['mini']['deadline'];self.f.clock.now=deadline-500
        mini.Controller(self.f.budget,'mini',deadline,self.f.executor).command(['xcodebuild','test-without-building','MiniUIResults-layout.xcresult'],480)
        self.assertEqual(self.f.calls[-1][1],480)
    def test_missing_full_next_command_cleanup_refused_before_launch(self):
        self.f.configure();self.f.clock.now=self.f.budget.state['phases']['mini']['deadline']-499.99;count=len(self.f.calls)
        with self.assertRaises(ValueError):self.f.row()
        self.assertEqual(len(self.f.calls),count);self.assertEqual(self.f.setup()['unexecuted'],['layout','files','photos'])
    def test_late_photos_refusal_preserves_original_clock_and_seed(self):
        self.f.configure();deadline=self.f.budget.state['phases']['mini']['deadline']
        original_persist=self.f.budget.persist
        def late_persist():
            original_persist()
            if any(item['command'][:3]==['xcrun','simctl','addmedia'] and item.get('state')=='completed' for item in self.f.budget.state['phases']['mini']['operations']):self.f.clock.now=deadline-379
        self.f.budget.persist=late_persist
        with self.assertRaises(ValueError):self.f.row()
        setup=self.f.setup();self.assertEqual(setup['unexecuted'],['photos']);self.assertEqual(setup['seed_attempts'],1)
        self.assertEqual(setup['real_photo_case_exit'],-1);self.assertEqual(setup['row_deadline_monotonic'],deadline)
        self.assertEqual(len([c for c,t in self.f.calls if c[:3]==['xcrun','simctl','addmedia']]),1)
    def test_completed_files_failure_remains_red_with_distinct_photos(self):
        self.f.file_exit=65;self.f.configure();self.assertEqual(self.f.row(),65)
        self.assertEqual(self.f.setup()['real_files_case_exit'],65);self.assertEqual(self.f.setup()['real_photo_case_exit'],0)
        self.assertEqual(self.f.setup()['unexecuted'],[])
    def test_layout_failure_stops_before_fixture_files_seed(self):
        self.f.layout_exit=65;self.f.configure();self.assertEqual(self.f.row(),65)
        self.assertEqual(self.f.setup()['unexecuted'],['files','photos'])
        self.assertFalse(any(c[:3]==['xcrun','simctl','addmedia'] for c,t in self.f.calls))
    def test_permanent_row_marker_refuses_repeat(self):
        self.f.configure();self.f.row();count=len(self.f.calls)
        with self.assertRaises(ValueError):self.f.row()
        self.assertEqual(len(self.f.calls),count);self.assertTrue((self.f.root/'build/ipad-mini-row-dispatched.json').is_file())
    def test_duplicate_type_identifier_refused(self):
        self.f.inventory_edit=lambda v:v['devicetypes'].append(copy.deepcopy(v['devicetypes'][0]))
        with self.assertRaises(ValueError):self.f.configure()
        self.assertEqual(len(self.f.calls),1)
    def test_missing_runtime_refused(self):
        self.f.inventory_edit=lambda v:v.update(runtimes=[])
        with self.assertRaises(ValueError):self.f.configure()
        self.assertEqual(len(self.f.calls),1)
    def test_existing_owned_name_refused(self):
        self.f.inventory_edit=lambda v:v['devices'][RUNTIME].append({'udid':DEVICE,'name':'QRCatcher Mini 123-1'})
        with self.assertRaises(ValueError):self.f.configure()
        self.assertEqual(len(self.f.calls),1)
    def test_preexisting_created_uuid_refused(self):
        self.f.inventory_edit=lambda v:v['devices'][RUNTIME].append({'udid':DEVICE,'name':'Other app'})
        with self.assertRaises(ValueError):self.f.configure()
        self.assertEqual(len(self.f.calls),2)
    def test_lowercase_uuid_refused(self):
        self.f.created=DEVICE.lower()
        with self.assertRaises(ValueError):self.f.configure()
    def test_nonshutdown_or_foreign_readback_refused(self):
        for field,value in [('state','Booted'),('deviceTypeIdentifier','com.apple.CoreSimulator.SimDeviceType.foreign'),('isAvailable',False)]:
            self.f.readback_edit=lambda v,field=field,value=value:v['devices'][RUNTIME][0].update({field:value})
            with self.subTest(field=field),self.assertRaises(ValueError):self.f.configure()
            self.f.budget.state['phases'].pop('mini');self.f.budget.persist()
    def test_configured_receipt_preserves_setup_uncertainty(self):
        value=self.f.configure();self.assertEqual(value['deployment_owner'],'xcodebuild')
        self.assertEqual(value['pretest_boot_completion'],'not_requested');self.assertEqual(value['pretest_installed_bytes'],'not_observed')
        self.assertFalse(any(c[:3] in [['xcrun','simctl','boot'],['xcrun','simctl','install']] for c,t in self.f.calls))
    def test_unconfirmed_cleanup_stops_later_configuration(self):
        self.f.operation_edit=lambda v,c:v.update(cleanup_confirmed=False)
        with self.assertRaises(ValueError):self.f.configure()
        self.assertEqual(len(self.f.calls),1);self.assertTrue(barrier.blocked())
    def test_late_create_stops_before_readback(self):
        self.f.after_command=lambda c:setattr(self.f.clock,'now',self.f.clock.now+63) if c[:3]==['xcrun','simctl','create'] else None
        with self.assertRaises(ValueError):self.f.configure()
        self.assertEqual(len(self.f.calls),2);self.assertTrue(barrier.blocked())
    def test_removed_latch_is_uncertainty(self):
        self.f.after_command=lambda c:(self.f.root/'build/ipad-mini-inflight.json').unlink()
        with self.assertRaises((ValueError,OSError)):self.f.configure()
        self.assertTrue(barrier.blocked());self.assertEqual(len(self.f.calls),1)
    def test_origin_change_after_read_refused(self):
        value=copy.deepcopy(self.f.origin_value);value['started_monotonic']=.09;write_json(self.f.origin,value,limit=2048)
        with self.assertRaises(ValueError):self.f.budget.current()
    def test_separate_checkout_post_debit_and_full_job_unknown(self):
        self.assertEqual(mini.CAPS['checkout_post'],60);self.assertEqual(sum(mini.CAPS.values()),2700)
        self.assertFalse(self.f.budget.state['full_job_accepted'])
        self.assertEqual(self.f.budget.state['post_checkout'],{'owner':'actions-runner','separate_limit_seconds':60,'status':'pending_platform_post_action'})
        self.f.clock.now=self.f.budget.deadline-119.99
        with self.assertRaises(ValueError):self.f.budget.enter('final')
    def test_whole_future_phase_budget_refused(self):
        self.f.clock.now=self.f.budget.deadline-1700
        with self.assertRaises(ValueError):self.f.configure()
        self.assertEqual(self.f.calls,[])
    def test_fixed_full_row_identity_and_extra_args_refused(self):
        self.f.configure()
        for args in [[DEVICE,'MiniUIResults.xcresult','QRCatcherPadUITests','extra'],[DEVICE,'Files.xcresult','QRCatcherImageImportUITests']]:
            with self.subTest(args=args),self.assertRaises(ValueError):mini.row(args,self.f.budget,self.f.executor,self.f.stage)
        for args in [['row'],['phase','embedding'],['configure','extra'],['generic','true']]:
            with self.subTest(args=args),self.assertRaises(ValueError):mini.main(args)
    def test_original_selectors_caps_and_all_four_case_counts(self):
        self.f.configure();self.f.row();calls=[(c,t) for c,t in self.f.calls if c[:2]==['xcodebuild','test-without-building']]
        self.assertEqual([cap for c,cap in calls],[480,240,360]);self.assertEqual(len(calls),3)
        for (command,cap),selectors in zip(calls,[mini.LAYOUT,mini.FILES,mini.PHOTOS]):
            for selector in selectors:self.assertIn(selector,command)
            self.assertIn('180',command);self.assertIn('240',command);self.assertIn('NO',command)
        results=self.f.budget.state['phases']['mini']['results'];self.assertEqual(sum(v['totalTestCount'] for v in results.values()),4)
        self.assertEqual([t for c,t in self.f.calls if c[:3]==['xcrun','simctl','addmedia']],[210])
        self.assertEqual([t for c,t in self.f.calls if c[:3]==['xcrun','xcresulttool','get']],[10,10,10])
    def test_zero_case_summary_stops_before_fixture_seed(self):
        self.f.summary_edit=lambda v,r:v.update(totalTestCount=0,passedTests=0) if '-layout.' in r else None
        self.f.configure()
        with self.assertRaises(ValueError):self.f.row()
        self.assertFalse(any(c[:3]==['xcrun','simctl','addmedia'] for c,t in self.f.calls))
    def test_foreign_destination_summary_stops_before_seed(self):
        self.f.summary_edit=lambda v,r:v['devicesAndConfigurations'][0]['device'].update(deviceId='11111111-2222-4333-8444-555555555555')
        self.f.configure()
        with self.assertRaises(ValueError):self.f.row()
        self.assertFalse(any(c[:3]==['xcrun','simctl','addmedia'] for c,t in self.f.calls))
    def test_skipped_or_warning_result_refused(self):
        self.f.configure()
        self.f.summary_edit=lambda v,r:v.update(runtimeWarnings=['Synthetic warning'])
        with self.assertRaises(ValueError):self.f.row()
    def test_stale_result_directory_refused_before_launch(self):
        self.f.configure();(self.f.root/'MiniUIResults-files.xcresult').mkdir();count=len(self.f.calls)
        with self.assertRaises(ValueError):self.f.row()
        self.assertEqual(len(self.f.calls),count)
    def test_fixture_queries_exact_sequence_only(self):
        self.f.configure()
        def wrong(device):
            with query_guard(['xcrun','simctl','get_app_container',device,'100mango.QRCatcher','data']):pass
        with self.assertRaises(ValueError):self.f.row(wrong)
        self.assertFalse(any(c[:3]==['xcrun','simctl','addmedia'] for c,t in self.f.calls))
    def test_fixture_incomplete_queries_refused(self):
        self.f.configure()
        with self.assertRaises(ValueError):self.f.row(lambda device:None)
        self.assertFalse(any(c[:3]==['xcrun','simctl','addmedia'] for c,t in self.f.calls))
    def test_replaced_build_symlink_before_claim_no_foreign_write(self):
        foreign=self.f.root/'foreign';foreign.mkdir();(self.f.root/'build').rename(self.f.root/'original-build');(self.f.root/'build').symlink_to(foreign,target_is_directory=True)
        with self.assertRaises(ValueError):mini.Claim(self.f.budget,['true'],'mini')
        self.assertEqual(list(foreign.iterdir()),[])
    def test_claim_identity_changed_refuses_dispatch(self):
        deadline=self.f.budget.enter('mini');claim=mini.Claim(self.f.budget,['true'],'mini');mini._ACTIVE=claim
        try:
            claim.path.write_text('{}');self.assertFalse(mini.active_claim_is_current(['true']))
        finally:claim.close(False)
    def test_production_prepare_only_removes_six_redundant_unit_calls(self):
        body=(ROOT/'scripts/ipad_mini_prepare.sh').read_text();fixed=''.join('python3 Tests/Harness/'+name+'\n' for name in UNITS)
        # Normalize only the explicitly reviewed iOS-first metadata/project
        # clauses. The original canonical restoration hash stays unchanged.
        staged='if [ "$GITHUB_REF" = refs/heads/codex/ios-original-release ]; then\n  python3 scripts/ios_original_release_route.py prepared "$SOURCE_HEAD" "$SOURCE_TREE"\nfi\n'
        generate='if [ "$GITHUB_REF" = refs/heads/codex/ios-original-release ]; then\n  python3 scripts/generate_project.py --profile ios-only\n  git diff --exit-code -- QRCatcher.xcodeproj QRCatcher-iOS-Only.xcodeproj\nelse\n  python3 scripts/generate_project.py\n  git diff --exit-code -- QRCatcher.xcodeproj\nfi\n'
        listing='if [ "$GITHUB_REF" = refs/heads/codex/ios-original-release ]; then\n  xcodebuild -list -project QRCatcher-iOS-Only.xcodeproj\nelse\n  xcodebuild -list -project QRCatcher.xcodeproj\nfi\n'
        for clause in (staged,generate,listing):self.assertEqual(body.count(clause),1)
        body=body.replace(staged,'',1).replace(generate,'python3 scripts/generate_project.py\ngit diff --exit-code -- QRCatcher.xcodeproj\n',1).replace(listing,'xcodebuild -list -project QRCatcher.xcodeproj\n',1)
        if (ROOT/'scripts/diagnostic_mini_managed_route.py').is_file():
            ref_new='python3 scripts/ipad_mini_setup.py source-identity\n';ref_old='test "$GITHUB_REF" = refs/heads/codex/apple-platforms\n'
            head_new='SOURCE_HEAD=$(git rev-parse HEAD)\necho "Tested commit: $SOURCE_HEAD"\nSOURCE_TREE=$(git rev-parse \'HEAD^{tree}\')\necho "Tested tree: $SOURCE_TREE"\nif [ "$GITHUB_REF" = refs/heads/codex/mini-managed-full-row ]; then\n  python3 scripts/diagnostic_mini_managed_route.py prepared "$SOURCE_HEAD" "$SOURCE_TREE"\nfi\n';head_old='echo "Tested commit: $(git rev-parse HEAD)"\necho "Tested tree: $(git rev-parse \'HEAD^{tree}\')"\n'
            self.assertEqual(body.count(ref_new),1);self.assertEqual(body.count(head_new),1)
            body=body.replace(ref_new,ref_old,1).replace(head_new,head_old,1)
        anchor='test "$(uname -m)" = arm64\n'
        self.assertEqual(body.count(anchor),1)
        self.assertFalse(any('Tests/Harness/'+name in body for name in UNITS))
        restored=body.replace(anchor,anchor+fixed,1)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),'b39e1b91d593b65d7d7fc25beee0646a89d439efc5ceb50bfd875c47058528e4')
    def test_nonmini_selector_and_launcher_body_byte_equivalence(self):
        selector=(ROOT/'scripts/select_ios_platform_matrix.py').read_text().replace("if os.environ.get('EVIDENCE_SCOPE') == 'ipad_mini':\n from ipad_mini_setup import configure\n configure()\n raise SystemExit(0)\n",'',1)
        launcher=(ROOT/'scripts/run_ios_platform_ui.sh').read_text().replace("if [ \"${EVIDENCE_SCOPE:-}\" = ipad_mini ] || [ \"${2:-}\" = MiniUIResults.xcresult ]; then\n  python3 -u scripts/ipad_mini_setup.py row \"$@\"\n  exit $?\nfi\n",'',1)
        staged='PROJECT=QRCatcher.xcodeproj\nif [ "${GITHUB_REF:-}" = refs/heads/codex/ios-original-release ]; then\n  PROJECT=$(python3 scripts/ios_original_release_route.py project)\nfi\n'
        self.assertEqual(launcher.count(staged),1);self.assertEqual(launcher.count('-project "$PROJECT"'),1)
        launcher=launcher.replace(staged,'',1).replace('-project "$PROJECT"','-project QRCatcher.xcodeproj',1)
        self.assertEqual(hashlib.sha256(selector.encode()).hexdigest(),'950f7f4d3171a980fcdb2de4e6229c530088c0ed0b86a40aaf3ef4e3ec777dd2')
        self.assertEqual(hashlib.sha256(launcher.encode()).hexdigest(),'c39047fa5a26a101422f11ec954b2a30073e40937cf2c37018175890cf5df7e6')
    def test_exact_known_workflow_and_schedule(self):
        body=(ROOT/'.github/workflows/apple-platforms.yml').read_bytes()
        self.assertEqual(len(body),34550);self.assertEqual(hashlib.sha256(body).hexdigest(),'1c3b0759c211b54ec30bd8d19cac9e7a4f03b77dea94ae81146910f10ff202d4')
        text=body.decode();self.assertIn('timeout-minutes: 45',text);self.assertIn('timeout-minutes: 27',text)
        self.assertLess(text.index('Capture original Mini job clock before checkout'),text.index('Checkout Mini exact source'))
        self.assertIn("'checkout_post':60",text);self.assertIn('compile_platform_preflight.py',text)
    def test_persistence_consuming_next_whole_window_refused_before_dispatch(self):
        self.f.configure();deadline=self.f.budget.state['phases']['mini']['deadline'];self.f.clock.now=deadline-500
        original=self.f.budget.persist
        def consume():original();self.f.clock.now+=.01
        self.f.budget.persist=consume;count=len(self.f.calls)
        with self.assertRaises(ValueError):mini.Controller(self.f.budget,'mini',deadline,self.f.executor).command(['xcodebuild','test-without-building','MiniUIResults-layout.xcresult'],480)
        self.assertEqual(len(self.f.calls),count);self.assertTrue(barrier.blocked())
    def test_original_products_native_cases_fixtures_and_process_caps_unchanged(self):
        protected={'QRCatcherUITests/QRCatcherImageImportUITests.m': 'a549e2360cc1245166f8bdbe568a557b05afa09a44f0b9d406720074614d81d5', 'QRCatcherUITests/QRCatcherPadUITests.m': 'ec3d7211c2b844af6d8320d081847990b960fe5f4af02a83db88bd552c562edf', 'QRCatcherUITests/QRCatcherUITests.m': 'e29e743721b4a539550cd1d563b0ec1834a368b1f2056cbc9a4c307202202648', 'scripts/stage_owned_import_fixture.py': '44d6f5b937b367b7490b1b7a0cec5befd96d3bf6f6b868f5fa5134784fa02564', 'scripts/owned_process_group.py': 'eb406d2fe4c928d6438875761d596e3415ab9330593fd1b5a678ae6f99cb535e', 'scripts/watch_process.py': '607cabe0a86031e1e895422ae16c85c59efd4cee14171feef2a11509844f79a3', 'scripts/ios_import_continuation.py': 'bb764b4682b655fc09e51a10e08075c5ccdd97b6c6443c0e15b0d3efd251cf51', 'scripts/materialize_qr_fixtures.py': 'da154b7bd83186849c08d5932af45d2b066fb4212a27ae62e0cbc1171fc09d51', 'scripts/validate_evidence_budget.py': '2cc09c7cb570ac4501bc3694a33c9b302c70b17075f6b1c74b2fc3fa61c0b898', 'scripts/compile_platform_preflight.py': '4e8f71e1c1ec2833d1cb022d2c051782d388d0b3ff5ac1873ca6ca5411aead46', 'QRCatcher/Info.plist': '5a734a2d89a266bc4e6c193762592ded3eafa4ea0f449579baec8311b6095dff', 'QRCatcher/PrivacyInfo.xcprivacy': 'a82d1b5d9285a2b75f67ff6756ebc9f6a5565d3d4400cfd4fa8747a0b380ae58', 'QRCatcher.xcodeproj/project.pbxproj': 'b88dfe4e98ee99dbab780abe14872fcafbfd88b3dfc02becbb084dc7e243bca0'}
        for name,digest in protected.items():
            with self.subTest(path=name):
                data=(ROOT/name).read_bytes()
                if name=='QRCatcherUITests/QRCatcherPadUITests.m':
                    from test_ios_offline_privacy import restore_pad_for_historical_observer
                    data=restore_pad_for_historical_observer(data.decode()).encode()
                self.assertEqual(hashlib.sha256(data).hexdigest(),digest)
    def test_existing_same_head_preflight_dependency_and_discovery_imports(self):
        self.assertTrue(preflight_contract((ROOT/'.github/workflows/apple-platforms.yml').read_text()))
    def test_missing_preflight_dependency_source_negative(self):
        text=(ROOT/'.github/workflows/apple-platforms.yml').read_text().replace('    needs: preflight\n','',1)
        with self.assertRaises(ValueError):preflight_contract(text)
    def test_missing_full_discovery_source_negative(self):
        text=(ROOT/'.github/workflows/apple-platforms.yml').read_text().replace("python3 -m unittest discover -s Tests/Harness -p 'test_*.py' -v","python3 Tests/Harness/test_atomic_json.py",1)
        with self.assertRaises(ValueError):preflight_contract(text)
    def test_bypassed_preflight_default_success_source_negative(self):
        text=(ROOT/'.github/workflows/apple-platforms.yml').read_text().replace('    needs: preflight\n','    needs: preflight\n    if: ${{ always() }}\n',1)
        with self.assertRaises(ValueError):preflight_contract(text)
    def test_swallowed_discovery_failure_source_negative(self):
        text=(ROOT/'.github/workflows/apple-platforms.yml').read_text().replace("python3 -m unittest discover -s Tests/Harness -p 'test_*.py' -v","python3 -m unittest discover -s Tests/Harness -p 'test_*.py' -v || true",1)
        with self.assertRaises(ValueError):preflight_contract(text)
    def test_missing_required_module_import_coverage_source_negative(self):
        text=(ROOT/'.github/workflows/apple-platforms.yml').read_text()
        for absent in UNITS:
            with self.subTest(module=absent),self.assertRaises(ValueError):preflight_contract(text,[name for name in UNITS if name!=absent])
    def test_preflight_failure_continue_on_error_source_negative(self):
        text=(ROOT/'.github/workflows/apple-platforms.yml').read_text().replace('  preflight:\n','  preflight:\n    continue-on-error: true\n',1)
        with self.assertRaises(ValueError):preflight_contract(text)
    def install_source(self):
        for path in ROOT.rglob('*'):
            relative=path.relative_to(ROOT)
            if path.is_file() and '__pycache__' not in relative.parts and 'build' not in relative.parts:
                target=self.f.root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target);shutil.copymode(path,target)
    def real_fixture(self):
        self.f.close();self.f=Fixture(time.monotonic());self.install_source()
    def test_actual_cli_full_row_module_alias_and_original_fixture_stager(self):
        self.real_fixture();materialized=subprocess.run([sys.executable,'scripts/materialize_qr_fixtures.py'],cwd=self.f.root,capture_output=True,text=True,timeout=10)
        self.assertEqual(materialized.returncode,0,materialized.stdout+materialized.stderr)
        self.f.configure();binary=self.f.root/'bin';binary.mkdir();log=self.f.root/'fake-native.log'
        app=self.f.root/'synthetic-app';app.mkdir();data=self.f.root/'synthetic-data';data.mkdir()
        (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'100mango.QRCatcher','UIFileSharingEnabled':True,'LSSupportsOpeningDocumentsInPlace':True}))
        stub='''#!/usr/bin/env python3
import os,sys,json
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:]
with open(os.environ['APPLE_CALL_LOG'],'a') as f:f.write(json.dumps([name,args])+'\\n')
if name=='xcodebuild':print('Explicit Xcode double; no native execution')
elif args[:2]==['simctl','get_app_container']:print(os.environ['SYNTHETIC_APP' if args[-1]=='app' else 'SYNTHETIC_DATA'])
elif args[:3]==['xcresulttool','get','test-results']:
 expected=2 if '-layout.' in args[-1] else 1
 print(json.dumps({'totalTestCount':expected,'passedTests':expected,'failedTests':0,'skippedTests':0,'expectedFailures':0,'devicesAndConfigurations':[{'device':{'deviceId':os.environ['MINI_SIMULATOR_ID']}}],'runtimeWarnings':[],'result':'Passed','testFailures':[]}))
else:print('Explicit seed double; no service execution')
'''
        for name in ['xcodebuild','xcrun']:(binary/name).write_text(stub);(binary/name).chmod(0o755)
        env={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH'],'APPLE_CALL_LOG':str(log),'SYNTHETIC_APP':str(app),'SYNTHETIC_DATA':str(data)}
        argv=[sys.executable]+(['-O'] if not __debug__ else [])+[str(self.f.root/'scripts/ipad_mini_setup.py'),'row',DEVICE,'MiniUIResults.xcresult','QRCatcherPadUITests']
        result=subprocess.run(argv,cwd=self.f.root,env=env,capture_output=True,text=True,timeout=20,start_new_session=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual((data/'Documents/QRCatcher-Test-Imports/SyntheticQR.png').read_bytes(),(self.f.root/'Tests/Fixtures/unicode.png').read_bytes())
        self.assertEqual(self.f.setup()['unexecuted'],[]);self.assertEqual(result.stdout.count('FIXTURE_CONTAINER_QUERY_END'),2)
        self.assertTrue((self.f.root/'build/ipad-mini-row-dispatched.json').exists())
    def prepare_fixture(self,poison=None):
        self.real_fixture();self.f.budget.path.unlink();binary=self.f.root/'bin';binary.mkdir();log=self.f.root/'fake-apple-calls.log'
        stub='''#!/usr/bin/env python3
import sys,os,json,shutil
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:]
with open(os.environ['APPLE_CALL_LOG'],'a') as f:f.write(json.dumps([name,args])+'\\n')
marker=Path(os.environ['GITHUB_WORKSPACE'])/'build/ipad-mini-host-inflight.json'
raw=marker.read_bytes()
with open(os.environ['APPLE_CALL_LOG']+'.lease.jsonl','a') as f:f.write(json.dumps({'command':[name,args],'lease':json.loads(raw),'sha256':__import__('hashlib').sha256(raw).hexdigest()})+'\\n')
if name=='git':
 if args[:2]==['rev-parse','HEAD']:print(os.environ['GITHUB_SHA'])
 elif args[:1]==['rev-parse']:print('b'*40)
elif name=='xcodebuild' and args==['-version']:print('Xcode 27.0\\nBuild version 27A266a')
elif name=='uname':print('arm64')
elif name=='sips':
 source=Path(args[args.index('--out')-1]);target=Path(args[args.index('--out')+1]);shutil.copyfile(source,target)
else:print('Explicit Apple/identity double; no native execution')
'''
        for name in ['git','sw_vers','xcodebuild','uname','sips','xcrun','plutil']:(binary/name).write_text(stub);(binary/name).chmod(0o755)
        env={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH'],'APPLE_CALL_LOG':str(log)}
        if poison=='true':env['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED']='true'
        elif poison=='marker':(self.f.root/'build/owned-process-cleanup.json').write_text('{"blocked":true}')
        elif poison=='path':env['QRCATCHER_OWNED_PROCESS_BARRIER']=str(self.f.root/'foreign.json')
        return env,log
    def test_actual_host_prepare_keeps_real_lease_without_redundant_unit_reruns(self):
        env,log=self.prepare_fixture();argv=[sys.executable]+(['-O'] if not __debug__ else [])+[str(self.f.root/'scripts/ipad_mini_setup.py'),'phase','prepare']
        result=subprocess.run(argv,cwd=self.f.root,env=env,capture_output=True,text=True,timeout=100,start_new_session=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertNotIn('MINI_SYNTHETIC_UNIT_COMPLETED',result.stdout)
        self.assertNotIn('SHELL_ARGUMENT_ROUTING_PASS',result.stdout)
        self.assertFalse((self.f.root/'build/ipad-mini-host-inflight.json').exists())
        state=json.loads((self.f.root/'build/ipad-mini-job-state.json').read_text());self.assertEqual(state['phases']['prepare']['status'],'completed');self.assertFalse(state['full_job_accepted'])
        calls=[json.loads(line) for line in log.read_text().splitlines()]
        self.assertIn(['xcrun',['swift','scripts/materialize_native_icons.swift']],calls);self.assertTrue(any(name=='sips' for name,args in calls))
        leases=[json.loads(line) for line in Path(str(log)+'.lease.jsonl').read_text().splitlines()]
        self.assertEqual(len(leases),len(calls));self.assertEqual(len({item['sha256'] for item in leases}),1)
        self.assertTrue(all(item['lease']['phase']=='host-prepare' and item['lease']['source']==SHA and item['lease']['command']==['bash','scripts/ipad_mini_prepare.sh'] for item in leases))
        self.assertEqual(len({item['lease']['owner_pid'] for item in leases}),1)
    def test_actual_host_prepare_true_inherited_uncertainty_stops_before_units(self):
        env,log=self.prepare_fixture('true');argv=[sys.executable]+(['-O'] if not __debug__ else [])+[str(self.f.root/'scripts/ipad_mini_setup.py'),'phase','prepare']
        result=subprocess.run(argv,cwd=self.f.root,env=env,capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0);self.assertFalse(log.exists());self.assertNotIn('MINI_SYNTHETIC_UNIT_COMPLETED',result.stdout)
    def test_actual_host_prepare_real_barrier_stops_before_units(self):
        env,log=self.prepare_fixture('marker');argv=[sys.executable]+(['-O'] if not __debug__ else [])+[str(self.f.root/'scripts/ipad_mini_setup.py'),'phase','prepare']
        result=subprocess.run(argv,cwd=self.f.root,env=env,capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0);self.assertFalse(log.exists());self.assertNotIn('MINI_SYNTHETIC_UNIT_COMPLETED',result.stdout)
    def test_actual_host_prepare_poisoned_barrier_path_stops_before_units(self):
        env,log=self.prepare_fixture('path');result=subprocess.run([sys.executable,str(self.f.root/'scripts/ipad_mini_setup.py'),'phase','prepare'],cwd=self.f.root,env=env,capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0);self.assertFalse(log.exists())

if __name__=='__main__':unittest.main()
