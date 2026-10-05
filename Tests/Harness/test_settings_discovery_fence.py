"""LOCAL PROPOSAL: disposable shell/FD/process fixtures; no Apple execution."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
DEVICE = '11111111-2222-4333-8444-555555555555'
FILES = ['run_settings_discovery_fenced.sh', 'run_settings_discovery_fenced.py', 'settings_discovery_fence.py',
         'owned_process_barrier.py', 'owned_process_group.py', 'watch_process.py', 'atomic_json.py',
         'vision_command_fence.py', 'run_bounded.py']
FIXTURE = '''import os
from owned_process_barrier import blocked

def discover(platform, device, runner):
    if blocked(): raise ValueError('Controller precheck unexpectedly blocked')
    command=['git', 'rev-parse', 'HEAD']
    code, text, operation=runner(command, 5, output_limit=1024, tail_limit=1024, echo=False)
    return dict(source=os.environ['GITHUB_SHA'], device=device, platform=platform,
                setting_change_attempted=False, system_propagation_qualified=False,
                status='read_only_discovery_stopped_unqualified', operations=[dict(operation=operation)])
'''


class SettingsDiscoveryFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in ['scripts', 'build', 'bin']: (self.root / name).mkdir()
        for name in FILES: shutil.copyfile(ROOT / 'scripts' / name, self.root / 'scripts' / name)
        self.env = dict(os.environ, GITHUB_WORKSPACE=str(self.root), GITHUB_ENV=str(self.root/'github-env'),
                        GITHUB_REPOSITORY='100mango/QRCatcher', GITHUB_SHA='a'*40, GITHUB_WORKFLOW_SHA='a'*40,
                        EVIDENCE_SCOPE='watchos', WATCH_SIMULATOR_ID=DEVICE, TV_SIMULATOR_ID=DEVICE,
                        QRCATCHER_OWNED_PROCESS_BARRIER=str(self.root/'build/owned-process-cleanup.json'),
                        PATH=str(self.root/'bin')+os.pathsep+os.environ['PATH'], PYTHONDONTWRITEBYTECODE='1')
        self.env.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED', None)
        self.env.pop('PYTHONPATH', None)
        (self.root/'scripts/discover_native_settings.py').write_text(FIXTURE)
        self.stub = self.root/'bin/git'
        self.stub.write_text('#!'+sys.executable+'\nfrom pathlib import Path\nPath("called").write_text("yes")\nprint("'+'a'*40+'")\n')
        self.stub.chmod(0o755)
        self.latch = self.root/'build/settings-discovery-inflight.json'

    def argv(self, platform='watch', origin=None):
        start = time.monotonic() if origin is None else origin
        return ['bash', 'scripts/run_settings_discovery_fenced.sh', platform, DEVICE, format(start, '.6f')]

    def shell(self, platform='watch', origin=None):
        return subprocess.run(self.argv(platform, origin), cwd=self.root, env=self.env, capture_output=True, text=True, timeout=8)

    def blocked_later(self):
        p = subprocess.run([sys.executable, 'scripts/run_bounded.py', '1', 'git', 'rev-parse', 'HEAD'],
                           cwd=self.root, env=self.env, capture_output=True, text=True, timeout=4)
        self.assertEqual(p.returncode, 126, p.stdout+p.stderr)

    def test_confirmed_completion_clears_only_own_latch_and_never_returns_green(self):
        p = self.shell(); self.assertEqual(p.returncode, 2, p.stdout+p.stderr)
        self.assertFalse(self.latch.exists())
        r = json.loads((self.root/'build/settings-discovery-watch-fence.json').read_text())
        self.assertTrue(r['cleanup_confirmed']); self.assertFalse(r['system_propagation_qualified'])
        self.assertEqual(r['operations'][0]['command'], ['git','rev-parse','HEAD'])
        self.assertEqual(r['operations'][0]['timeout_seconds'], 5)
        self.assertEqual(p.stdout.index('SETTINGS_FENCE_BEFORE_PYTHON') < p.stdout.index('SETTINGS_FENCE_PYTHON_ENTRY'), True)
        p = self.shell(); self.assertEqual(p.returncode, 126)

    def test_tv_scope_has_unchanged_eighteen_minute_budget(self):
        self.env['EVIDENCE_SCOPE']='tvos'
        p=self.shell('tv'); self.assertEqual(p.returncode,2,p.stdout+p.stderr)
        r=json.loads((self.root/'build/settings-discovery-tv-fence.json').read_text())
        self.assertEqual(r['parent_deadline_monotonic']-float(r['parent_started_monotonic']),1080)

    def test_insufficient_original_parent_budget_never_spawns(self):
        p=self.shell(origin=time.monotonic()-1200)
        self.assertEqual(p.returncode,2,p.stdout+p.stderr)
        self.assertFalse((self.root/'called').exists()); self.assertFalse(self.latch.exists())
        r=json.loads((self.root/'build/settings-discovery-watch-fence.json').read_text())
        self.assertEqual(r['operations'],[])
        self.assertEqual(r['reason'],'insufficient_existing_parent_step_budget')
        self.assertEqual(r['required_admission_seconds'],210)

    def test_future_clock_never_spawns_and_is_not_reset(self):
        p=self.shell(origin=time.monotonic()+50)
        self.assertEqual(p.returncode,126); self.assertTrue(self.latch.exists())
        self.assertFalse((self.root/'called').exists()); self.blocked_later()

    def test_pre_python_failure_leaves_latch_and_blocks_fresh_interpreter(self):
        stub=self.root/'bin/python3';stub.write_text('#!/bin/sh\nexit 73\n');stub.chmod(0o755)
        p=self.shell();self.assertEqual(p.returncode,126)
        self.assertTrue(self.latch.exists()); self.assertFalse((self.root/'called').exists())
        self.blocked_later()

    def test_missing_global_patch_refuses_before_any_owned_command(self):
        path=self.root/'scripts/owned_process_barrier.py'
        path.write_text(path.read_text().replace('SETTINGS_DISCOVERY_FENCE_VERSION = 1','SETTINGS_DISCOVERY_FENCE_VERSION = 0'))
        p=self.shell();self.assertEqual(p.returncode,126)
        self.assertTrue(self.latch.exists());self.assertFalse((self.root/'called').exists())

    def test_existing_foreign_vision_or_partial_latch_is_not_overwritten(self):
        for path in [self.latch,self.root/'build/vision-command-inflight.json',self.root/'build/fixture-query-inflight.json']:
            path.write_bytes(b'')
            p=self.shell();self.assertEqual(p.returncode,126);self.assertEqual(path.read_bytes(),b'')
            self.assertFalse((self.root/'called').exists());path.unlink()

    def test_wrong_command_order_and_ui_selection_never_spawn(self):
        for command in ["['xcrun','simctl','shutdown',device]", "['git','diff','--quiet','HEAD','--']",
                        "['env','TEST_RUNNER_QRCATCHER_SETTINGS_DISCOVERY={}','xcodebuild','test']"]:
            (self.root/'scripts/discover_native_settings.py').write_text(FIXTURE.replace("['git', 'rev-parse', 'HEAD']",command))
            p=self.shell();self.assertEqual(p.returncode,126,p.stdout+p.stderr)
            self.assertTrue(self.latch.exists());self.assertFalse((self.root/'called').exists())
            self.blocked_later();self.latch.unlink()
            (self.root/'github-env').unlink(missing_ok=True)

    def test_unknown_cleanup_and_report_loss_never_clear(self):
        path=self.root/'scripts/watch_process.py'
        path.write_text(path.read_text()+'\nstop_group = lambda process: False\n')
        p=self.shell();self.assertEqual(p.returncode,126,p.stdout+p.stderr)
        self.assertTrue(self.latch.exists());self.blocked_later()

    def test_unexpected_prompt_marker_stops_without_clearing(self):
        self.stub.write_text(self.stub.read_text()+'print("QRCATCHER_UNEXPECTED_INTERRUPTION_ABORT_BEFORE_UI_ACTION")\n')
        p=self.shell();self.assertEqual(p.returncode,126,p.stdout+p.stderr)
        self.assertTrue(self.latch.exists());self.blocked_later()

    def test_missing_or_replaced_active_latch_never_admits_generic_or_direct_command(self):
        source=self.root/'scripts/discover_native_settings.py'
        source.write_text(FIXTURE.replace("    command=", "    from pathlib import Path\n    Path('build/settings-discovery-inflight.json').unlink()\n    if not blocked(): raise RuntimeError('Missing active identity was accepted')\n    command="))
        p=self.shell();self.assertEqual(p.returncode,126,p.stdout+p.stderr)
        self.assertFalse((self.root/'called').exists())
        self.assertIn('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED=true',(self.root/'github-env').read_text())

    def test_parent_replacement_keeps_active_identity_blocked(self):
        source=self.root/'scripts/discover_native_settings.py'
        source.write_text(FIXTURE.replace("    command=", "    from pathlib import Path\n    Path('build').rename('old-build'); Path('build').mkdir()\n    if not blocked(): raise RuntimeError('Replaced active parent was accepted')\n    command="))
        p=self.shell();self.assertEqual(p.returncode,126,p.stdout+p.stderr)
        self.assertFalse((self.root/'called').exists())
        self.assertTrue((self.root/'old-build/settings-discovery-inflight.json').exists())

    def test_receipt_failure_never_unlinks_latch(self):
        source=self.root/'scripts/discover_native_settings.py'
        source.write_text(FIXTURE.replace("    return dict(", "    from pathlib import Path\n    Path('build/settings-discovery-watch-fence.json').write_text('existing')\n    return dict("))
        p=self.shell();self.assertEqual(p.returncode,126,p.stdout+p.stderr)
        self.assertTrue(self.latch.exists());self.blocked_later()

    def outer_stop(self, bootstrap):
        if bootstrap:
            child=self.root/'bin/python3'
            child.write_text('#!/bin/sh\nprintf BOOTSTRAP_ENTERED > bootstrap-ready\nsleep 10\n');child.chmod(0o755)
            ready=self.root/'bootstrap-ready'
        else:
            self.stub.write_text('#!'+sys.executable+'\nimport os,time\nfrom pathlib import Path\nPath("owned-child.pid").write_text(str(os.getpid()))\ntime.sleep(10)\n')
            ready=self.root/'owned-child.pid'
        p=subprocess.Popen(self.argv(),cwd=self.root,env=self.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        child_pid=None
        try:
            deadline=time.monotonic()+3
            while time.monotonic()<deadline and not ready.exists():time.sleep(.02)
            self.assertTrue(ready.exists());self.assertTrue(self.latch.exists())
            if not bootstrap:child_pid=int(ready.read_text())
            os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=3)
            self.assertTrue(self.latch.exists());self.blocked_later()
        finally:
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=3)
            if child_pid:
                try:os.killpg(child_pid,signal.SIGKILL)
                except ProcessLookupError:pass

    def test_outer_stop_during_python_bootstrap_retains_preexisting_latch(self):self.outer_stop(True)
    def test_outer_stop_after_owned_child_spawn_retains_latch(self):self.outer_stop(False)

    def test_real_launcher_command_sequence_matches_the_narrow_fence(self):
        shutil.copyfile(ROOT/'scripts/discover_native_settings.py', self.root/'scripts/discover_native_settings.py')
        (self.root/'scripts/settings_build_provenance.py').write_text('def verify(platform, root): return {\"synthetic_fixture\": True}\n')
        (self.root/'build/WatchTests').mkdir(); (self.root/'QRCatcher.xcodeproj').mkdir()
        self.stub.write_text('#!'+sys.executable+'\nimport sys\nprint("'+ 'a'*40 +'") if sys.argv[1:] == ["rev-parse","HEAD"] else None\n')
        catalog={'com.apple.SyntheticSettingsFixture':dict(CFBundleIdentifier='com.apple.SyntheticSettingsFixture',
                    CFBundleDisplayName='Settings',CFBundleName='Fixture',ApplicationType='System')}
        inventory={'devices':{'com.apple.CoreSimulator.SimRuntime.watchOS-27-0':[
                    dict(udid=DEVICE,state='Booted',isAvailable=True)]}}
        from test_settings_navigation import navigation_fixture
        files={
            'xcrun': 'import sys\na=sys.argv[1:]\nif a == ["simctl","help","listapps"]: print("Usage: simctl listapps <device>")\n'
                     +'elif a == ["simctl","list","devices","-j"]: print('+repr(json.dumps(inventory))+')\n'
                     +'elif a == ["simctl","listapps","'+DEVICE+'"]: print('+repr(json.dumps(catalog))+')\n'
                     +'else: raise SystemExit(99)\n',
            'plutil': 'import sys\nfrom pathlib import Path\nPath(sys.argv[4]).write_bytes(Path(sys.argv[5]).read_bytes())\n',
            'xcodebuild': 'import os,json\nr=json.loads(os.environ["TEST_RUNNER_QRCATCHER_SETTINGS_DISCOVERY"])\n'
                     +'r.update(status="settings_screen_observed",original_value_restorable=False,setting_write_authorized=False,'
                     +'hierarchy="synthetic fixture",controls=[dict(type=1,identifier="fixture",label="Settings",value="")],screenshot_attached=True)\n'
                     +'r.update('+repr(navigation_fixture('watch'))+')\n'
                     +'print("QRCATCHER_SETTINGS_DISCOVERY "+json.dumps(r))\n'}
        for name,content in files.items():
            path=self.root/'bin'/name;path.write_text('#!'+sys.executable+'\n'+content);path.chmod(0o755)
        p=self.shell();self.assertEqual(p.returncode,2,p.stdout+p.stderr)
        self.assertFalse(self.latch.exists())
        receipt=json.loads((self.root/'build/settings-discovery-watch-fence.json').read_text())
        self.assertEqual(len(receipt['operations']),7)
        self.assertEqual(receipt['status'],'read_only_discovery_complete_unqualified')

    def test_nonzero_completed_command_stays_stopped_but_can_clear_cleanup(self):
        self.stub.write_text(self.stub.read_text()+'raise SystemExit(7)\n')
        p=self.shell();self.assertEqual(p.returncode,2,p.stdout+p.stderr)
        self.assertFalse(self.latch.exists())
        receipt=json.loads((self.root/'build/settings-discovery-watch-fence.json').read_text())
        self.assertEqual(receipt['operations'][0]['exit'],7)
        self.assertEqual(receipt['status'],'read_only_discovery_stopped_unqualified')

    def test_direct_execute_cannot_bypass_prepared_ordered_command(self):
        source=self.root/'scripts/discover_native_settings.py'
        source.write_text(FIXTURE.replace("    command=", "    from watch_process import execute\n    code,_,_=execute(['git','rev-parse','HEAD'],1)\n    if code != 126: raise RuntimeError('Unprepared command bypassed controller')\n    raise ValueError('Expected safe direct-call refusal')\n    command="))
        p=self.shell();self.assertEqual(p.returncode,126,p.stdout+p.stderr)
        self.assertFalse((self.root/'called').exists());self.assertTrue(self.latch.exists())

    def test_integrated_barrier_keeps_both_pending_owners(self):
        self.assertNotIn('run_settings_discovery_fenced', (ROOT/'.github/workflows/apple-platforms.yml').read_text())
        barrier=(ROOT/'scripts/owned_process_barrier.py').read_text()
        self.assertIn('SETTINGS_DISCOVERY_FENCE_VERSION', barrier)
        self.assertIn('fixture-query-inflight.json', barrier)
        self.assertIn('vision-command-inflight.json', barrier)


if __name__=='__main__':unittest.main()
