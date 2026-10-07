"""Execute fixed adapter boundaries with owned files and command doubles only."""
import contextlib
import copy
import hashlib
import importlib.util
import json
import os
import io
import runpy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(Path(__file__).parent)]
import vision_targeted_job as adapter
import test_vision_capture_collector as collector

class ClockTests(unittest.TestCase):
    def data(self, job='photos'):
        scope, ceiling, reserve = adapter.JOBS[job]
        env = {'GITHUB_JOB': job, 'GITHUB_SHA': 'a'*40, 'GITHUB_WORKFLOW_SHA': 'a'*40,
               'GITHUB_REPOSITORY': '100mango/QRCatcher', 'GITHUB_REF': adapter.BRANCH,
               'GITHUB_RUN_ID': '12', 'GITHUB_RUN_ATTEMPT': '1', 'EVIDENCE_SCOPE': scope}
        value = {'schema': 1, 'repository': env['GITHUB_REPOSITORY'], 'ref': env['GITHUB_REF'],
                 'source': env['GITHUB_SHA'], 'workflow_sha': env['GITHUB_WORKFLOW_SHA'],
                 'run_id': '12', 'attempt': '1', 'job': job, 'scope': scope,
                 'ceiling_seconds': ceiling, 'reserve_seconds': reserve, 'started_monotonic': 1000.0}
        return value, env
    def test_clock_exact_binding_and_wrong_inputs(self):
        value, env = self.data(); self.assertEqual(adapter.inspect_clock(value, env, 1100)[2], 2600)
        for key in value:
            bad = copy.deepcopy(value); bad[key] = None
            with self.subTest(key=key), self.assertRaises(ValueError): adapter.inspect_clock(bad, env, 1100)
        for start in [0, -1, True, float('nan'), float('inf'), 1101]:
            bad = dict(value, started_monotonic=start)
            with self.assertRaises(ValueError): adapter.inspect_clock(bad, env, 1100)
        for key, item in [('GITHUB_JOB','files'),('EVIDENCE_SCOPE','visionos_files'),('GITHUB_REF','refs/heads/master'),('GITHUB_SHA','b'*40)]:
            with self.assertRaises(ValueError): adapter.inspect_clock(value, dict(env, **{key:item}), 1100)
    def test_every_phase_reserves_original_clock_and_unknown_scope_is_rejected(self):
        for job, phases in adapter.CAPS.items():
            for phase, cap in phases.items():
                reserve = adapter.JOBS[job][2] if phase in adapter.BUSINESS[job] else sum(phases[p] for p in adapter.FINAL[adapter.FINAL.index(phase)+1:]) + 90
                self.assertEqual(adapter.phase_allowance(job, phase, cap+reserve), cap)
                with self.assertRaises(ValueError): adapter.phase_allowance(job, phase, cap+reserve-0.01)
        for phase in ['files','largest','seed','hosted']:
            with self.assertRaises(ValueError): adapter.phase_allowance('privacy', phase, 1500)
    def test_native_timeout_host_cleanup_does_not_release_uncertainty(self):
        good={'state':'completed','cleanup_confirmed':True,'exit':0}
        self.assertFalse(adapter.uncertain_operation('seed',0,good))
        for code in [124,125,126]: self.assertTrue(adapter.uncertain_operation('seed',code,good))
        self.assertTrue(adapter.uncertain_operation('hosted',0,dict(good,cleanup_confirmed=False)))
        self.assertTrue(adapter.uncertain_operation('ui',1,good,{'cases':[{'exit':124,'operation':{'state':'timed_out','cleanup_confirmed':True}}]}))
        self.assertFalse(adapter.uncertain_operation('ui',0,good,{'cases':[{'exit':0,'operation':good,'pre_case_app_termination':good}],'capture_cleanup_confirmed':True,'capture_process_exit':0}))

