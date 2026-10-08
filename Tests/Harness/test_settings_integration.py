"""Portable provenance/export fixtures and source contracts; no Apple UI proof."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import settings_build_provenance as build
import export_settings_discovery as exporter


class SettingsBuildProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); (self.root/'build').mkdir()
        self.old = Path.cwd(); os.chdir(self.root); self.addCleanup(os.chdir, self.old)
        env = dict(GITHUB_WORKSPACE=str(self.root), GITHUB_REPOSITORY='100mango/QRCatcher',
                   GITHUB_SHA='a'*40, GITHUB_WORKFLOW_SHA='a'*40, EVIDENCE_SCOPE='watchos',
                   GITHUB_RUN_ID='1', GITHUB_RUN_ATTEMPT='1', GITHUB_JOB='platform', RUNNER_NAME='fixture')
        self.environment=patch.dict(os.environ, env, clear=True); self.environment.start(); self.addCleanup(self.environment.stop)
        self.clean=patch.object(build,'source_clean'); self.clean.start(); self.addCleanup(self.clean.stop)
        self.names=['QRCatcher.xcodeproj/project.pbxproj', 'QRCatcher.xcodeproj/xcshareddata/xcschemes/QRCatcherWatch.xcscheme', 'QRCatcherWatchUITests/QRCatcherWatchUITests.swift']
        for name in self.names:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic source fixture')

    def make_products(self):
        base=self.root/'build/WatchTests/Build/Products'
        bundle=base/'Debug-watchsimulator/QRCatcherWatchUITests-Runner.app/PlugIns/QRCatcherWatchUITests.xctest'
        bundle.mkdir(parents=True)
        (bundle/'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'QRCatcherWatchUITests'}))
        (bundle/'QRCatcherWatchUITests').write_bytes(b'synthetic compiled-product fixture, not a native executable')
        (base/'fixture.xctestrun').write_bytes(plistlib.dumps({'synthetic_fixture':True}))
        return bundle

    def completed(self):
        build.begin('watch'); bundle=self.make_products();build.finish('watch');return bundle

    def test_fresh_same_job_build_products_are_rechecked_without_binary_attestation(self):
        self.completed();value=build.verify('watch',self.root)
        self.assertTrue(value['same_job_fresh_build_verified']);self.assertFalse(value['binary_source_binding_verified'])
        self.assertEqual(len(value['products']),3)

    def test_fresh_tv_checkout_initializes_only_owned_build_directory(self):
        (self.root/'build').rmdir()
        os.environ['EVIDENCE_SCOPE']='tvos'
        for name in [self.names[1].replace('Watch','TV'),self.names[2].replace('Watch','TV')]:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic TV source fixture')
        build.begin('tv')
        value=build.read_state('tv',self.root)
        self.assertEqual(value['platform'],'tv');self.assertEqual(value['state'],'before_fresh_build')
        self.assertTrue(value['derived_data_was_absent']);self.assertFalse(value['binary_source_binding_verified'])
        self.assertEqual(sorted(path.name for path in (self.root/'build').iterdir()),['settings-build-tv.json'])
        self.assertEqual((self.root/'build').stat().st_mode & 0o777,0o700)
        with self.assertRaises(ValueError):build.begin('tv')

    def test_aliased_build_directory_never_receives_provenance(self):
        (self.root/'build').rmdir();other=self.root/'elsewhere';other.mkdir()
        (other/'keep').write_text('unchanged');(self.root/'build').symlink_to(other,target_is_directory=True)
        with self.assertRaises(ValueError):build.begin('watch')
        self.assertEqual([path.name for path in other.iterdir()],['keep'])
        self.assertEqual((other/'keep').read_text(),'unchanged')

    def test_dangling_build_alias_stops_before_creation(self):
        (self.root/'build').rmdir();other=self.root/'missing';(self.root/'build').symlink_to(other,target_is_directory=True)
        with self.assertRaises(ValueError):build.begin('watch')
        self.assertFalse(other.exists())

    def test_non_directory_build_path_is_not_overwritten(self):
        path=self.root/'build';path.rmdir();path.write_text('keep')
        with self.assertRaises((OSError,ValueError)):build.begin('watch')
        self.assertEqual(path.read_text(),'keep')

    def test_identity_or_source_rejection_does_not_create_build_directory(self):
        (self.root/'build').rmdir()
        with patch.dict(os.environ,{'GITHUB_REPOSITORY':'other/repo'}),self.assertRaises(ValueError):build.begin('watch')
        self.assertFalse((self.root/'build').exists())
        with patch.object(build,'source_clean',side_effect=ValueError('not current source')),self.assertRaises(ValueError):build.begin('watch')
        self.assertFalse((self.root/'build').exists())

    def test_actual_tv_workflow_build_block_on_fresh_checkout(self):
        # Execute the actual unchanged workflow shell with the real provenance,
        # barrier and bounded-owner scripts. Only git/compiler commands are
        # doubles; the resulting product bytes never qualify native compilation.
        (self.root/'build').rmdir();os.environ['EVIDENCE_SCOPE']='tvos'
        for name in [self.names[1].replace('Watch','TV'),self.names[2].replace('Watch','TV')]:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic TV source fixture')
        scripts=self.root/'scripts';scripts.mkdir()
        for name in ['settings_build_provenance.py','atomic_json.py','watch_process.py','owned_process_group.py','owned_process_barrier.py','run_bounded.py']:
            shutil.copy2(ROOT/'scripts'/name,scripts/name)
        binary=self.root/'bin';binary.mkdir()
        def command(name,body):
            path=binary/name;path.write_text('#!'+sys.executable+'\n'+body);path.chmod(0o755)
        command('git',"import sys\nif sys.argv[1:]==['rev-parse','HEAD']:print('a'*40)\nelif sys.argv[1:]!=['diff','--quiet','HEAD','--']:raise SystemExit(9)\n")
        command('xcodebuild',"""import json,plistlib,sys
