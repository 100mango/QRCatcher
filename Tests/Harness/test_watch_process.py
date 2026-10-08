#!/usr/bin/env python3
"""Process-owner timeout/output contract using local children, never an app test."""
from pathlib import Path
import os,select,signal,subprocess,sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from watch_process import execute
from owned_process_group import stop_group

class WatchCommandTests(unittest.TestCase):
    def setUp(self):
        isolation=patch.dict(os.environ);isolation.start();self.addCleanup(isolation.stop)
        for key in ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED','QRCATCHER_OWNED_PROCESS_BARRIER','GITHUB_ENV','GITHUB_WORKSPACE']:os.environ.pop(key,None)
    def test_exited_leader_does_not_hide_owned_orphan(self):
        class ReapedLeader:
            pid=987654
            def poll(self):return 0
        with patch('owned_process_group.group_exists',return_value=True),patch('owned_process_group.os.killpg') as kill:
            self.assertFalse(stop_group(ReapedLeader(),grace=.025))
            self.assertEqual([call.args[1] for call in kill.call_args_list],[signal.SIGTERM,signal.SIGKILL])
        with patch('owned_process_group.group_exists',side_effect=[True,False]),patch('owned_process_group.os.killpg') as kill:
            self.assertTrue(stop_group(ReapedLeader(),grace=.025));kill.assert_called_once_with(987654,signal.SIGTERM)
    def test_refuses_callers_own_group(self):
        class OwnGroup:
            pid=os.getpgrp()
        with self.assertRaises(ValueError):stop_group(OwnGroup())
    def test_real_term_ignoring_child_reaches_bounded_kill(self):
        child=subprocess.Popen([sys.executable,'-u','-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print("ready"); time.sleep(30)'],stdout=subprocess.PIPE,text=True,start_new_session=True)
        try:
            self.assertTrue(select.select([child.stdout],[],[],5)[0]);self.assertEqual(child.stdout.readline().strip(),'ready')
            self.assertTrue(stop_group(child,grace=.1));self.assertEqual(child.returncode,-signal.SIGKILL)
        finally:
            stop_group(child,grace=.1);child.stdout.close()
    def test_execute_reports_unconfirmed_cleanup_even_after_zero_leader_exit(self):
        with patch('watch_process.stop_group',return_value=False):
            code,_,operation=self.run_python('print("ready")',seconds=2)
        self.assertEqual(code,126);self.assertEqual(operation['state'],'cleanup_unconfirmed');self.assertFalse(operation['cleanup_confirmed'])
    def test_child_exit_two_cannot_mask_unconfirmed_cleanup(self):
        with patch('watch_process.stop_group',return_value=False):
            code,_,operation=self.run_python('raise SystemExit(2)',seconds=2)
        self.assertEqual(code,126);self.assertEqual(operation['original_exit'],2)
        self.assertEqual(operation['state'],'cleanup_unconfirmed');self.assertFalse(operation['cleanup_confirmed'])
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
