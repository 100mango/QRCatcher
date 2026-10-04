#!/usr/bin/env python3
"""Process-owner timeout/output contract using local children, never an app test."""
from pathlib import Path
import os,signal,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from watch_process import execute

class WatchCommandTests(unittest.TestCase):
    def run_python(self,source,**kwargs):
        return execute([sys.executable,'-u','-c',source],echo=False,**kwargs)
    def test_success_and_exact_tail(self):
        code,tail,operation=self.run_python('print("ready")',seconds=2)
        self.assertEqual((code,tail),(0,'ready\n'))
        self.assertEqual(operation['state'],'completed')
    def test_nonzero_is_preserved(self):
        code,_,operation=self.run_python('raise SystemExit(7)',seconds=2)
        self.assertEqual((code,operation['exit']),(7,7))
    def test_timeout_preserves_started_message(self):
        code,tail,operation=self.run_python('import time; print("started"); time.sleep(30)',seconds=.1)
        self.assertEqual(code,124);self.assertIn('started',tail)
        self.assertEqual(operation['state'],'timed_out')
        self.assertLess(operation['elapsed_seconds'],4)
    def test_child_closing_output_cannot_escape_deadline(self):
        code,_,operation=self.run_python('import os,time; os.close(1); os.close(2); time.sleep(30)',seconds=.1)
        self.assertEqual(code,124);self.assertLess(operation['elapsed_seconds'],4)
    def test_inherited_output_pipe_cannot_extend_owned_command_deadline(self):
        code,tail,operation=self.run_python('import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); print(p.pid,flush=True); time.sleep(30)',seconds=.1)
        # This is an exact synthetic child created by this test. Clean it up
        # explicitly; production watchdogs never enumerate/kill other processes.
        child=int(tail.strip())
        try:
            self.assertEqual(code,124)
            self.assertLess(operation['elapsed_seconds'],4)
        finally:
            try:os.kill(child,signal.SIGTERM)
            except ProcessLookupError:pass
    def test_output_budget_and_tail_are_bounded(self):
        code,tail,operation=self.run_python('import sys,time; sys.stdout.write("x"*100000); sys.stdout.flush(); time.sleep(30)',seconds=2,output_limit=4096,tail_limit=1024)
        self.assertEqual(code,125);self.assertLessEqual(len(tail.encode()),1024)
        self.assertEqual(operation['state'],'output_limit')

if __name__=='__main__':unittest.main()