from pathlib import Path
if sys.argv[1:]!=['build-for-testing','-project','QRCatcher.xcodeproj','-scheme','QRCatcherTV','-configuration','Debug','-derivedDataPath','build/TVTests','-destination','generic/platform=tvOS Simulator','ARCHS=arm64','CODE_SIGNING_ALLOWED=NO']:raise SystemExit('wrong actual compiler routing')
receipt=json.loads(Path('build/settings-build-tv.json').read_text())
if receipt['state']!='before_fresh_build' or Path('build/TVTests').exists():raise SystemExit('compiler ran before fresh provenance')
Path('compiler-called').write_text('one')
base=Path('build/TVTests/Build/Products');bundle=base/'Debug-appletvsimulator/QRCatcherTVUITests-Runner.app/PlugIns/QRCatcherTVUITests.xctest';bundle.mkdir(parents=True)
(bundle/'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'QRCatcherTVUITests'}))
(bundle/'QRCatcherTVUITests').write_bytes(b'synthetic compiler output, never Apple runtime proof')
(base/'fixture.xctestrun').write_bytes(plistlib.dumps({'synthetic':True}))
app=base/'Debug-appletvsimulator/QRCatcherTV.app';app.mkdir()
(app/'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps({'NSPrivacyAccessedAPITypes':[{'NSPrivacyAccessedAPIType':'NSPrivacyAccessedAPICategoryUserDefaults','NSPrivacyAccessedAPITypeReasons':['CA92.1']}]}))
""")
        workflow=(ROOT/'.github/workflows/apple-platforms.yml').read_text()
        block=next(block for block in workflow.split('    - name: ')[1:] if 'settings_build_provenance.py begin tv' in block)
        shell='\n'.join(line[8:] for line in block.split('      run: |\n',1)[1].splitlines())+'\n'
        env=dict(os.environ,PATH=str(binary)+os.pathsep+os.environ.get('PATH','/usr/bin:/bin'),
                 QRCATCHER_OWNED_PROCESS_BARRIER=str(self.root/'build/owned-process-cleanup.json'))
        result=subprocess.run(['/bin/bash','-e','-c',shell],cwd=self.root,env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('VERIFIED_TV_BUNDLED_REQUIRED_REASON',result.stdout)
        self.assertEqual((self.root/'compiler-called').read_text(),'one')
        receipt=build.verify('tv',self.root)
        self.assertEqual(receipt['state'],'fresh_build_completed')
        self.assertFalse(receipt['binary_source_binding_verified'])
        # A repeat invocation is rejected before compiler entry, not adopted.
        (self.root/'compiler-called').unlink()
        repeat=subprocess.run(['/bin/bash','-e','-c',shell],cwd=self.root,env=env,capture_output=True,text=True,timeout=20)
        self.assertNotEqual(repeat.returncode,0);self.assertFalse((self.root/'compiler-called').exists())

    def test_existing_derived_directory_cannot_be_reused_or_removed(self):
        path=self.root/'build/WatchTests';path.mkdir()
        with self.assertRaises(ValueError):build.begin('watch')
        self.assertTrue(path.exists())

    def test_changed_compiled_bytes_stop_discovery(self):
        bundle=self.completed();(bundle/'QRCatcherWatchUITests').write_bytes(b'changed')
        with self.assertRaises(ValueError):build.verify('watch',self.root)

    def test_changed_test_source_stops_discovery(self):
        self.completed();(self.root/self.names[-1]).write_text('changed source')
        with self.assertRaises(ValueError):build.verify('watch',self.root)

    def test_source_change_during_build_is_rejected(self):
        build.begin('watch');self.make_products();(self.root/self.names[0]).write_text('changed')
        with self.assertRaises(ValueError):build.finish('watch')

    def test_other_job_or_attempt_cannot_reuse_receipt(self):
        self.completed()
        for key in ['GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_JOB','RUNNER_NAME','GITHUB_SHA']:
            with self.subTest(key=key),patch.dict(os.environ,{key:'different'}),self.assertRaises(ValueError):build.verify('watch',self.root)

    def test_multiple_descriptors_are_ambiguous(self):
        self.completed();base=self.root/'build/WatchTests/Build/Products';(base/'other.xctestrun').write_bytes(b'other')
        with self.assertRaises(ValueError):build.verify('watch',self.root)

    def test_product_symlink_is_rejected(self):
        bundle=self.completed();p=bundle/'QRCatcherWatchUITests';p.unlink();p.symlink_to(self.root/self.names[-1])
        with self.assertRaises(ValueError):build.verify('watch',self.root)

    def test_missing_build_completion_is_not_provenance(self):
        build.begin('watch');self.make_products()
        with self.assertRaises(ValueError):build.verify('watch',self.root)

    def test_repeat_finish_and_other_watch_endpoints_are_rejected(self):
        self.completed()
        with self.assertRaises(ValueError):build.finish('watch')
        with patch.dict(os.environ,{'EVIDENCE_SCOPE':'watchos_40'}),self.assertRaises(ValueError):build.verify('watch',self.root)

    def unsupported(self, **changes):
        device='11111111-2222-4333-8444-555555555555'
        value=dict(device=device,status='original_value_not_recognized',original_raw='unsupported',
                   requested_largest=None,observed_original=None,ui_executed=False,
                   operations=[{'label':'help'},{'label':'device_inventory'},
                               {'label':'read_original','output':'unsupported\n','operation':dict(command=['xcrun','simctl','ui',device,'content_size'],exit=0,state='completed',cleanup_confirmed=True)}])
        value.update(changes);p=self.root/'build/watch-runtime/system-content-size.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(value))
        return device,p

    def test_only_exact_completed_unsupported_read_admits_discovery(self):
        device,_=self.unsupported();self.assertTrue(build.observed_unsupported('watch',device))
        self.assertFalse(build.observed_unsupported('watch','different-device'))

    def test_missing_uncertain_or_setter_path_never_admits_discovery(self):
        self.assertFalse(build.observed_unsupported('watch','missing'))
        for changes in [dict(cleanup_unconfirmed=True),dict(requested_largest='accessibility5'),dict(ui_executed=True),dict(original_raw='unknown')]:
            device,_=self.unsupported(**changes);self.assertFalse(build.observed_unsupported('watch',device))

    def test_failed_or_wrong_read_command_cannot_admit_discovery(self):
        device,p=self.unsupported();value=json.loads(p.read_text());value['operations'][-1]['operation']['exit']=124;p.write_text(json.dumps(value))
        self.assertFalse(build.observed_unsupported('watch',device))
        value['operations'][-1]['operation']['exit']=0;value['operations'][-1]['operation']['command'].append('accessibility5');p.write_text(json.dumps(value))
        self.assertFalse(build.observed_unsupported('watch',device))


class SettingsExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.old=Path.cwd();os.chdir(self.root);self.addCleanup(os.chdir,self.old)
        self.source=self.root/'build/settings-discovery-watch';self.source.mkdir(parents=True)
        self.out=self.root/'build/evidence';self.out.mkdir()
        self.report={'settings_ui':{'screenshot_attached':True,'setting_change_attempted':False,'system_propagation_qualified':False,'screenshot_pane':'Text Size','navigation_complete':True}}
        (self.source/'report.json').write_text(json.dumps(self.report))
        result=self.root/'WatchSettingsDiscovery.xcresult';result.mkdir();(result/'Info.plist').write_bytes(b'fixture')
        self.calls=[];self.mode='ok'

    def runner(self,args,seconds,**options):
        self.calls.append((args,seconds));self.assertLessEqual(seconds,20)
        if args[0]=='xcrun':
            folder=Path(args[-1]);folder.mkdir();(folder/'image.png').write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            records=[{'exportedFileName':'image.png','suggestedHumanReadableName':'watch-settings-discovery'}]
            if self.mode=='duplicate':records*=2
            if self.mode=='escape':records[0]['exportedFileName']='../../outside.png'
            (folder/'manifest.json').write_text(json.dumps(records))
        elif args[0]=='sips':Path(args[-1]).write_bytes(b'\xff\xd8'+b'x'*(160000 if self.mode=='oversize' else 100))
        else:self.fail('Unexpected command')
        return 0,'',{'command':args,'timeout_seconds':seconds,'exit':0,'state':'completed','cleanup_confirmed':True}

    def exercise(self,available=300000,blocked=False,elapsed=0):
        with patch.object(exporter,'blocked',return_value=blocked):
            return exporter.export_settings('watchos',self.out,available,time.monotonic()-elapsed,runner=self.runner)

    def test_one_bounded_whole_frame_retained_without_qualification(self):
        value=self.exercise();self.assertEqual(value['status'],'read_only_evidence_retained_unqualified')
        self.assertFalse(value['system_propagation_qualified']);self.assertEqual(len(self.calls),2)
        self.assertLessEqual(value['bytes'],300000);self.assertTrue(value['image_is_whole_frame'])

    def test_uncertainty_retains_only_local_metadata_and_no_tool(self):
        value=self.exercise(blocked=True);self.assertEqual(value['status'],'metadata_only_cleanup_unconfirmed')
        self.assertFalse(self.calls);self.assertEqual(len(value['files']),1)

    def test_exhausted_existing_export_deadline_stops_before_tools(self):
        value=self.exercise(elapsed=179);self.assertIn('incomplete',value['status']);self.assertFalse(self.calls)

    def test_insufficient_bytes_never_displace_ordinary_proof(self):
        (self.out/'ordinary.jpg').write_bytes(b'ordinary proof')
        value=self.exercise(available=1);self.assertIn('incomplete',value['status']);self.assertFalse(self.calls)
        self.assertEqual((self.out/'ordinary.jpg').read_bytes(),b'ordinary proof')

    def test_duplicate_or_escaped_frame_stops_before_conversion(self):
        self.mode='duplicate';value=self.exercise();self.assertIn('incomplete',value['status']);self.assertEqual(len(self.calls),1)

    def test_oversized_frame_is_not_retained(self):
        self.mode='oversize';value=self.exercise();self.assertIn('incomplete',value['status'])
        self.assertFalse(any(item['name'].endswith('.jpg') for item in value['files']))

    def test_unknown_screenshot_receipt_does_not_export(self):
        (self.source/'report.json').write_text('{}');value=self.exercise()
        self.assertEqual(value['status'],'metadata_only_no_verified_screenshot_receipt');self.assertFalse(self.calls)

    def test_redirection_of_metadata_stops(self):
        p=self.source/'report.json';p.unlink();p.symlink_to(self.root/'outside')
        value=self.exercise();self.assertIn('incomplete',value['status']);self.assertFalse(self.calls)


class SettingsIntegrationSourceContracts(unittest.TestCase):
    def test_owned_driver_placement_preserves_ordinary_flows_and_failed_size_exit(self):
        watch=(ROOT/'scripts/run_watch_platform_tests.py').read_text()
        self.assertLess(watch.index("run_case('watch'"),watch.index('run_settings_discovery_fenced.sh'))
        self.assertLess(watch.index('run_settings_discovery_fenced.sh'),watch.index("run(['xcrun','simctl','delete'"))
        self.assertIn("scope=='watchos' and size_exit==2",watch)
        self.assertIn('subprocess.run([',watch);self.assertNotIn('start_new_session',watch)
        tv=(ROOT/'scripts/run_tv_platform_tests.sh').read_text()
        self.assertLess(tv.index('testExplicitlyRevokedPhotosRecovery'),tv.index('run_settings_discovery_fenced.sh'))
        self.assertIn('exit "$SIZE_PROBE_EXIT"',tv);self.assertIn('export TV_SIMULATOR_ID="$DEVICE"',tv)

    def test_original_clock_and_existing_step_limits_are_retained(self):
        workflow=(ROOT/'.github/workflows/apple-platforms.yml').read_text()
        self.assertEqual(workflow.count('export QRCATCHER_RUNTIME_PARENT_START='),2)
        self.assertIn('timeout-minutes: 22',workflow);self.assertIn('timeout-minutes: 18',workflow)
        self.assertIn('max-parallel: 1',workflow)
        self.assertIn('settings_build_provenance.py begin watch',workflow)
        self.assertIn('settings_build_provenance.py finish tv',workflow)

    def test_shell_checks_all_durable_pending_owners_before_python(self):
        shell=(ROOT/'scripts/run_settings_discovery_fenced.sh').read_text()
        for marker in ['fixture-query-inflight.json','vision-command-inflight.json','owned-process-cleanup.json']:
            self.assertLess(shell.index(marker),shell.index('python3 -u'))

    def test_settings_does_not_displace_ordinary_export_or_expand_allocation(self):
        source=(ROOT/'scripts/export_ios_platform_screenshots.py').read_text()
        self.assertLess(source.index("summary['missing_import_audit_pairs']="),source.index('summary[\'settings_discovery\']=export_settings'))
        limits=json.loads((ROOT/'scripts/evidence-allocation.json').read_text())
        self.assertEqual(sum(limits['scope_limits_bytes'].values()),19800000)
        self.assertEqual(limits['whole_run_limit_bytes'],20000000)


if __name__=='__main__':unittest.main()