class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(); self.old=Path.cwd(); os.chdir(self.root);self.addCleanup(os.chdir,self.old)
        self.value,self.env=ClockTests().data()
        self.clock=self.root/'qr-vision-12-1-photos.json'; self.clock.write_text(json.dumps(self.value))
        self.env.update(GITHUB_WORKSPACE=str(self.root), RUNNER_TEMP=str(self.root), QRCATCHER_VISION_TARGETED_CLOCK=str(self.clock),
                        GITHUB_ENV=str(self.root/'github-env'), GITHUB_OUTPUT=str(self.root/'github-output'),
                        QRCATCHER_OWNED_PROCESS_BARRIER=str(self.root/'build/owned-process-cleanup.json'),
                        VISION_SIMULATOR_ID='11111111-2222-4333-8444-555555555555')
        self.environment=patch.dict(os.environ,self.env,clear=True);self.environment.start();self.addCleanup(self.environment.stop)
        self.time=patch.object(adapter.time,'monotonic',return_value=1000.0);self.time.start();self.addCleanup(self.time.stop)
        self.prepare=adapter.Job('prepare');self.prepare.row['state']='passed';self.prepare.write()
    def prior(self, until):
        for name in adapter.BUSINESS['photos']:
            if name==until:break
            if name=='prepare':continue
            path=self.root/'build/vision-targeted-stages'/ (name+'.json')
            path.write_text(json.dumps({'phase':name,'state':'passed','scope':'visionos_photos','source':'a'*40,'job':'photos','run_id':'12','attempt':'1'}))
    def result(self,args,seconds,**kwargs):
        return 0,'',{'command':args,'timeout_seconds':seconds,'state':'completed','cleanup_confirmed':True,'exit':0}
    def test_exact_once_phase_and_original_clock_reset_rejected(self):
        with self.assertRaises(ValueError): adapter.Job('prepare')
        self.value['started_monotonic']=999.0;self.clock.write_text(json.dumps(self.value))
        with self.assertRaises(ValueError): adapter.Job('build')
    def test_hosted_is_required_before_seed_and_no_UI_after_seed_failure(self):
        self.prior('hosted')
        job=adapter.Job('seed')
        with patch.object(adapter,'execute',side_effect=self.result) as run, self.assertRaises(ValueError):job.perform()
        run.assert_not_called()
        ui=adapter.Job('ui')
        with patch.object(adapter,'execute',side_effect=self.result) as run,self.assertRaises(ValueError):ui.perform()
        run.assert_not_called()
    def test_seed_is_one_exact_command_and_timeout_blocks_followup(self):
        self.prior('seed'); job=adapter.Job('seed')
        def timeout(args,seconds,**kwargs):return 124,'',{'command':args,'timeout_seconds':seconds,'state':'timed_out','cleanup_confirmed':True,'exit':124}
        with patch.object(adapter,'execute',side_effect=timeout) as run,self.assertRaises(ValueError):job.perform()
        self.assertEqual(run.call_count,1);self.assertEqual(run.call_args.args[0][:3],['xcrun','simctl','addmedia']);self.assertEqual(run.call_args.args[1],150)
        self.assertTrue(adapter.blocked())
        shutdown=adapter.Job('shutdown')
        with patch.object(adapter,'execute',side_effect=self.result) as run,self.assertRaises(ValueError):shutdown.perform()
        run.assert_not_called()
    def test_interrupted_controller_receipt_prevents_shutdown(self):
        self.prior('hosted'); interrupted=adapter.Job('hosted')
        interrupted.row['operations']=[{'state':'starting','command':['xcodebuild']}];interrupted.write()
        later=adapter.Job('collect');self.assertTrue(adapter.blocked())
        with patch.object(adapter,'execute',side_effect=AssertionError('no host or device command')):later.perform()
        manifest=adapter.read_json(self.root/'build/ios-platform-evidence/manifest.json')
        self.assertFalse(manifest['qualified']);self.assertTrue(manifest['host_only_retention'])
    def test_spawn_exception_marks_device_uncertainty(self):
        self.prior('seed');job=adapter.Job('seed')
        with patch.object(adapter,'execute',side_effect=RuntimeError('interrupted')),self.assertRaises(RuntimeError):job.perform()
        self.assertTrue(adapter.blocked());self.assertTrue(job.row['simulator_operation_unconfirmed'])
    def test_failed_UI_collect_is_host_only_before_shutdown(self):
        self.prior('ui');p=self.root/'build/vision-targeted-stages/ui.json';p.write_text(json.dumps({'phase':'ui','state':'failed'}))
        runtime=self.root/'build/vision-runtime';runtime.mkdir();(runtime/'runtime.json').write_text('{}')
        job=adapter.Job('collect')
        with patch.object(adapter,'execute',side_effect=AssertionError('no native followup')):job.perform()
        self.assertTrue(job.row['host_only_retention'])
        manifest=adapter.read_json(self.root/'build/ios-platform-evidence/manifest.json')
        self.assertFalse(manifest['native_followup_started']);self.assertFalse(manifest['qualified'])
    def test_validation_retains_bounded_failure_without_deleting_oversized_pixels(self):
        out=self.root/'build/ios-platform-evidence';out.mkdir();(out/'manifest.json').write_text('{"qualified":false}')
        (out/'one.jpg').write_bytes(b'x'*600000);(out/'two.jpg').write_bytes(b'x'*600000)
        job=adapter.Job('validate');job.perform()
        self.assertFalse(job.row['qualified']);self.assertEqual(job.row['artifact_path'],'build/vision-targeted-failure')
        self.assertEqual((out/'one.jpg').stat().st_size,600000)
        self.assertIn('eligible=true',(self.root/'github-output').read_text())
    def test_hosted_summary_requires_all_eleven_before_seed(self):
        self.prior('hosted');job=adapter.Job('hosted')
        device=self.env['VISION_SIMULATOR_ID']
        summary={'totalTestCount':11,'passedTests':11,'failedTests':0,'skippedTests':0,'expectedFailures':0,'result':'Passed',
                 'devicesAndConfigurations':[{'device':{'deviceId':device,'platform':'visionOS Simulator'}}]}
        def run(args,seconds,**kwargs):
            return 0,json.dumps(summary) if 'xcresulttool' in args else '',{'command':args,'timeout_seconds':seconds,'state':'completed','cleanup_confirmed':True,'exit':0}
        with patch.object(adapter,'execute',side_effect=run) as mocked:job.perform()
        self.assertEqual(job.row['actual_hosted_passed'],11);self.assertEqual(mocked.call_count,2)
        self.assertEqual(mocked.call_args_list[0].args[1],555);self.assertEqual(mocked.call_args_list[1].args[1],30)
        self.assertTrue((self.root/'build/vision-runtime/hosted-summary.json').is_file())
    def test_wrong_hosted_count_never_qualifies_warmup(self):
        self.prior('hosted');job=adapter.Job('hosted')
        def run(args,seconds,**kwargs):
            return 0,'{}',{'command':args,'timeout_seconds':seconds,'state':'completed','cleanup_confirmed':True,'exit':0}
        with patch.object(adapter,'execute',side_effect=run),self.assertRaises(ValueError):job.perform()
        self.assertEqual(job.row['state'],'failed')
        seed=adapter.Job('seed')
        with patch.object(adapter,'execute') as mocked,self.assertRaises(ValueError):seed.perform()
        mocked.assert_not_called()
    def test_known_success_seed_preserves_command_cap(self):
        self.prior('seed');job=adapter.Job('seed')
        with patch.object(adapter,'execute',side_effect=self.result) as run:job.perform()
        self.assertEqual(job.row['state'],'passed');self.assertEqual(run.call_count,1);self.assertEqual(run.call_args.args[1],150)

