"""Command contracts only; installed system-size support requires Apple runtime."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from run_native_size_case import run_case
from simulator_content_size import validate_ui_command

class NativeSizeCaseTests(unittest.TestCase):
    def setUp(self):
        isolation=patch.dict(os.environ);isolation.start();self.addCleanup(isolation.stop)
        for key in ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED','QRCATCHER_OWNED_PROCESS_BARRIER','GITHUB_ENV','GITHUB_WORKSPACE']:os.environ.pop(key,None)
    def exercise(self,platform,status='largest_ui_passed',precondition=True):
        device='11111111-2222-4333-8444-555555555555';calls=[]
        def probe(udid,path,command,cap,**kwargs):
            calls.append((command,cap))
            if precondition:validate_ui_command(command,device,kwargs['expected_ui'])
            else:self.assertIsNone(command)
            return {'status':status,'restore_verified':status=='largest_ui_passed'}
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'QRCatcher.xcodeproj').mkdir()
            for name in ['Watch','Vision','TV']:(folder/'build'/(name+'Tests')).mkdir(parents=True)
            old=Path.cwd()
            try:
                os.chdir(folder)
                with patch('run_native_size_case.probe',side_effect=probe):result=run_case(platform,device,precondition)
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

if __name__=='__main__':unittest.main()
