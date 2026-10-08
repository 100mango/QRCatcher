"""Exact observed timeout guard. Synthetic paths/commands, no simulator execution."""
import json,os,plistlib,runpy,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import owned_process_barrier as barrier
DEVICE='11111111-2222-4333-8444-555555555555'

class FixtureTimeoutGuardTests(unittest.TestCase):
 def exercise(self, fail_at=None):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder).resolve();(root/'build').mkdir();(root/'app').mkdir();(root/'data').mkdir();(root/'Tests/Fixtures').mkdir(parents=True)
   (root/'app/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'100mango.QRCatcher','UIFileSharingEnabled':True,'LSSupportsOpeningDocumentsInPlace':True}))
   source=b'synthetic file bytes';(root/'Tests/Fixtures/unicode.png').write_bytes(source)
   env={'GITHUB_WORKSPACE':str(root),'GITHUB_ENV':str(root/'env'),'QRCATCHER_OWNED_PROCESS_BARRIER':str(root/'build/owned-process-cleanup.json')}
   calls=[]
   def query(command,**kwargs):
    calls.append(command)
    self.assertEqual(kwargs,{'text':True,'timeout':30})
    self.assertEqual(command[:5],['xcrun','simctl','get_app_container',DEVICE,'100mango.QRCatcher'])
    if len(calls)==fail_at:raise subprocess.TimeoutExpired(command,30)
    return str(root/command[-1])+'\n'
   prior=Path.cwd()
   try:
    os.chdir(root)
    with patch.dict(os.environ,env,clear=True),patch.object(sys,'argv',['stage_owned_import_fixture.py',DEVICE]),patch('subprocess.check_output',side_effect=query):
     if fail_at:
      with self.assertRaises(SystemExit) as result:runpy.run_path(str(ROOT/'scripts/stage_owned_import_fixture.py'),run_name='__main__')
      self.assertEqual(result.exception.code,126);self.assertTrue(barrier.blocked())
      self.assertTrue((root/'build/fixture-query-inflight.json').is_file())
      d=json.loads((root/'build/owned-process-cleanup.json').read_text())
      self.assertEqual(d['operation'],{'state':'fixture_container_query_timeout','exit':126,'original_exit':124,'cleanup_confirmed':False})
      self.assertFalse((root/'data/Documents').exists());self.assertFalse((root/'build/import-fixture/fixture.json').exists())
      self.assertEqual((root/'env').read_text(),'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED=true\n')
     else:
      runpy.run_path(str(ROOT/'scripts/stage_owned_import_fixture.py'),run_name='__main__')
      self.assertEqual((root/'data/Documents/QRCatcher-Test-Imports/SyntheticQR.png').read_bytes(),source)
      self.assertFalse(barrier.blocked());self.assertFalse((root/'env').exists());self.assertFalse((root/'build/fixture-query-inflight.json').exists())
   finally:os.chdir(prior)
   self.assertEqual(len(calls),fail_at or 2)
 def test_first_lookup_timeout_stops_before_data_lookup_or_any_document_write(self):self.exercise(1)
 def test_second_lookup_timeout_stops_before_any_document_write(self):self.exercise(2)
 def test_success_preserves_existing_query_and_fixture_flow(self):self.exercise()
 def test_existing_parent_deadline_and_group_inheritance_are_unchanged(self):
  source=(ROOT/'scripts/stage_owned_import_fixture.py').read_text()
  self.assertNotIn('start_new_session',source);self.assertNotIn('from watch_process',source)
  launcher=(ROOT/'scripts/run_ios_platform_ui.sh').read_text()
  self.assertIn('run_bounded.py 75 python3 scripts/stage_owned_import_fixture.py',launcher)

class FixtureOuterOwnerTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();(self.root/'build').mkdir()
  self.env={**os.environ,'GITHUB_WORKSPACE':str(self.root),'GITHUB_ENV':str(self.root/'env'),'QRCATCHER_OWNED_PROCESS_BARRIER':str(self.root/'build/owned-process-cleanup.json')}
  self.env.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED',None)
  self.program=self.root/'query.py'
  self.program.write_text('''import json,os,signal,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,''' + repr(str(ROOT/'scripts')) + ''')
from fixture_query_guard import query_guard
command=['xcrun','simctl','get_app_container',"''' + DEVICE + '''",'100mango.QRCatcher','app']
if os.environ.get('COOPERATIVE_PARENT')=='1':
 def stop(signum,frame): raise SystemExit(128+signum)
 signal.signal(signal.SIGTERM,stop)
with query_guard(command):
 subprocess.check_output([sys.executable,'-c',"import json,os,time;from pathlib import Path;Path('child.json').write_text(json.dumps({'pid':os.getpid(),'group':os.getpgrp()}));time.sleep(30)"],text=True,timeout=30)
''')
 def wait_started(self):
  import time
  deadline=time.monotonic()+4
  while time.monotonic()<deadline:
   try:return json.loads((self.root/'child.json').read_text())
   except (OSError,ValueError):time.sleep(.01)
  self.fail('Owned synthetic query did not start')
 def fresh_blocked(self):
  result=subprocess.run([sys.executable,str(ROOT/'scripts/owned_process_barrier.py'),'--check'],cwd=self.root,env=self.env,capture_output=True,timeout=3)
  self.assertEqual(result.returncode,126)
 def test_standalone_outer_kill_leaves_durable_pending_query(self):
  import signal
  from owned_process_group import stop_group
  process=subprocess.Popen([sys.executable,str(self.program)],cwd=self.root,env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
  try:
   child=self.wait_started();self.assertEqual(child['group'],process.pid)
   os.kill(process.pid,signal.SIGKILL);process.wait(timeout=3)
   marker=json.loads((self.root/'build/fixture-query-inflight.json').read_text())
   self.assertEqual(marker['inherited_group'],process.pid);self.assertFalse(marker['host_group_cleanup_claimed'])
   self.fresh_blocked()
  finally:
   stop_group(process,grace=.1);process.stdout.close();process.stderr.close()
 def test_existing_short_outer_owner_cleans_inherited_query_and_keeps_gate_closed(self):
  from watch_process import execute
  from owned_process_group import stop_group
  self.env['COOPERATIVE_PARENT']='1';old=Path.cwd()
  try:
   os.chdir(self.root)
   with patch.dict(os.environ,self.env,clear=True):
    code,output,operation=execute([sys.executable,str(self.program)],.4,echo=False)
    self.assertEqual(code,124);self.assertTrue(operation['cleanup_confirmed']);self.assertLess(operation['elapsed_seconds'],4)
   child=json.loads((self.root/'child.json').read_text())
   marker=json.loads((self.root/'build/fixture-query-inflight.json').read_text())
   self.assertEqual(child['group'],marker['inherited_group']);self.fresh_blocked()
  finally:os.chdir(old)
 def test_pending_partial_or_symbolic_marker_blocks_fresh_invocation(self):
  marker=self.root/'build/fixture-query-inflight.json'
  marker.write_bytes(b'');self.fresh_blocked();marker.unlink()
  marker.symlink_to(self.root/'missing');self.fresh_blocked()
 def test_changed_marker_is_not_cleared_after_normal_query_return(self):
  from fixture_query_guard import query_guard
  old=Path.cwd()
  try:
   os.chdir(self.root)
   with patch.dict(os.environ,self.env,clear=True),self.assertRaises(SystemExit) as error:
    with query_guard(['xcrun','simctl','get_app_container',DEVICE,'100mango.QRCatcher','app']):
     (self.root/'build/fixture-query-inflight.json').write_text('changed')
   self.assertEqual(error.exception.code,126);self.assertEqual((self.root/'build/fixture-query-inflight.json').read_text(),'changed');self.fresh_blocked()
  finally:os.chdir(old)

if __name__=='__main__':unittest.main()