class WorkflowTests(unittest.TestCase):
    def test_published_entry_admits_only_fixed_privacy_job_before_any_phase(self):
        for job,scope in [('photos','visionos_photos'),('privacy','visionos_files'),('files','visionos_privacy')]:
            with patch.dict(os.environ,{'GITHUB_JOB':job,'EVIDENCE_SCOPE':scope},clear=True), patch.object(sys,'argv',['vision_targeted_job.py','prepare']), patch.object(adapter,'Job') as controller, self.assertRaises(ValueError):
                adapter.main()
            controller.assert_not_called()
        with patch.dict(os.environ,{'GITHUB_JOB':'privacy','EVIDENCE_SCOPE':'visionos_privacy'},clear=True), patch.object(sys,'argv',['vision_targeted_job.py','prepare']), patch.object(adapter,'Job') as controller:
            adapter.main()
        controller.assert_called_once_with('prepare'); controller.return_value.perform.assert_called_once_with()

    def test_fixed_serial_fresh_VM_jobs_and_evidence_first_order(self):
        workflow=json.loads((ROOT/adapter.WORKFLOW).read_text())
        self.assertEqual(list(workflow['jobs']),['privacy'])
        self.assertEqual(workflow['on'],{'push':{'branches':['codex/vision-targeted-completion']}})
        self.assertEqual(workflow['concurrency'],{'group':'qrcatcher-apple-platforms','cancel-in-progress':False})
        self.assertEqual(workflow['permissions'],{'contents':'read'})
        self.assertNotIn('needs',workflow['jobs']['privacy'])
        self.assertNotIn('if',workflow['jobs']['privacy'])
        for name,job in workflow['jobs'].items():
            self.assertEqual(job['runs-on'],'xcode-27');self.assertNotIn('strategy',job)
            self.assertEqual(job['timeout-minutes'],45 if name=='photos' else 25)
            ids=[s.get('id') for s in job['steps']]
            self.assertEqual(ids[0],'origin');self.assertIn('actions/checkout@',job['steps'][1]['uses'])
            self.assertEqual([i for i in ids if i in adapter.BUSINESS[name]],list(adapter.BUSINESS[name]))
            self.assertLess(ids.index('collect'),ids.index('shutdown'));self.assertLess(ids.index('source_final'),ids.index('validate'));self.assertLess(ids.index('validate'),ids.index('upload'))
            source=job['steps'][0]['run'].split("<<'PY_CLOCK'\n",1)[1].rsplit('\nPY_CLOCK',1)[0];compile(source,'original-clock','exec')
            upload=next(s for s in job['steps'] if s.get('id')=='upload');self.assertEqual(upload['with']['retention-days'],1)
            self.assertEqual(upload['with']['path'],'${{ steps.validate.outputs.artifact_path }}')
            for step in job['steps']:
                if 'run' in step:
                    result=subprocess.run(['bash','-n'],input=step['run'],text=True,capture_output=True)
                    self.assertEqual(result.returncode,0,result.stderr)
            text=json.dumps(job)
            for forbidden in ['visionos_photos','visionos_files','visionos_largest','continue-on-error','rerun','download-artifact']:
                self.assertNotIn(forbidden,text)
    def test_source_unchanged_input_map_and_no_shipping_paths_in_allowance(self):
        value=json.loads((ROOT/'scripts/vision_targeted_source_inputs.json').read_text())
        self.assertEqual(value['base_commit'],adapter.PARENT);self.assertEqual(len(value['unchanged_inputs']),416)
        for row in value['unchanged_inputs']:
            self.assertEqual(hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest(),row['sha256'])
            self.assertNotIn(row['path'],adapter.ALLOWED_CHANGED)
        self.assertFalse(any(p.startswith(('QRCatcherVision/','Shared/','QRCatcherMac/')) for p in adapter.ALLOWED_CHANGED))

