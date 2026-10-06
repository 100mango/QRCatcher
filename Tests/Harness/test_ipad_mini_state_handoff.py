#!/usr/bin/env python3
"""Diagnostic handoff unit doubles through the real closed controller/lease.
No simulator, compiler, daemon or app is run; production profile wiring is
owned by the parent and remains unexecuted in this preparation component.
"""
from pathlib import Path
import copy,hashlib,json,os,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import ipad_mini_setup as mini
import ipad_mini_state_handoff as handoff
import owned_process_barrier as barrier
import test_ipad_mini_setup as base

class MiniStateHandoffTests(unittest.TestCase):
    def setUp(self):
        self.f=base.Fixture();self.receipt=self.f.configure();phase=self.f.budget.state['phases']['mini'];phase['status']='row_running'
        phase['results']={'MiniUIResults-layout.xcresult':{'totalTestCount':2,'passedTests':2,'failedTests':0,'skippedTests':0,'expectedFailures':0},
                          'MiniUIResults-files.xcresult':{'totalTestCount':1,'passedTests':1,'failedTests':0,'skippedTests':0,'expectedFailures':0}}
        # Explicit synthetic prior case/summary receipts, never native coverage.
        for result,selectors,cap in [('MiniUIResults-layout.xcresult',mini.LAYOUT,480),('MiniUIResults-files.xcresult',mini.FILES,240)]:
            for command,limit in [(mini.test_command(base.DEVICE,selectors,result),cap),(['xcrun','xcresulttool','get','test-results','summary','--path',result],10)]:
                phase['operations'].append({'command':command,'cap':limit,'state':'completed','exit':0,'cleanup_confirmed':True,'elapsed_seconds':.01})
        self.lease=mini.Claim(self.f.budget,None,'full_row_dispatched_once',mini.STOP);mini._ROW_LEASE=self.lease
        self.controller=mini.Controller(self.f.budget,'mini',phase['deadline'],self.execute)
        self.calls=[];self.states=['Booted'];self.edit=None;self.boot_exit=0;self.status_exit=0;self.operation_edit=None;self.after=None;self.raw_override=None
    def tearDown(self):
        self.lease.close(False);mini._ROW_LEASE=None;self.f.close()
    def execute(self,command,cap,**kwargs):
        self.calls.append((command,cap));self.f.clock.now+=.01;code=0
        if command==['xcrun','simctl','list','devices','available','-j']:
            state=self.states.pop(0) if len(self.states)>1 else self.states[0]
            value={'devices':{base.RUNTIME:[{'udid':base.DEVICE,'name':self.receipt['name'],'deviceTypeIdentifier':base.TYPE,'isAvailable':True,'state':state}]}}
            if self.edit:self.edit(value)
            raw=self.raw_override if self.raw_override is not None else json.dumps(value)
        elif command==['xcrun','simctl','boot',base.DEVICE]:raw='Explicit owned boot double';code=self.boot_exit
        elif command==['xcrun','simctl','bootstatus',base.DEVICE,'-b']:raw='Explicit bootstatus double';code=self.status_exit
        else:raise AssertionError(command)
        operation={'state':'completed','exit':code,'cleanup_confirmed':True,'elapsed_seconds':.01}
        if self.operation_edit:self.operation_edit(operation,command)
        if self.after:self.after(command)
        return code,raw,operation
    def first(self):return handoff.ensure_owned_booted(self.controller,base.DEVICE,self.receipt,'before_files_fixture')
    def second(self):return handoff.ensure_owned_booted(self.controller,base.DEVICE,self.receipt,'before_photos_seed')
    def test_booted_proceeds_with_one_read_only_precheck(self):
        record=self.first();self.assertEqual(record['state'],'booted_snapshot_only');self.assertEqual(record['boot_attempts'],0)
        self.assertEqual([cap for command,cap in self.calls],[30]);self.assertFalse(record['service_completion_claimed']);self.assertFalse(record['daemon_cleanup_claimed'])
    def test_shutdown_one_bounded_recovery_then_verified_booted(self):
        self.states=['Shutdown','Booted'];record=self.first()
        self.assertEqual([cap for command,cap in self.calls],[30,30,90,30]);self.assertEqual(record['boot_attempts'],1);self.assertEqual(record['bootstatus_attempts'],1)
        self.assertEqual([r['state'] for r in record['observations']],['Shutdown','Booted']);self.assertEqual(record['state'],'booted_snapshot_only')
        self.assertEqual(record['row_deadline_monotonic'],self.controller.deadline)
    def test_second_handoff_booted_after_original_files(self):
        self.first();self.calls.clear();record=self.second();self.assertEqual(record['state'],'booted_snapshot_only');self.assertEqual(len(self.calls),1)
    def test_second_handoff_shutdown_recovery_is_separate_once(self):
        self.first();self.calls.clear();self.states=['Shutdown','Booted'];self.second();self.assertEqual([cap for command,cap in self.calls],[30,30,90,30])
    def test_known_complete_failed_files_does_not_block_independent_seed_handoff(self):
        self.first();self.controller.record['results']['MiniUIResults-files.xcresult'].update(passedTests=0,failedTests=1)
        next(item for item in self.controller.record['operations'] if item['command']==mini.test_command(base.DEVICE,mini.FILES,'MiniUIResults-files.xcresult'))['exit']=65
        record=self.second();self.assertEqual(record['state'],'booted_snapshot_only');self.assertEqual(self.controller.record['results']['MiniUIResults-files.xcresult']['failedTests'],1)
    def test_missing_layout_qualification_refused_before_any_command(self):
        self.controller.record['results'].pop('MiniUIResults-layout.xcresult')
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(self.calls,[])
    def test_second_without_first_handoff_refused(self):
        with self.assertRaises(ValueError):self.second()
        self.assertEqual(self.calls,[])
    def test_missing_or_zero_files_qualification_refused(self):
        self.first();self.calls.clear();self.controller.record['results']['MiniUIResults-files.xcresult']['totalTestCount']=0
        with self.assertRaises(ValueError):self.second()
        self.assertEqual(self.calls,[])
    def test_unknown_state_stops_without_boot(self):
        for state in ['Booting','Creating','Unknown',None]:
            with self.subTest(state=state):
                self.states=[state]
                with self.assertRaises(ValueError):self.first()
                self.assertEqual(len(self.calls),1);self.assertFalse(any(command[2]=='boot' for command,cap in self.calls))
                self.controller.record['state_handoffs'].clear();self.calls.clear()
    def test_missing_owned_device_stops_without_boot(self):
        self.edit=lambda value:value['devices'].update({base.RUNTIME:[]})
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),1)
    def test_duplicate_owned_device_stops_without_boot(self):
        self.edit=lambda value:value['devices'][base.RUNTIME].append(copy.deepcopy(value['devices'][base.RUNTIME][0]))
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),1)
    def test_foreign_runtime_or_type_or_name_refused(self):
        edits=[lambda v:v['devices'][base.RUNTIME][0].update(deviceTypeIdentifier='com.apple.CoreSimulator.SimDeviceType.foreign'),
               lambda v:v['devices'][base.RUNTIME][0].update(name='Other app owned device'),
               lambda v:v.update(devices={'com.apple.CoreSimulator.SimRuntime.iOS-26-0':v['devices'][base.RUNTIME]}),
               lambda v:v['devices'][base.RUNTIME][0].update(isAvailable=False)]
        for edit in edits:
            with self.subTest(edit=edit):
                self.edit=edit
                with self.assertRaises(ValueError):self.first()
                self.assertEqual(len(self.calls),1);self.controller.record['state_handoffs'].clear();self.calls.clear()
    def test_foreign_uuid_refused_without_destination_fallback(self):
        self.edit=lambda value:value['devices'][base.RUNTIME][0].update(udid='11111111-2222-4333-8444-555555555555')
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),1)
    def test_stale_source_run_or_row_clock_receipt_refused(self):
        for key,value in [('source','b'*40),('run_id','124'),('row_deadline_monotonic',self.controller.deadline+1),('device','11111111-2222-4333-8444-555555555555')]:
            wrong=copy.deepcopy(self.receipt);wrong[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):handoff.ensure_owned_booted(self.controller,base.DEVICE,wrong,'before_files_fixture')
        self.assertEqual(self.calls,[])
    def test_real_row_lease_required(self):
        mini._ROW_LEASE=None
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(self.calls,[]);mini._ROW_LEASE=self.lease
    def test_removed_real_row_lease_stops_before_command(self):
        self.lease.path.unlink()
        with self.assertRaises((ValueError,OSError)):self.first()
        self.assertEqual(self.calls,[])
    def test_one_handoff_cannot_retry_after_success(self):
        self.first();count=len(self.calls)
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),count)
    def test_one_handoff_cannot_retry_after_refusal(self):
        self.states=['Unknown']
        with self.assertRaises(ValueError):self.first()
        count=len(self.calls);self.states=['Booted']
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),count)
    def test_boot_nonzero_stops_without_bootstatus_or_readback(self):
        self.states=['Shutdown'];self.boot_exit=149
        with self.assertRaises(ValueError):self.first()
        self.assertEqual([cap for command,cap in self.calls],[30,30])
    def test_bootstatus_nonzero_stops_without_readback(self):
        self.states=['Shutdown'];self.status_exit=124
        with self.assertRaises(ValueError):self.first()
        self.assertEqual([cap for command,cap in self.calls],[30,30,90])
    def test_shutdown_final_readback_stops_without_boot_retry(self):
        self.states=['Shutdown','Shutdown']
        with self.assertRaises(ValueError):self.first()
        self.assertEqual([cap for command,cap in self.calls],[30,30,90,30])
        self.assertEqual(self.controller.record['state_handoffs']['before_files_fixture']['state'],'failed_or_refused')
    def test_unconfirmed_precheck_cleanup_stops_later_commands(self):
        self.operation_edit=lambda operation,command:operation.update(cleanup_confirmed=False)
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),1);self.assertTrue(barrier.blocked())
    def test_unconfirmed_boot_cleanup_stops_bootstatus(self):
        self.states=['Shutdown'];self.operation_edit=lambda operation,command:operation.update(cleanup_confirmed=False) if command[2]=='boot' else None
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),2);self.assertTrue(barrier.blocked())
    def test_true_inherited_uncertainty_stops_precheck(self):
        os.environ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED']='true'
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(self.calls,[])
    def test_missing_precheck_full_window_refused_before_launch(self):
        self.f.clock.now=self.controller.deadline-49.99
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(self.calls,[])
    def consume_after_completed(self,action,remaining):
        original=self.f.budget.persist
        def consume():
            original()
            operations=self.controller.record['operations']
            if operations and operations[-1]['command'][2]==action and operations[-1].get('state')=='completed':self.f.clock.now=self.controller.deadline-remaining
        self.f.budget.persist=consume
    def test_missing_complete_recovery_window_refused_before_boot(self):
        self.states=['Shutdown'];self.consume_after_completed('list',175.99)
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),1);self.assertEqual(self.controller.record['state_handoffs']['before_files_fixture']['boot_attempts'],0)
    def test_missing_bootstatus_full_window_refused_after_one_returned_boot(self):
        self.states=['Shutdown'];self.consume_after_completed('boot',109.99)
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),2)
    def test_missing_final_readback_window_refused_after_returned_bootstatus(self):
        self.states=['Shutdown'];self.consume_after_completed('bootstatus',49.99)
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),3)
    def test_persistence_consumes_precheck_window_before_dispatch(self):
        self.f.clock.now=self.controller.deadline-50
        original=self.f.budget.persist
        def consume():original();self.f.clock.now+=.01
        self.f.budget.persist=consume
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(self.calls,[])
    def test_foreign_handoff_label_refused(self):
        with self.assertRaises(ValueError):handoff.ensure_owned_booted(self.controller,base.DEVICE,self.receipt,'install')
        self.assertEqual(self.calls,[])
    def test_phase_deadline_never_reset_by_shutdown_recovery(self):
        self.states=['Shutdown','Booted'];deadline=self.controller.deadline;start=self.controller.record['started'];self.first()
        self.assertEqual(self.controller.deadline,deadline);self.assertEqual(self.controller.record['started'],start)
        self.assertEqual(self.receipt['pretest_boot_completion'],'not_requested');self.assertEqual(self.receipt['state'],'configured_shutdown_device_only')
    def test_caps_and_worst_case_arithmetic_are_explicit(self):
        self.assertEqual(handoff.CAPS,{'precheck':30,'boot':30,'bootstatus':90,'readback':30})
        self.assertEqual(1500+2*sum(handoff.CAPS.values()),1860)
        self.assertEqual(1860+18*2,1896);self.assertEqual(1860+20*2,1900)

    def test_malformed_or_duplicate_json_stops_without_boot(self):
        for raw in ['not JSON','{"devices":{},"devices":{}}','{"devices":{"x":NaN}}']:
            with self.subTest(raw=raw):
                self.raw_override=raw
                with self.assertRaises(ValueError):self.first()
                self.assertEqual(len(self.calls),1);self.controller.record['state_handoffs'].clear();self.calls.clear()
    def test_timed_out_precheck_stops_all_later_commands(self):
        self.operation_edit=lambda operation,command:operation.update(state='timed_out',exit=124)
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),1);self.assertTrue(barrier.blocked())
    def test_timed_out_bootstatus_stops_final_readback(self):
        self.states=['Shutdown'];self.operation_edit=lambda operation,command:operation.update(state='timed_out',exit=124) if command[2]=='bootstatus' else None
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),3);self.assertTrue(barrier.blocked())
    def test_exact_recovery_chain_admission_boundary(self):
        self.states=['Shutdown','Booted'];self.consume_after_completed('list',176)
        record=self.first();self.assertEqual(record['state'],'booted_snapshot_only');self.assertEqual(len(self.calls),4)

    def test_unclean_prior_case_refused_before_handoff(self):
        next(item for item in self.controller.record['operations'] if item['command']==mini.test_command(base.DEVICE,mini.LAYOUT,'MiniUIResults-layout.xcresult'))['cleanup_confirmed']=False
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(self.calls,[])
    def test_late_prior_case_refused_before_handoff(self):
        next(item for item in self.controller.record['operations'] if item['command']==mini.test_command(base.DEVICE,mini.LAYOUT,'MiniUIResults-layout.xcresult'))['elapsed_seconds']=482
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(self.calls,[])
    def test_missing_prior_summary_operation_refused(self):
        self.controller.record['operations']=[item for item in self.controller.record['operations'] if item['command']!=['xcrun','xcresulttool','get','test-results','summary','--path','MiniUIResults-layout.xcresult']]
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(self.calls,[])
    def test_unclean_prior_files_summary_refuses_seed_handoff(self):
        self.first();self.calls.clear()
        next(item for item in self.controller.record['operations'] if item['command']==['xcrun','xcresulttool','get','test-results','summary','--path','MiniUIResults-files.xcresult'])['cleanup_confirmed']=False
        with self.assertRaises(ValueError):self.second()
        self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()
