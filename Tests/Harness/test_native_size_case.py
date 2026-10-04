"""Command contracts only; installed system-size support requires Apple runtime."""
import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from run_native_size_case import run_case
from simulator_content_size import validate_ui_command

class NativeSizeCaseTests(unittest.TestCase):
    def setUp(self):
        isolation=patch.dict(os.environ);isolation.start();self.addCleanup(isolation.stop)
        for key in ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED','QRCATCHER_OWNED_PROCESS_BARRIER','GITHUB_ENV','GITHUB_WORKSPACE']:os.environ.pop(key,None)
    def exercise(self,platform,status='largest_ui_passed',precondition=True,original_raw=None,output=None,unknown=False,raises=False):
        device='11111111-2222-4333-8444-555555555555';calls=[]
        def probe(udid,path,command,cap,**kwargs):
            calls.append((command,cap))
            if precondition:validate_ui_command(command,device,kwargs['expected_ui'])
            else:self.assertIsNone(command)
            return {'status':status,'restore_verified':status=='largest_ui_passed','original_raw':original_raw}
        proof={'trait':'accessibility5','baseline_body_metric':17,'actual_body_metric':24,'baseline_payload_height':20,'actual_payload_height':48,'viewport_width_points':162,'viewport_height_points':197,'system_setting_propagation':False}
        def run(command,cap):
            expected={'watch':(240,'Watch','testFixtureResultAndRelaunchAtLargestPublicTrait'),'tv':(420,'TV','testPreconditionedPhotosWorkflowAtLargestPublicTrait')}[platform]
            self.assertEqual(cap,expected[0]);self.assertIn('-only-testing:QRCatcher'+expected[1]+'UITests/QRCatcher'+expected[1]+'UITests/'+expected[2],command)
            if raises:raise RuntimeError('synthetic runner exception before cleanup metadata')
            return 126 if unknown else 0,output if output is not None else ('WATCH_PUBLIC_TRAIT_PROOF ' if platform=='watch' else 'TV_PUBLIC_TRAIT_PROOF ')+json.dumps(proof),{'cleanup_confirmed':not unknown,'exit':126 if unknown else 0}
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'QRCatcher.xcodeproj').mkdir()
            for name in ['Watch','Vision','TV']:(folder/'build'/(name+'Tests')).mkdir(parents=True)
            old=Path.cwd()
            try:
                os.chdir(folder)
                with patch('run_native_size_case.probe',side_effect=probe),patch('run_native_size_case.execute',side_effect=run) as runner:
                    result=run_case(platform,device,precondition)
                    expected=platform in {'watch','tv'} and precondition and status=='original_value_not_recognized' and original_raw=='unsupported'
                    self.assertEqual(runner.call_count,int(expected))
            finally:os.chdir(old)
        return result,calls
    def test_each_platform_runs_one_existing_applicable_case_with_its_smaller_bound(self):
        for platform,cap,case in [('watch',240,'testFixtureFedOfflineResultSourceImageAndRelaunch'),('vision',300,'testChineseEmptyPhotosResultAndOfflinePolicy'),('tv',420,'testExplicitlyPreconditionedPhotosDecodeExportAndReopen')]:
            with self.subTest(platform=platform):
                result,calls=self.exercise(platform);self.assertEqual(result[0],0);self.assertEqual(len(calls),1)
                self.assertEqual(calls[0][1],cap);self.assertTrue(any(arg.endswith('/'+case) for arg in calls[0][0]))
    def test_unknown_help_keeps_required_gate_red_without_claiming_ui_coverage(self):
        result,_=self.exercise('vision','help_syntax_not_recognized');self.assertEqual(result[0],2)
        self.assertNotEqual(os.environ.get('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED'),'true')
    def test_missing_watch_fixture_precondition_cannot_claim_largest_ui_pass(self):
        result,calls=self.exercise('watch','setting_probe_only_ui_not_executed',False)
        self.assertEqual(result[0],2);self.assertIsNone(calls[0][0])
    def test_failed_restore_blocks_later_mutations(self):
        result,_=self.exercise('tv','restore_readback_failed');self.assertEqual(result[0],126)
        self.assertEqual(os.environ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED'],'true')
    def test_exact_observed_watch_unsupported_routes_one_measured_trait_case_without_system_pass(self):
        result,_=self.exercise('watch','original_value_not_recognized',original_raw='unsupported')
        self.assertEqual(result[0],2);self.assertEqual(result[1]['status'],'original_value_not_recognized')
        self.assertTrue(result[1]['layout_stress']['passed']);self.assertFalse(result[1]['layout_stress']['system_setting_propagation'])
    def test_exact_observed_tv_unsupported_routes_real_photos_workflow_with_unchanged_cap(self):
        result,_=self.exercise('tv','original_value_not_recognized',original_raw='unsupported')
        self.assertEqual(result[0],2);self.assertTrue(result[1]['layout_stress']['passed'])
        self.assertFalse(result[1]['layout_stress']['system_setting_propagation'])
    def test_unknown_response_or_other_platform_does_not_invent_trait_fallback(self):
        for platform,raw in [('watch','unknown'),('vision','unsupported'),('tv','unknown')]:
            result,_=self.exercise(platform,'original_value_not_recognized',original_raw=raw)
            self.assertEqual(result[0],2);self.assertNotIn('layout_stress',result[1])
    def test_zero_exit_without_actual_growth_proof_cannot_qualify_layout(self):
        for output in ['', 'WATCH_PUBLIC_TRAIT_PROOF {"trait":"accessibility5"}', 'WATCH_PUBLIC_TRAIT_PROOF malformed']:
            result,_=self.exercise('watch','original_value_not_recognized',original_raw='unsupported',output=output)
            self.assertEqual(result[0],2);self.assertFalse(result[1]['layout_stress']['passed'])
            self.assertNotEqual(os.environ.get('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED'),'true')
    def test_trait_runner_unknown_cleanup_or_exception_stops_later_commands(self):
        for platform in ['watch','tv']:
            for key in ['unknown','raises']:
                os.environ.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED',None)
                result,_=self.exercise(platform,'original_value_not_recognized',original_raw='unsupported',**{key:True})
                self.assertEqual(result[0],126);self.assertEqual(os.environ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED'],'true')

if __name__=='__main__':unittest.main()