class OriginExecutionTests(unittest.TestCase):
    def test_actual_embedded_origin_writes_one_real_ENV_line_for_each_job(self):
        workflow=json.loads((ROOT/adapter.WORKFLOW).read_text())
        for job in workflow['jobs']:
            with self.subTest(job=job), tempfile.TemporaryDirectory() as folder:
                folder=Path(folder).resolve(); value,env=ClockTests().data(job)
                env.update(RUNNER_TEMP=str(folder),GITHUB_WORKSPACE=str(folder),GITHUB_ENV=str(folder/'github-env'),GITHUB_OUTPUT=str(folder/'github-output'))
                shell=workflow['jobs'][job]['steps'][0]['run']
                source=shell.split("<<'PY_CLOCK'\n",1)[1].rsplit('\nPY_CLOCK',1)[0]
                result=subprocess.run([sys.executable,'-c',source],env=env,text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr)
                raw=(folder/'github-env').read_bytes()
                self.assertTrue(raw.endswith(b'\n'));self.assertEqual(raw.count(b'\n'),1)
                key,path=raw.decode().strip().split('=',1)
                self.assertEqual(key,'QRCATCHER_VISION_TARGETED_CLOCK');self.assertTrue(Path(path).is_file())
                env[key]=path
                old=Path.cwd()
                try:
                    os.chdir(folder)
                    with patch.dict(os.environ,env,clear=True):
                        receipt=adapter.Job('prepare');self.assertEqual(receipt.job,job)
                finally:os.chdir(old)
                before=Path(path).read_bytes()
                again=subprocess.run([sys.executable,'-c',source],env=env,text=True,capture_output=True)
                self.assertNotEqual(again.returncode,0);self.assertEqual(Path(path).read_bytes(),before)

