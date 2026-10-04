"""Command-routing checks; these do not substitute for Apple compilation."""
import contextlib,io,json,os,runpy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))

class PlatformPreflightTests(unittest.TestCase):
    def setUp(self):
        isolation=patch.dict(os.environ);isolation.start();self.addCleanup(isolation.stop)
        for key in ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED','QRCATCHER_OWNED_PROCESS_BARRIER','GITHUB_ENV','GITHUB_WORKSPACE']:os.environ.pop(key,None)
    def test_unknown_system_size_cleanup_blocks_following_mutations(self):
        workflow=(ROOT/'.github/workflows/apple-platforms.yml').read_text()
        named={block.splitlines()[0]:block for block in workflow.split('    - name: ')[1:]}
        for name,block in named.items():
            if 'run_bounded.py' in block or 'run_watch_platform_tests.py' in block or 'run_vision_ui_cases.py' in block or 'run_tv_platform_tests.sh' in block or 'run_ios_platform_ui.sh' in block:
                self.assertIn("env.QRCATCHER_OWNED_CLEANUP_UNCONFIRMED != 'true'",block)
                self.assertEqual(block.split('      run: |\n',1)[1].splitlines()[0].strip(),'python3 scripts/owned_process_barrier.py --check')
        for platform,name in [('VISION','Stop the Vision simulator before other platform tests'),('TV','Stop TV simulator before phone and iPad tests'),('WATCH','Stop Watch simulator before phone and iPad matrix')]:
            self.assertIn("env."+platform+"_SIZE_CLEANUP_UNCONFIRMED != 'true'",named[name])
        text=(ROOT/'scripts/run_tv_platform_tests.sh').read_text()
        self.assertLess(text.index('SIZE_PROBE_EXIT" -ne 2'),text.index('privacy "$DEVICE" revoke'))
        self.assertLess(text.index('TV_SIZE_CLEANUP_UNCONFIRMED=true'),text.index('scripts/run_native_size_case.py'))
    def execute(self,failed_scheme=None,embedding_failure=False,cleanup=None):
        calls=[]
        def command(args,seconds,**options):
            calls.append(args)
            if args[0]=='xcodebuild':
                self.assertEqual(args[1],'build-for-testing');self.assertNotIn('-sdk',args)
                self.assertIn('CODE_SIGNING_ALLOWED=NO',args)
                code=1 if args[args.index('-scheme')+1]==failed_scheme else 0
            else:
                self.assertEqual(args,['python3','scripts/verify_embedded_watch.py','simulator'])
                code=int(embedding_failure)
            detail={'exit':code,'state':'completed','cleanup_confirmed':True}
            if cleanup and len(calls)==1:
                code=126;detail.update(exit=code,state='cleanup_unconfirmed')
                if cleanup=='missing':detail.pop('cleanup_confirmed')
                else:detail['cleanup_confirmed']=False
            return code,'synthetic compiler/verification result',detail
        with tempfile.TemporaryDirectory() as folder:
            old=Path.cwd()
            try:
                os.chdir(folder)
                with patch('watch_process.execute',side_effect=command),contextlib.redirect_stdout(io.StringIO()):
                    if failed_scheme or embedding_failure or cleanup:
                        with self.assertRaises(SystemExit):runpy.run_path(str(ROOT/'scripts/compile_platform_preflight.py'),run_name='__main__')
                    else:runpy.run_path(str(ROOT/'scripts/compile_platform_preflight.py'),run_name='__main__')
                report=json.loads(Path('build/preflight/summary.json').read_text())
            finally:os.chdir(old)
        return calls,report
    def test_all_native_and_shipping_test_schemes_compile_before_matrix(self):
        calls,report=self.execute()
        self.assertEqual([a[a.index('-scheme')+1] for a in calls if a[0]=='xcodebuild'],
                         ['QRCatcher','QRCatcherMac','QRCatcherMacSandbox','QRCatcherWatch','QRCatcherVision','QRCatcherTV'])
        self.assertEqual(calls[1],['python3','scripts/verify_embedded_watch.py','simulator']);self.assertTrue(report['passed'])
    def test_compiler_failure_stays_red_while_other_schemes_are_checked(self):
        calls,report=self.execute('QRCatcher')
        self.assertEqual(len(calls),6);self.assertFalse(report['passed'])
    def test_embedding_failure_stays_red_and_other_compilers_still_run(self):
        calls,report=self.execute(embedding_failure=True)
        self.assertEqual(len(calls),7);self.assertFalse(report['passed'])
    def test_missing_or_false_cleanup_proof_blocks_every_later_compiler(self):
        for cleanup in ['missing','false']:
            with self.subTest(cleanup=cleanup):
                calls,report=self.execute(cleanup=cleanup)
                self.assertEqual(len(calls),1);self.assertTrue(report['cleanup_unconfirmed']);self.assertFalse(report['passed'])
                self.assertTrue(all(row['state']=='blocked_owned_process_cleanup_unconfirmed' for row in report['operations'][1:]))

if __name__=='__main__':unittest.main()
