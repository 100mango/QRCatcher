"""Control-flow doubles only. These do not claim installed simctl support."""
import json,os,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from simulator_content_size import probe,LARGEST,validate_ui_command

DEVICE='11111111-2222-4333-8444-555555555555'
# Deliberately synthetic help: the real next runner must provide its own help,
# which is retained and checked before any device setting is changed.
HELP='''Usage: simctl ui <device> <option> [<arguments>]
    content_size
        Get or set content size.
        small medium large extra-large accessibility-extra-extra-extra-large
    appearance
        light dark
'''

class SimulatorContentSizeTests(unittest.TestCase):
    def setUp(self):
        isolation=patch.dict(os.environ);isolation.start();self.addCleanup(isolation.stop)
        for key in ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED','QRCATCHER_OWNED_PROCESS_BARRIER','GITHUB_ENV','GITHUB_WORKSPACE']:os.environ.pop(key,None)
    def ui_fixture(self,folder):
        root=Path(folder);project=root/'QR.xcodeproj';derived=root/'build'/'Vision'
        project.mkdir();derived.mkdir(parents=True)
        contract=dict(root=str(root),project='QR.xcodeproj',scheme='QRVision',derived_data='build/Vision',test_bundle='QRVisionUITests',platform='visionOS Simulator')
        command=['xcodebuild','test-without-building','-project',str(project),'-scheme','QRVision','-derivedDataPath',str(derived),'-destination','platform=visionOS Simulator,id='+DEVICE,'-configuration','Debug','-resultBundlePath',str(root/'Result.xcresult'),'-only-testing:QRVisionUITests/Flow/testImport','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-test-timeouts-enabled','YES','CODE_SIGNING_ALLOWED=NO']
        return contract,command
    def run_probe(self,variant='normal',ui=False,ui_timeout=300):
        calls=[];current='medium';setting_writes=[]
        def run(args,seconds,**options):
            nonlocal current
            calls.append(args)
            detail={'command':args,'exit':0,'state':'completed','timeout_seconds':seconds,'cleanup_confirmed':True}
            if args==['xcrun','simctl','help','ui']:
                if variant=='missing_cleanup':detail.pop('cleanup_confirmed')
                return 0,HELP if variant!='unknown_help' else HELP.replace('content_size','unrecognized_setting'),detail
            if args==['xcrun','simctl','list','devices','-j']:
                return 0,json.dumps({'devices':{'com.apple.CoreSimulator.SimRuntime.xrOS-27-0':[{'udid':DEVICE,'state':'Booted'}]}}),detail
            if args[:2]==['xcodebuild','test-without-building']:
                self.assertEqual(current,LARGEST)
                self.assertTrue(options['echo'],'Real held-capture markers must remain visible to the existing log reader')
                if variant=='ui_cleanup_unknown':detail['cleanup_confirmed']=False
                return (1 if variant=='ui_failure' else 0),'synthetic UI command result',detail
            self.assertEqual(args[:5],['xcrun','simctl','ui',DEVICE,'content_size'])
            if len(args)==6:
                # Original is durably recorded before the first setter.
                self.assertEqual(json.loads(report.read_text())['observed_original'],'medium')
                setting_writes.append(args[-1])
                if args[-1]==LARGEST:
                    if variant!='readback_mismatch':current=LARGEST
                    if variant=='set_cleanup_unknown':
                        detail['cleanup_confirmed']=False
                        return 124,'synthetic timeout with surviving owned child',detail
                    if variant=='uncertain_set':return 124,'synthetic timeout after setting applied',detail
                elif variant!='restore_failure':current=args[-1]
                if variant=='restore_cleanup_unknown' and args[-1]=='medium':detail['cleanup_confirmed']=False
                return 0,'',detail
            if variant=='unsupported_device' and not setting_writes:return 1,'This runtime rejects content_size',detail
            if variant=='read_cleanup_unknown':detail['cleanup_confirmed']=False
            return 0,current,detail
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'probe.json'
            contract,command=self.ui_fixture(folder)
            result=probe(DEVICE,report,command if ui else None,ui_timeout,runner=run,expected_ui=contract if ui else None)
            self.assertEqual(result,json.loads(report.read_text()))
        return result,setting_writes,calls

    def test_unknown_help_never_queries_or_writes_an_invented_action(self):
        value,writes,calls=self.run_probe('unknown_help')
        self.assertEqual(value['status'],'help_syntax_not_recognized');self.assertEqual(writes,[]);self.assertEqual(len(calls),1)
    def test_device_rejection_never_mutates_settings(self):
        value,writes,_=self.run_probe('unsupported_device')
        self.assertEqual(value['status'],'device_read_rejected');self.assertEqual(writes,[])
    def test_setting_only_probe_does_not_claim_ui_coverage(self):
        value,writes,_=self.run_probe()
        self.assertEqual(value['status'],'setting_probe_only_ui_not_executed');self.assertFalse(value['ui_executed'])
        self.assertTrue(value['restore_verified']);self.assertEqual(writes,[LARGEST,'medium'])
    def test_ui_executes_only_after_exact_largest_readback_then_restores(self):
        value,writes,_=self.run_probe(ui=True)
        self.assertEqual(value['status'],'largest_ui_passed');self.assertEqual(value['ui_exit'],0);self.assertTrue(value['restore_verified'])
    def test_explicit_approved_whole_command_bound_accepts_840_and_900(self):
        for cap in [840,900]:
            value,_,_=self.run_probe(ui=True,ui_timeout=cap)
            self.assertEqual(next(row['operation']['timeout_seconds'] for row in value['operations'] if row['label']=='actual_ui'),cap)
    def test_ui_failure_remains_failure_after_restore(self):
        value,_,_=self.run_probe('ui_failure',ui=True)
        self.assertEqual(value['status'],'largest_ui_failed');self.assertEqual(value['ui_exit'],1);self.assertTrue(value['restore_verified'])
    def test_uncertain_write_is_reconciled_without_retry(self):
        value,writes,_=self.run_probe('uncertain_set')
        self.assertEqual(value['observed_largest'],LARGEST);self.assertEqual(writes,[LARGEST,'medium'])
    def test_failed_readback_does_not_execute_ui(self):
        value,writes,_=self.run_probe('readback_mismatch',ui=True)
        self.assertEqual(value['status'],'largest_readback_failed');self.assertFalse(value['ui_executed']);self.assertTrue(value['restore_verified'])
        self.assertEqual(writes,[LARGEST])
    def test_failed_restore_stays_red_with_exact_observed_value(self):
        value,writes,_=self.run_probe('restore_failure',ui=True)
        self.assertEqual(value['status'],'restore_readback_failed');self.assertFalse(value['restore_verified'])
        self.assertEqual(value['observed_restored'],LARGEST);self.assertEqual(writes,[LARGEST,'medium'])
    def test_uncertain_set_with_unconfirmed_cleanup_stops_before_ui_or_second_mutation(self):
        value,writes,calls=self.run_probe('set_cleanup_unknown',ui=True)
        self.assertEqual(value['status'],'owned_process_cleanup_unconfirmed')
        self.assertFalse(value['ui_executed']);self.assertFalse(value['restore_verified'])
        self.assertEqual(writes,[LARGEST]);self.assertEqual(calls[-1][-1],LARGEST)
        self.assertEqual(value['operations'][-1]['label'],'set_largest')
    def test_unconfirmed_reader_stops_before_any_setting_write(self):
        value,writes,_=self.run_probe('read_cleanup_unknown',ui=True)
        self.assertEqual(value['status'],'owned_process_cleanup_unconfirmed');self.assertEqual(writes,[])
        self.assertEqual(value['operations'][-1]['label'],'read_original')
    def test_unconfirmed_ui_group_prevents_restore_command(self):
        value,writes,_=self.run_probe('ui_cleanup_unknown',ui=True)
        self.assertEqual(value['status'],'owned_process_cleanup_unconfirmed');self.assertEqual(writes,[LARGEST])
        self.assertEqual(value['operations'][-1]['label'],'actual_ui');self.assertFalse(value['restore_verified'])
    def test_missing_runner_cleanup_proof_stops_after_help(self):
        value,writes,calls=self.run_probe('missing_cleanup')
        self.assertEqual(value['status'],'owned_process_cleanup_unconfirmed');self.assertEqual(writes,[]);self.assertEqual(len(calls),1)
    def test_unconfirmed_restore_stops_before_another_read_or_write(self):
        value,writes,_=self.run_probe('restore_cleanup_unknown')
        self.assertEqual(value['status'],'owned_process_cleanup_unconfirmed');self.assertEqual(writes,[LARGEST,'medium'])
        self.assertEqual(value['operations'][-1]['label'],'restore_original');self.assertFalse(value['restore_verified'])
    def test_exact_command_contract_rejects_wrong_device_product_root_and_selectors_before_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            contract,command=self.ui_fixture(folder)
            validate_ui_command(command,DEVICE,contract)
            changes={'-destination':'platform=visionOS Simulator,id=AAAAAAAA-2222-4333-8444-555555555555','-project':folder,'-derivedDataPath':folder,'-scheme':'OtherApp','-configuration':'Release','-resultBundlePath':str(Path(folder).parent/'Escaped.xcresult')}
            for option,value in changes.items():
                altered=command.copy();altered[altered.index(option)+1]=value
                with self.subTest(option=option),self.assertRaises(ValueError):
                    probe(DEVICE,Path(folder)/'probe.json',altered,runner=lambda *a,**k:self.fail('No command may run'),expected_ui=contract)
            for altered in [command+['-only-testing:OtherUITests'],command+['-destination','platform=visionOS Simulator,id='+DEVICE],command+['-sdk','iphoneos'],command[:-1]+['CODE_SIGNING_ALLOWED=YES'],command+['-parallel-testing-enabled','YES'],command+['-maximum-test-execution-time-allowance','999999']]:
                with self.assertRaises(ValueError):validate_ui_command(altered,DEVICE,contract)
    def test_optimized_python_keeps_timeout_and_ui_contract_guards(self):
        script='from simulator_content_size import probe; from pathlib import Path\nfor kwargs in ({"ui_timeout":0},{"ui_timeout":901},{"ui_command":["xcodebuild","test-without-building"]}):\n try: probe("'+DEVICE+'",Path("unused.json"),runner=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("must not execute")),**kwargs)\n except ValueError: continue\n raise SystemExit("guard omitted")\n'
        import os
        result=subprocess.run([sys.executable,'-O','-c',script],env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[2]/'scripts')),capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