class NestedTimeoutTests(unittest.TestCase):
    def exercise(self,scope,mode):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();old=Path.cwd();os.chdir(root)
            calls=[];drain=[];cleanup=[]
            def execute(args,seconds):
                calls.append(args)
                code=124 if (mode=='terminate_timeout' and len(calls)==1) or (mode=='ui_timeout' and len(calls)==2) else 0
                if mode=='not_running' and len(calls)==1:code=3
                detail={'command':args,'timeout_seconds':seconds,'state':'timed_out' if code==124 else 'completed','cleanup_confirmed':True,'exit':code}
                if mode=='terminate_unknown' and len(calls)==1:detail.pop('state')
                return code,'',detail
            class Capture:
                def wait(self,timeout):
                    drain.append(adapter.blocked())
                    if mode=='capture_timeout':raise subprocess.TimeoutExpired('capture',timeout)
                    return 0
            def stop(process):cleanup.append(adapter.blocked());return True
            env={'GITHUB_SHA':'a'*40,'EVIDENCE_SCOPE':scope,'GITHUB_WORKSPACE':str(root),'GITHUB_ENV':str(root/'env'),'QRCATCHER_OWNED_PROCESS_BARRIER':str(root/'build/owned-process-cleanup.json')}
            try:
                with patch.dict(os.environ,env,clear=True),patch.object(sys,'argv',['run_vision_ui_cases.py','11111111-1111-4111-8111-111111111111',scope]),patch('watch_process.execute',side_effect=execute),patch('subprocess.Popen',return_value=Capture()),patch('owned_process_group.stop_group',side_effect=stop),contextlib.redirect_stdout(io.StringIO()):
                    code=0
                    try:runpy.run_path(str(ROOT/'scripts/run_vision_ui_cases.py'),run_name='__main__')
                    except SystemExit:code=1
                    report=json.loads((root/'build/vision-runtime/ui-cases.json').read_text());latched=adapter.blocked()
                return {'code':code,'calls':calls,'drain':drain,'cleanup':cleanup,'report':report,'latched':latched}
            finally:os.chdir(old)
    def test_both_cases_lock_all_three_nested_timeouts_before_any_followup(self):
        for scope in ['visionos_photos','visionos_privacy']:
            for mode in ['terminate_timeout','ui_timeout','capture_timeout','terminate_unknown']:
                with self.subTest(scope=scope,mode=mode):
                    result=self.exercise(scope,mode)
                    self.assertEqual(result['code'],1);self.assertTrue(result['latched']);self.assertEqual(result['cleanup'],[True])
                    self.assertEqual(len(result['calls']),1 if mode.startswith('terminate') else 2)
                    self.assertEqual(result['drain'],[mode!='capture_timeout'])
                    self.assertTrue(adapter.uncertain_operation('ui',1,{'state':'completed','cleanup_confirmed':True},result['report']))
    def test_known_completed_app_not_running_keeps_original_success_route(self):
        for scope in ['visionos_photos','visionos_privacy']:
            result=self.exercise(scope,'not_running')
            self.assertEqual(result['code'],0);self.assertFalse(result['latched']);self.assertEqual(len(result['calls']),2)
            self.assertEqual(result['report']['cases'][0]['pre_case_app_termination']['exit'],3)
            self.assertFalse(adapter.uncertain_operation('ui',0,{'state':'completed','cleanup_confirmed':True},result['report']))
    def test_adapter_does_not_trust_cleared_inner_failure_flag(self):
        for mode in ['terminate_timeout','capture_timeout']:
            result=self.exercise('visionos_photos',mode);report=result['report'];report['cleanup_unconfirmed']=False
            if mode=='terminate_timeout':
                report['cases'][0].update(state='finished',exit=0,operation={'state':'completed','cleanup_confirmed':True,'exit':0})
            self.assertTrue(adapter.uncertain_operation('ui',0,{'state':'completed','cleanup_confirmed':True},report))
        self.assertTrue(adapter.uncertain_operation('ui',0,{'state':'completed','cleanup_confirmed':True},None))


