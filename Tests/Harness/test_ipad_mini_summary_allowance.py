"""Exact diagnostic first-summary allowance; explicit local command doubles only."""
from pathlib import Path
import hashlib,json,os,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import ipad_mini_setup as mini
import ipad_mini_state_handoff as handoff
import owned_process_barrier as barrier
import test_ipad_mini_setup as base
import test_ipad_mini_ledger as ledger

LAYOUT='MiniUIResults-layout.xcresult'
FILES='MiniUIResults-files.xcresult'
PHOTOS='MiniUIResults.xcresult'


class MiniFirstSummaryAllowanceTests(unittest.TestCase):
    def setUp(self):
        self.f=base.Fixture();ledger.diagnostic(self.f)
        for phase in ('prepare','build'):
            self.f.budget.enter(phase);self.f.budget.state['phases'][phase]['status']='completed';self.f.budget.persist()
        self.receipt=self.f.configure();self.f.calls.clear()
        phase=self.f.budget.state['phases']['mini'];phase['status']='row_running'
        self.controller=mini.Controller(self.f.budget,'mini',phase['deadline'],self.f.executor)
    def tearDown(self):self.f.close()
    def summary(self,result=LAYOUT,expected=2,exit_code=0):
        return mini.qualify_result(self.controller,base.DEVICE,result,expected,exit_code)
    def operation(self):return self.controller.record['operations'][-1]
    def test_exact_diagnostic_first_summary_uses30_once_and_qualifies_same_counts(self):
        self.summary();self.assertEqual(len(self.f.calls),1);self.assertEqual(self.f.calls[0][1],30)
        self.assertEqual(self.controller.record['results'][LAYOUT],{'totalTestCount':2,'passedTests':2,'failedTests':0,'skippedTests':0,'expectedFailures':0})
        self.assertFalse(barrier.blocked());self.assertFalse((self.f.root/'build'/mini.PENDING).exists())
    def test_later_and_unknown_results_keep10(self):
        for result in (FILES,PHOTOS,'Other-layout.xcresult'):
            with self.subTest(result=result):self.assertEqual(mini.result_summary_limit(result),10)
        self.summary(FILES,1);self.summary(PHOTOS,1)
        self.assertEqual([cap for command,cap in self.f.calls],[10,10])
    def test_canonical_and_unrelated_refs_keep10(self):
        for ref in ('refs/heads/codex/apple-platforms','refs/heads/another'):
            with patch.dict(os.environ,{'GITHUB_REF':ref,'QRCATCHER_IOS_SUPPLEMENT_ONLY':'false'}):self.assertEqual(mini.result_summary_limit(LAYOUT),10)
    def test_wrong_diagnostic_identity_refuses_before_reader(self):
        for key,value in [('GITHUB_REPOSITORY','other/repo'),('GITHUB_WORKFLOW_SHA','b'*40),('GITHUB_WORKFLOW_REF','wrong'),('EVIDENCE_SCOPE','ipad_pro'),('DIAGNOSTIC_ONLY','false')]:
            with self.subTest(key=key),patch.dict(os.environ,{key:value}):
                with self.assertRaises(ValueError):self.summary()
                self.assertEqual(self.f.calls,[])
    def test_full30_plus20_cleanup_window_is_admitted(self):
        self.f.clock.now=self.controller.deadline-50;self.summary();self.assertEqual(self.f.calls[0][1],30)
    def test_less_than30_plus20_refuses_without_command_or_clock_reset(self):
        start=self.controller.record['started'];deadline=self.controller.deadline
        self.f.clock.now=deadline-49.999
        with self.assertRaises(ValueError):self.summary()
        self.assertEqual(self.f.calls,[]);self.assertEqual(self.controller.record['started'],start);self.assertEqual(self.controller.deadline,deadline)
        self.assertFalse((self.f.root/'build'/mini.PENDING).exists())
    def test_return_between10_and30_is_timely_and_not_retried(self):
        original=self.f.executor
        def delayed(command,cap,**kwargs):
            code,raw,op=original(command,cap,**kwargs);self.f.clock.now+=24.99;op['elapsed_seconds']=25;return code,raw,op
        self.controller.executor=delayed;self.summary();self.assertEqual(len(self.f.calls),1)
        self.assertEqual(self.operation()['cap'],30);self.assertEqual(self.operation()['elapsed_seconds'],25)
    def test_late_success_at_cap_plus2_is_rejected_and_latched_without_retry(self):
        original=self.f.executor
        def late(command,cap,**kwargs):
            code,raw,op=original(command,cap,**kwargs);self.f.clock.now+=31.99;op['elapsed_seconds']=32;return code,raw,op
        self.controller.executor=late
        with self.assertRaises(ValueError):self.summary()
        self.assertTrue(barrier.blocked());self.assertEqual(len(self.f.calls),1)
        with self.assertRaises(ValueError):self.summary()
        self.assertEqual(len(self.f.calls),1)
    def test_unknown_or_unclean_completion_latches_and_prevents_more_commands(self):
        for change in ({'state':'timed_out','exit':124},{'state':'unknown'},{'cleanup_confirmed':False}):
            with self.subTest(change=change):
                self.f.operation_edit=lambda op,cmd:op.update(change)
                with self.assertRaises(ValueError):self.summary()
                self.assertEqual(len(self.f.calls),1);self.assertTrue(barrier.blocked())
                with self.assertRaises(ValueError):self.summary()
                self.assertEqual(len(self.f.calls),1)
                self.f.close();self.setUp()
    def test_source_device_counts_and_warning_decoder_still_refuses_bad_result(self):
        for change in ({'totalTestCount':1},{'passedTests':1},{'skippedTests':1},{'expectedFailures':1},{'runtimeWarnings':['warning']},{'testFailures':[{}]},{'devicesAndConfigurations':[{'device':{'deviceId':'foreign'}}]}):
            with self.subTest(change=change):
                self.f.summary_edit=lambda obj,result:obj.update(change)
                with self.assertRaises(ValueError):self.summary()
                self.assertNotIn(LAYOUT,self.controller.record.get('results',{}))
                self.f.calls.clear()
    def test_handoff_consumes_same_exact_first_cap_and_rejects_duplicate_or_late_proof(self):
        self.summary();case=mini.test_command(base.DEVICE,mini.LAYOUT,LAYOUT)
        self.controller.record['operations'].insert(0,{'command':case,'cap':480,'state':'completed','exit':0,'cleanup_confirmed':True,'elapsed_seconds':.01})
        handoff.qualified_prior(self.controller,base.DEVICE,'before_files_fixture')
        op=self.operation();original=dict(op)
        for change in ({'cap':10},{'cap':31},{'elapsed_seconds':32},{'state':'timed_out'},{'cleanup_confirmed':False},{'exit':1}):
            op.clear();op.update(original);op.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):handoff.qualified_prior(self.controller,base.DEVICE,'before_files_fixture')
        op.clear();op.update(original);self.controller.record['operations'].append(dict(op))
        with self.assertRaises(ValueError):handoff.qualified_prior(self.controller,base.DEVICE,'before_files_fixture')
    def test_consumer_files_summary_remains10_and_known_failed_case_remains65(self):
        self.f.file_exit=65;self.summary(FILES,1,65);case=mini.test_command(base.DEVICE,mini.FILES,FILES)
        self.controller.record['operations'].insert(0,{'command':case,'cap':240,'state':'completed','exit':65,'cleanup_confirmed':True,'elapsed_seconds':.01})
        handoff.qualified_prior(self.controller,base.DEVICE,'before_photos_seed')
        self.operation()['cap']=30
        with self.assertRaises(ValueError):handoff.qualified_prior(self.controller,base.DEVICE,'before_photos_seed')
    def test_runtime_clocks_native_commands_and_strict_qualification_body_are_preserved(self):
        source=(ROOT/'scripts/ipad_mini_setup.py').read_text();qualified=source.split('def qualify_result(',1)[1].split('\n\n_FIXTURE',1)[0]
        old='6369b13ab4a7bee9da905ba4c4441902738ce84d609479bfabd285351b8dc06b'
        # Explicit normalization of the one selected argument; every existing
        # decoder assertion is compared to the immutable admitted source body.
        normalized=qualified.replace('result_summary_limit(result))','10)',1)
        self.assertEqual(hashlib.sha256(normalized.encode()).hexdigest(),old)
        self.assertEqual(mini.DIAGNOSTIC_CAPS['mini'],1920);self.assertEqual(sum(mini.DIAGNOSTIC_CAPS.values()),3000);self.assertEqual(mini.CLEANUP,20)
        self.assertEqual(mini.CAPS['mini'],1620);self.assertEqual(sum(mini.CAPS.values()),2700)


if __name__=='__main__':unittest.main()
