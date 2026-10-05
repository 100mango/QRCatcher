"""Executable probe/ownership doubles, never Apple simulator qualification."""
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
DEVICE='11111111-2222-4333-8444-555555555555'
FILES=['probe_vision_runtime.py','vision_command_fence.py','watch_process.py','owned_process_barrier.py',
       'owned_process_group.py','atomic_json.py','run_bounded.py','run_vision_fenced_command.py','run_vision_fenced_command.sh']


class VisionBootstrapFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'build').mkdir();(self.root/'scripts').mkdir();(self.root/'bin').mkdir()
        for name in FILES:shutil.copy2(ROOT/'scripts'/name,self.root/'scripts'/name)
        self.env={**os.environ,'PATH':str(self.root/'bin')+os.pathsep+os.environ['PATH'],
                  'GITHUB_WORKSPACE':str(self.root),'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_SHA':'a'*40,
                  'EVIDENCE_SCOPE':'visionos_files','GITHUB_ENV':str(self.root/'github-env'),
                  'QRCATCHER_OWNED_PROCESS_BARRIER':str(self.root/'build/owned-process-cleanup.json'),
                  'PYTHONOPTIMIZE':str(sys.flags.optimize),'MODE':'ok'}
        self.env.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED',None);self.env.pop('VISION_SIMULATOR_ID',None)
        self.program('git',"print('a'*40)\n")
        self.program('xcrun',r'''import json,os,sys,time
from pathlib import Path
args=sys.argv[1:];action=args[1];mode=os.environ['MODE']
with Path('calls.jsonl').open('a') as stream:stream.write(json.dumps(args)+'\n')
if action=='list':
 if mode=='inventory124':raise SystemExit(124)
 if mode=='malformed':print('invalid JSON');raise SystemExit(0)
 print(json.dumps({'devices':{'com.apple.CoreSimulator.SimRuntime.xrOS-27-0':[{'udid':'11111111-2222-4333-8444-555555555555','name':'Apple Vision Pro','state':'Booted' if mode.startswith('already') else 'Shutdown'}]}}))
elif action=='boot':
 if mode=='outer':Path('owned-child.pid').write_text(str(os.getpid()));time.sleep(20)
 if mode in {'boot124','timed','output'}:raise SystemExit(125 if mode=='output' else 124)
 if mode=='unknown':raise SystemExit(7)
 if mode.startswith('already'):
  print('An error was encountered processing the command (domain=com.apple.CoreSimulator.SimError, code=405):')
  print('Unable to boot device in current state: '+('Unknown' if mode=='already-bad' else 'Booted'))
  raise SystemExit(149)
elif action=='bootstatus':
 if mode=='status124':raise SystemExit(124)
else:raise SystemExit('Unexpected device command')
''')
        runner=self.root/'scripts/watch_process.py'
        runner.write_text(runner.read_text()+r'''
_original_execute=execute
def execute(args,seconds=120,**kwargs):
 code,output,operation=_original_execute(args,seconds,**kwargs)
 if args[:3]==['xcrun','simctl','boot']:
  if os.environ.get('MODE')=='timed':operation.update(state='timed_out',exit=124,elapsed_seconds=183.2);code=124
  if os.environ.get('MODE')=='late':operation.update(state='completed',exit=0,elapsed_seconds=180.01);code=0
  if os.environ.get('MODE')=='missing':operation.pop('elapsed_seconds',None)
  if os.environ.get('MODE')=='unclean':operation['cleanup_confirmed']=False
 return code,output,operation
''')

    def program(self,name,body):
        path=self.root/'bin'/name;path.write_text('#!'+sys.executable+'\n'+body);path.chmod(0o755)

    def run_probe(self,mode='ok'):
        self.env['MODE']=mode
        return subprocess.run([sys.executable,'scripts/probe_vision_runtime.py'],cwd=self.root,env=self.env,
                              capture_output=True,text=True,timeout=12)

    def calls(self):
        path=self.root/'calls.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def later_blocked(self):
        before=self.calls();self.env['MODE']='ok'
        probe=self.run_probe();self.assertEqual(probe.returncode,126,probe.stdout+probe.stderr)
        self.assertEqual(self.calls(),before)
        self.env['VISION_SIMULATOR_ID']=DEVICE
        for command in [[sys.executable,'scripts/run_bounded.py','2','xcrun','simctl','list','devices','available','-j'],
                        [sys.executable,'scripts/run_bounded.py','2','xcrun','simctl','shutdown',DEVICE],
                        ['bash','-c','. scripts/run_vision_fenced_command.sh shutdown']]:
            result=subprocess.run(command,cwd=self.root,env=self.env,capture_output=True,text=True,timeout=8)
            self.assertEqual(result.returncode,126,result.stdout+result.stderr);self.assertEqual(self.calls(),before)

    def test_original_order_caps_and_target_complete_once(self):
        result=self.run_probe();self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(self.calls(),[['simctl','list','devices','available','-j'],['simctl','boot',DEVICE],['simctl','bootstatus',DEVICE,'-b']])
        report=json.loads((self.root/'build/vision-runtime/runtime.json').read_text())
        self.assertTrue(report['ready']);self.assertEqual([x['timeout_seconds'] for x in report['operations']],[30,180,420])
        self.assertTrue(all(x['device_command_completion_confirmed'] for x in report['operations']))
        self.assertFalse((self.root/'build/vision-command-inflight.json').exists())

    def test_exact_already_booted_response_still_requires_bootstatus(self):
        result=self.run_probe('already');self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual([x[1] for x in self.calls()],['list','boot','bootstatus'])

    def test_boot_timeout_with_host_cleanup_true_stops_before_bootstatus(self):
        result=self.run_probe('timed');self.assertEqual(result.returncode,126,result.stdout+result.stderr)
        self.assertEqual([x[1] for x in self.calls()],['list','boot'])
        row=json.loads((self.root/'build/vision-runtime/runtime.json').read_text())['operations'][-1]
        self.assertEqual(row['state'],'timed_out');self.assertEqual(row['exit'],124);self.assertTrue(row['cleanup_confirmed'])
        self.assertFalse(row['device_command_completion_confirmed']);self.later_blocked()

    def test_child124_unknown_late_output_and_incomplete_outcomes_stop(self):
        for mode in ['boot124','unknown','late','output','missing','unclean','already-bad']:
            with self.subTest(mode=mode):
                # Recreate only this test's owned synthetic workspace between independent cases.
                case=VisionBootstrapFenceTests('test_original_order_caps_and_target_complete_once');case.setUp()
                try:
                    result=case.run_probe(mode);self.assertEqual(result.returncode,126,result.stdout+result.stderr)
                    self.assertEqual([x[1] for x in case.calls()],['list','boot']);case.later_blocked()
                finally:case.doCleanups()

    def test_inventory_and_bootstatus_uncertainty_block_fresh_reloads(self):
        for mode,count in [('inventory124',1),('malformed',1),('status124',3)]:
            with self.subTest(mode=mode):
                case=VisionBootstrapFenceTests('test_original_order_caps_and_target_complete_once');case.setUp()
                try:
                    result=case.run_probe(mode);self.assertEqual(result.returncode,126,result.stdout+result.stderr)
                    self.assertEqual(len(case.calls()),count);case.later_blocked()
                finally:case.doCleanups()

    def test_existing_barrier_blocks_even_inventory(self):
        (self.root/'build/owned-process-cleanup.json').write_text('{}')
        result=self.run_probe();self.assertEqual(result.returncode,126);self.assertEqual(self.calls(),[])

    def test_partial_claim_write_failure_never_starts_device_command(self):
        script=self.root/'scripts/vision_command_fence.py'
        script.write_text(script.read_text()+"\ndef fail_sync(fd):\n raise OSError('injected marker sync failure')\nos.fsync=fail_sync\n")
        result=self.run_probe();self.assertEqual(result.returncode,126,result.stdout+result.stderr)
        self.assertEqual(self.calls(),[]);self.later_blocked()

    def test_outer_kill_retains_claim_and_blocks_every_fresh_entry(self):
        self.env['MODE']='outer'
        process=subprocess.Popen([sys.executable,'scripts/probe_vision_runtime.py'],cwd=self.root,env=self.env,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        pid=None
        try:
            deadline=time.monotonic()+6
            while time.monotonic()<deadline and not (self.root/'owned-child.pid').exists():time.sleep(.02)
            self.assertTrue((self.root/'owned-child.pid').exists())
            pid=int((self.root/'owned-child.pid').read_text());process.terminate();process.communicate(timeout=4)
            self.assertEqual([x[1] for x in self.calls()],['list','boot']);self.later_blocked()
        finally:
            if process.poll() is None:process.kill();process.communicate(timeout=4)
            if pid is not None:
                try:os.killpg(pid,signal.SIGKILL)
                except ProcessLookupError:pass

    def test_outer_kill_between_successful_phases_has_no_clear_gap(self):
        for needle in ["runtime, device = run('inventory', inventory)", "run('boot', boot)"]:
            with self.subTest(after=needle):
                case=VisionBootstrapFenceTests('test_original_order_caps_and_target_complete_once');case.setUp()
                process=None
                try:
                    path=case.root/'scripts/probe_vision_runtime.py'
                    text=path.read_text().replace('import json','import json\nimport time',1)
                    text=text.replace(needle,needle+"\n        Path('phase-completed').touch(); time.sleep(20)")
                    path.write_text(text)
                    process=subprocess.Popen([sys.executable,'scripts/probe_vision_runtime.py'],cwd=case.root,env=case.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                    deadline=time.monotonic()+6
                    while time.monotonic()<deadline and not (case.root/'phase-completed').exists():time.sleep(.02)
                    self.assertTrue((case.root/'phase-completed').exists())
                    process.terminate();process.communicate(timeout=4)
                    before=len(case.calls());self.assertEqual(before,1 if 'inventory' in needle else 2)
                    case.later_blocked();self.assertEqual(len(case.calls()),before)
                finally:
                    if process is not None and process.poll() is None:process.kill();process.communicate(timeout=4)
                    case.doCleanups()

    def test_partial_bootstrap_cannot_clear_completed_phase_receipt(self):
        for needle,count in [("runtime, device = run('inventory', inventory)",1),("run('boot', boot)",2)]:
            with self.subTest(after=needle):
                case=VisionBootstrapFenceTests('test_original_order_caps_and_target_complete_once');case.setUp()
                try:
                    path=case.root/'scripts/probe_vision_runtime.py'
                    path.write_text(path.read_text().replace(needle,needle+"\n        fence.clear_confirmed(active_operation)"))
                    result=case.run_probe();self.assertEqual(result.returncode,126,result.stdout+result.stderr)
                    self.assertEqual(len(case.calls()),count);case.later_blocked()
                finally:case.doCleanups()

    def test_transition_write_failure_retains_same_latch(self):
        path=self.root/'scripts/vision_command_fence.py'
        path.write_text(path.read_text()+"\n_old_write=VisionCommandFence._write_claimed\ndef fail_phase(self, expected):\n if expected['action']=='bootstatus':raise OSError('injected transition failure')\n return _old_write(self,expected)\nVisionCommandFence._write_claimed=fail_phase\n")
        result=self.run_probe();self.assertEqual(result.returncode,126,result.stdout+result.stderr)
        self.assertEqual([x[1] for x in self.calls()],['list','boot']);self.later_blocked()

    def test_shell_owned_install_entry_rejects_probe_actions(self):
        result=subprocess.run([sys.executable,'scripts/run_vision_fenced_command.py','boot','1-2-3'],cwd=self.root,
                              env=self.env,capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,126);self.assertEqual(self.calls(),[])


if __name__=='__main__':unittest.main()