class SourceGuardTests(unittest.TestCase):
    def runner(self, changed=None, parents=None):
        paths=sorted({r['path'] for r in json.loads((ROOT/'scripts/vision_targeted_source_inputs.json').read_text())['unchanged_inputs']} | adapter.ALLOWED_CHANGED)
        responses={('rev-parse','HEAD'):'a'*40, ('rev-list','--parents','-n','1','HEAD'):parents or ('a'*40+' '+adapter.PARENT),
                   ('diff','--name-only','HEAD','--'):'', ('diff','--name-only',adapter.PARENT,'HEAD','--'):'\n'.join(sorted(changed or adapter.ALLOWED_CHANGED)),
                   ('ls-files',):'\n'.join(paths), ('rev-parse','HEAD^{tree}'):'b'*40}
        def run(args,seconds):return 0,responses[tuple(args[1:])],{'cleanup_confirmed':True}
        return run
    def test_actual_complete_source_inventory_and_sole_parent(self):
        with patch.dict(os.environ,{'GITHUB_SHA':'a'*40}):
            result=adapter.source_snapshot(ROOT,self.runner())
            self.assertEqual(len(result['files']),426)
            for parent in ['a'*40+' '+adapter.PARENT+' '+'c'*40, 'a'*40+' '+'c'*40]:
                with self.assertRaises(ValueError):adapter.source_snapshot(ROOT,self.runner(parents=parent))
            with self.assertRaises(ValueError):adapter.source_snapshot(ROOT,self.runner(changed=adapter.ALLOWED_CHANGED|{'QRCatcherVision/VisionMainView.swift'}))
    def test_changed_shipping_bytes_are_rejected_even_if_Git_command_is_faked(self):
        original=adapter.load_regular
        def load(path,limit=512*1024):
            value=original(path,limit)
            return value+b'\n' if str(path).endswith('QRCatcherVision/VisionMainView.swift') else value
        with patch.dict(os.environ,{'GITHUB_SHA':'a'*40}),patch.object(adapter,'load_regular',side_effect=load),self.assertRaises(ValueError):
            adapter.source_snapshot(ROOT,self.runner())


class CaptureStopTests(unittest.TestCase):
    def test_capture_timeout_never_starts_converter_or_followup_capture(self):
        instance=collector.VisionCollectorIntegrationTests()
        for mode,expected in [('screenshot-timeout',1),('conversion-timeout',2)]:
            # A fixture may not write the real workflow's uncertainty marker.
            with patch.dict(os.environ, {}, clear=True):
                result=instance.collect(mode)
            commands=[a for kind,a in result['commands'] if kind=='command']
            self.assertNotEqual(result['code'],0);self.assertEqual(len(commands),expected)
            self.assertFalse(result['row']['success']);self.assertFalse(result['ack']['success'])
            self.assertFalse(result['row'].get('pixels_retained',False))

if __name__=='__main__': unittest.main()
