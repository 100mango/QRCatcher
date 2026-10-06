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

# Exact retained public Xcode27 output shape, with synthetic owned identity.
# This command double is not evidence of simulator or app execution.
def bootstatus_output(name,device):
    return ('Monitoring boot status for '+name+' ('+device+').\n'
            '[2026-10-06 01:04:59 +0000] Status=4, isTerminal=NO, Elapsed=00:47.\n'
            '\tWaiting on System App\n\n'
            '[2026-10-06 01:05:15 +0000] Status=4294967295, isTerminal=YES, Elapsed=01:03.\n'
            '\tFinished\n\n')

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
        self.calls=[];self.states=['Booted'];self.edit=None;self.boot_exit=0;self.status_exit=0;self.operation_edit=None;self.after=None;self.raw_override=None;self.status_raw=bootstatus_output(self.receipt['name'],base.DEVICE)
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
        elif command==['xcrun','simctl','bootstatus',base.DEVICE,'-b']:raw=self.status_raw;code=self.status_exit
        else:raise AssertionError(command)
        operation={'state':'completed','exit':code,'cleanup_confirmed':True,'elapsed_seconds':.01,'output_bytes':len(raw.encode())}
        if self.operation_edit:self.operation_edit(operation,command)
        if self.after:self.after(command)
        return code,raw,operation
    def first(self):return handoff.ensure_owned_booted(self.controller,base.DEVICE,self.receipt,'before_files_fixture')
    def second(self):return handoff.ensure_owned_booted(self.controller,base.DEVICE,self.receipt,'before_photos_seed')
    def test_booted_proceeds_with_one_read_only_precheck(self):
        record=self.first();self.assertEqual(record['state'],'booted_snapshot_only');self.assertEqual(record['boot_attempts'],0)
        self.assertEqual([cap for command,cap in self.calls],[30]);self.assertFalse(record['service_completion_claimed']);self.assertFalse(record['daemon_cleanup_claimed'])
    def test_shutdown_one_bounded_pair_observes_exact_bootstatus_finished(self):
        self.states=['Shutdown'];record=self.first()
        self.assertEqual([cap for command,cap in self.calls],[30,30,90]);self.assertEqual(record['boot_attempts'],1);self.assertEqual(record['bootstatus_attempts'],1)
        self.assertEqual([r['state'] for r in record['observations']],['Shutdown']);self.assertEqual(record['state'],'bootstatus_completion_observation_only')
        self.assertEqual(record['readiness_basis'],'exact_owned_uuid_bootstatus_completion')
        proof=record['bootstatus_completion'];self.assertEqual(proof['stdout_sha256'],hashlib.sha256(self.status_raw.encode()).hexdigest())
        self.assertEqual(proof['stdout_bytes'],len(self.status_raw.encode()));self.assertEqual(proof['exit'],0);self.assertTrue(proof['cleanup_confirmed'])
        self.assertEqual(proof['completion_kind'],'terminal_finished');self.assertEqual(proof['terminal_status'],4294967295);self.assertTrue(proof['isTerminal']);self.assertEqual(proof['terminal_message'],'Finished')
        self.assertFalse(record['service_completion_claimed']);self.assertFalse(record['daemon_cleanup_claimed'])
        self.assertEqual(record['row_deadline_monotonic'],self.controller.deadline)
    def test_second_handoff_booted_after_original_files(self):
        self.first();self.calls.clear();record=self.second();self.assertEqual(record['state'],'booted_snapshot_only');self.assertEqual(len(self.calls),1)
    def test_second_handoff_shutdown_recovery_is_separate_once(self):
        self.first();self.calls.clear();self.states=['Shutdown'];self.second();self.assertEqual([cap for command,cap in self.calls],[30,30,90])
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
    def test_boot_nonzero_stops_without_bootstatus(self):
        self.states=['Shutdown'];self.boot_exit=149
        with self.assertRaises(ValueError):self.first()
        self.assertEqual([cap for command,cap in self.calls],[30,30])
    def test_bootstatus_nonzero_stops_without_more_commands(self):
        self.states=['Shutdown'];self.status_exit=124
        with self.assertRaises(ValueError):self.first()
        self.assertEqual([cap for command,cap in self.calls],[30,30,90])
    def test_shutdown_never_dispatches_a_third_device_query_or_retry(self):
        self.states=['Shutdown','Booted'];self.first()
        self.assertEqual(self.states,['Booted']);self.assertEqual([cap for command,cap in self.calls],[30,30,90])
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),3)
    def test_lease_mutated_between_bootstatus_and_return_refuses(self):
        self.states=['Shutdown']
        self.after=lambda command:self.lease.path.write_text('changed lease') if command[2]=='bootstatus' else None
        with self.assertRaises(ValueError):self.first()
        self.assertEqual([cap for command,cap in self.calls],[30,30,90])
        self.assertEqual(self.controller.record['state_handoffs']['before_files_fixture']['state'],'failed_or_refused')
    def test_lease_removed_between_bootstatus_and_return_refuses(self):
        self.states=['Shutdown']
        self.after=lambda command:self.lease.path.unlink() if command[2]=='bootstatus' else None
        with self.assertRaises((ValueError,OSError)):self.first()
        self.assertEqual(len(self.calls),3)
    def test_lease_mutated_during_final_receipt_persistence_refuses_return(self):
        self.states=['Shutdown'];original=self.f.budget.persist
        def mutate():
            original()
            record=self.controller.record.get('state_handoffs',{}).get('before_files_fixture',{})
            if record.get('state')=='bootstatus_completion_observation_only':self.lease.path.write_text('changed before return')
        self.f.budget.persist=mutate
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),3)
        self.assertEqual(self.controller.record['state_handoffs']['before_files_fixture']['state'],'failed_or_refused')
    def test_consumer_accepts_exact_bootstatus_completion_kind(self):
        self.states=['Shutdown'];self.first();self.calls.clear();self.states=['Booted']
        self.assertEqual(self.second()['state'],'booted_snapshot_only');self.assertEqual(len(self.calls),1)
    def test_consumer_rejects_arbitrary_or_mismatched_readiness_kind(self):
        self.first();prior=self.controller.record['state_handoffs']['before_files_fixture'];original=copy.deepcopy(prior);self.calls.clear()
        for state,basis in [('Booted','fresh_unique_owned_booted_inventory'),('bootstatus_completion_observation_only','fresh_unique_owned_booted_inventory'),('booted_snapshot_only',None),('finished',None),('failed_or_refused',None)]:
            with self.subTest(state=state,basis=basis):
                prior.update(state=state,readiness_basis=basis)
                with self.assertRaises(ValueError):self.second()
                self.assertEqual(self.calls,[])
        prior.clear();prior.update(original)
    def test_bootstatus_wrong_uuid_or_name_or_unknown_finished_shape_refuses(self):
        original=self.status_raw
        bad=[original.replace(base.DEVICE,'11111111-2222-4333-8444-555555555555'),
             original.replace(self.receipt['name'],'Other owned device'),
             original.replace('\tFinished\n\n',''),original.replace('\tFinished','\tUnknown'),
             original.replace('Status=4294967295','Status=5'),original.replace('isTerminal=YES','isTerminal=NO'),
             original+'Unexpected trailing output\n',original.replace('Status=4, isTerminal=NO','Status=4294967295, isTerminal=NO'),
             original.replace('Status=4, isTerminal=NO','Status=4, isTerminal=YES'),
             original.replace('\tWaiting on System App','\tFinished'),
             original+original[original.index('[2026-10-06 01:05:15'):],
             'Finished\n',original+original,'x'*65537]
        for raw in bad:
            with self.subTest(raw=raw[:80]):
                self.status_raw=raw;self.states=['Shutdown']
                with self.assertRaises(ValueError):self.first()
                self.assertEqual([cap for command,cap in self.calls],[30,30,90])
                self.assertEqual(self.controller.record['state_handoffs']['before_files_fixture']['state'],'failed_or_refused')
                self.controller.record['state_handoffs'].clear();self.calls.clear()
                self.controller.record['operations']=[operation for operation in self.controller.record['operations'] if operation['command'][:3] not in (['xcrun','simctl','boot'],['xcrun','simctl','bootstatus'])]
        self.status_raw=original
    def test_alternate_nonterminal_progress_is_unqualified_and_final_finished_still_decides(self):
        self.states=['Shutdown']
        self.status_raw=self.status_raw.replace('Status=4, isTerminal=NO','Status=2, isTerminal=NO').replace('\tWaiting on System App','\tWaiting on Data Migration\n\t\tReason: synthetic migration progress')
        record=self.first();self.assertEqual(record['state'],'bootstatus_completion_observation_only')
        self.assertEqual(record['readiness_basis'],'exact_owned_uuid_bootstatus_completion')
        self.assertEqual(record['bootstatus_completion']['terminal_status'],4294967295)
        self.assertEqual([cap for command,cap in self.calls],[30,30,90])
        self.assertNotIn('nonterminal_status',record['bootstatus_completion'])
    def test_exact_retained_already_booted_form_records_no_fabricated_terminal_fields(self):
        self.states=['Shutdown']
        self.status_raw='Monitoring boot status for '+self.receipt['name']+' ('+base.DEVICE+').\nDevice already booted, nothing to do.\n\n'
        record=self.first();proof=record['bootstatus_completion']
        self.assertEqual(record['state'],'bootstatus_completion_observation_only')
        self.assertEqual(proof['completion_kind'],'already_booted_no_work')
        self.assertEqual(proof['completion_message'],'Device already booted, nothing to do.')
        for key in ['terminal_status','isTerminal','terminal_message']:self.assertNotIn(key,proof)
        self.assertEqual(proof['stdout_sha256'],hashlib.sha256(self.status_raw.encode()).hexdigest())
        self.assertEqual(proof['stdout_bytes'],len(self.status_raw.encode()));self.assertTrue(proof['cleanup_confirmed'])
        self.assertEqual([cap for command,cap in self.calls],[30,30,90]);self.assertFalse(record['service_completion_claimed'])
        self.calls.clear();self.states=['Booted'];self.assertEqual(self.second()['state'],'booted_snapshot_only')
    def test_already_booted_near_match_mixed_duplicate_or_foreign_identity_refuses(self):
        good='Monitoring boot status for '+self.receipt['name']+' ('+base.DEVICE+').\nDevice already booted, nothing to do.\n\n'
        bad=[good.replace(base.DEVICE,'11111111-2222-4333-8444-555555555555'),good.replace(self.receipt['name'],'Foreign name'),
             good.replace('nothing to do.','nothing to do'),good.replace('already booted','Already booted'),
             good+good,good+self.status_raw[ self.status_raw.index('[2026-10-06 01:05:15'):],
             good.replace('Device already booted, nothing to do.','Device booted, nothing to do.'),
             good.replace('Device already booted, nothing to do.','Device already booted, doing more.')]
        for raw in bad:
            with self.subTest(raw=raw[:80]):
                self.states=['Shutdown'];self.status_raw=raw
                with self.assertRaises(ValueError):self.first()
                self.assertEqual(len(self.calls),3)
                self.controller.record['state_handoffs'].clear();self.calls.clear()
                self.controller.record['operations']=[operation for operation in self.controller.record['operations'] if operation['command'][:3] not in (['xcrun','simctl','boot'],['xcrun','simctl','bootstatus'])]
    def test_already_booted_wording_does_not_replace_current_cleanup_evidence(self):
        self.states=['Shutdown'];self.status_raw='Monitoring boot status for '+self.receipt['name']+' ('+base.DEVICE+').\nDevice already booted, nothing to do.\n\n'
        self.operation_edit=lambda operation,command:operation.pop('cleanup_confirmed',None) if command[2]=='bootstatus' else None
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),3);self.assertTrue(barrier.blocked())
    def test_bootstatus_completion_requires_actual_zero_timely_clean_operation(self):
        for edit in [dict(exit=149),dict(elapsed_seconds=92),dict(elapsed_seconds=None),dict(elapsed_seconds=float('nan')),dict(output_bytes=None),dict(output_bytes=1)]:
            with self.subTest(edit=edit):
                self.states=['Shutdown'];self.operation_edit=lambda operation,command:operation.update(edit) if command[2]=='bootstatus' else None
                with self.assertRaises(ValueError):self.first()
                self.assertEqual(len(self.calls),3)
                self.controller.record['state_handoffs'].clear();self.calls.clear()
                self.controller.record['operations']=[operation for operation in self.controller.record['operations'] if operation['command'][:3] not in (['xcrun','simctl','boot'],['xcrun','simctl','bootstatus'])]
    def test_unknown_bootstatus_cleanup_stops_return(self):
        self.states=['Shutdown'];self.operation_edit=lambda operation,command:operation.update(cleanup_confirmed=None) if command[2]=='bootstatus' else None
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),3);self.assertTrue(barrier.blocked())
    def test_actual_late_bootstatus_return_stops(self):
        self.states=['Shutdown'];self.after=lambda command:setattr(self.f.clock,'now',self.f.clock.now+92) if command[2]=='bootstatus' else None
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),3);self.assertTrue(barrier.blocked())
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
        self.states=['Shutdown'];self.consume_after_completed('list',143.99)
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),1);self.assertEqual(self.controller.record['state_handoffs']['before_files_fixture']['boot_attempts'],0)
    def test_missing_bootstatus_full_window_refused_after_one_returned_boot(self):
        self.states=['Shutdown'];self.consume_after_completed('boot',109.99)
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),2)
    def test_finished_bootstatus_needs_no_redundant_readback_window(self):
        self.states=['Shutdown'];self.consume_after_completed('bootstatus',49.99)
        record=self.first();self.assertEqual(record['state'],'bootstatus_completion_observation_only')
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
        self.assertEqual(handoff.CAPS,{'precheck':30,'boot':30,'bootstatus':90})
        self.assertEqual(1500+2*sum(handoff.CAPS.values()),1800)
        self.assertEqual(1800+16*2,1832);self.assertEqual(1800+18*2,1836)
        self.assertEqual(handoff.CAPS['boot']+handoff.CAPS['bootstatus']+4+mini.CLEANUP,144)

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
    def test_timed_out_bootstatus_stops_return(self):
        self.states=['Shutdown'];self.operation_edit=lambda operation,command:operation.update(state='timed_out',exit=124) if command[2]=='bootstatus' else None
        with self.assertRaises(ValueError):self.first()
        self.assertEqual(len(self.calls),3);self.assertTrue(barrier.blocked())
    def test_exact_recovery_chain_admission_boundary(self):
        self.states=['Shutdown','Booted'];self.consume_after_completed('list',144)
        record=self.first();self.assertEqual(record['state'],'bootstatus_completion_observation_only');self.assertEqual(len(self.calls),3)

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



class IOSFirstBootstrapTests(unittest.TestCase):
    """Closed source/clock/operation doubles; no native bootstrap proof."""
    def setUp(self):
        import ios_original_release_route as route
        self.f=base.Fixture();self.lease=None;self.state='Shutdown';self.boot_raw=None;self.edit_operation=None
        for path in (route.CANONICAL,route.WORKFLOW):
            target=self.f.root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((base.ROOT/path).read_bytes())
        os.environ.update(GITHUB_REF=route.REF,GITHUB_WORKFLOW_REF=route.WORKFLOW_REF,GITHUB_JOB='platform',
                          IOS_FIRST_RELEASE_CANDIDATE_ONLY='true',RUNNER_OS='macOS',RUNNER_ARCH='ARM64')
        origin=json.loads(self.f.origin.read_text());origin['caps']=mini.IOS_FIRST_CAPS;self.f.origin.write_text(json.dumps(origin))
        self.f.budget.path.unlink();self.f.budget=mini.Budget(self.f.clock)
        for phase in ('prepare','build'):
            self.f.budget.enter(phase);self.f.budget.state['phases'][phase]['status']='completed';self.f.budget.persist()
        original=self.f.executor
        def execute(command,cap,**kwargs):
            if command[:3] in (['xcrun','simctl','boot'],['xcrun','simctl','bootstatus']):
                self.f.calls.append((command,cap));self.f.clock.now+=.01
                raw='' if command[2]=='boot' else self.boot_raw or bootstatus_output('QRCatcher Mini 123-1',base.DEVICE)
                operation={'command':command,'timeout_seconds':cap,'state':'completed','exit':0,'cleanup_confirmed':True,
                           'elapsed_seconds':.01,'output_bytes':len(raw.encode())}
                if self.edit_operation:self.edit_operation(operation,command)
                return 0,raw,operation
            result=original(command,cap,**kwargs)
            if self.edit_operation:self.edit_operation(result[2],command)
            return result
        self.f.executor=execute
    def tearDown(self):
        if self.lease:self.lease.close(False)
        self.f.close()
    def configure(self,owned=True):
        self.receipt=self.f.configure();self.f.readback_edit=lambda value:value['devices'][base.RUNTIME][0].update(state=self.state)
        phase=self.f.budget.state['phases']['mini']
        if owned:phase['status']='row_running'
        self.controller=mini.Controller(self.f.budget,'mini',phase['deadline'],self.f.executor)
        if owned:
            self.lease=mini.Claim(self.f.budget,None,'full_row_dispatched_once',mini.STOP);mini._ROW_LEASE=self.lease
        return self.receipt
    def bootstrap(self):return handoff.ensure_owned_booted(self.controller,base.DEVICE,self.receipt,handoff.FIRST_HANDOFF)
    def test_shutdown_first_pair_is210_and_does_not_query_after_boot(self):
        self.configure();start=self.controller.record['started'];deadline=self.controller.deadline
        record=self.bootstrap();handoff.qualified_first_bootstrap(self.controller,base.DEVICE,self.receipt)
        self.assertEqual([cap for command,cap in self.f.calls],[30,60,30,30,30,210])
        self.assertEqual(record['state'],'bootstatus_completion_observation_only');self.assertFalse(record['automation_session_stability_claimed'])
        self.assertEqual(self.controller.record['started'],start);self.assertEqual(self.controller.deadline,deadline)
        self.assertEqual(self.receipt['pretest_boot_completion'],'not_requested');self.assertEqual(self.receipt['pretest_installed_bytes'],'not_observed')
    def test_booted_first_snapshot_skips_pair_with_honest_residual_basis(self):
        self.configure();self.state='Booted';record=self.bootstrap()
        handoff.qualified_first_bootstrap(self.controller,base.DEVICE,self.receipt)
        mini.admit_full_ios_first_row(self.f.budget,self.controller.deadline,'layout')
        self.assertEqual(record['state'],'booted_snapshot_only');self.assertEqual(len(self.f.calls),4)
        admission=self.controller.record['row_admissions']['layout']
        self.assertEqual(admission['completed_first_bootstrap_debit_seconds'],32)
        self.assertEqual(admission['skipped_first_boot_pair_seconds'],244)
    def test_full_reservation_arithmetic_matches_three_fixed_residuals(self):
        self.assertEqual(mini.IOS_FIRST_ROW_COMMAND_SECONDS,1820+270)
        self.assertEqual(mini.IOS_FIRST_ROW_OPERATIONS,18+3)
        self.assertEqual(mini.IOS_FIRST_ROW_RESERVATION,2152)
        self.assertEqual(mini.IOS_FIRST_RESERVATIONS,{'configure':2152,'first_bootstrap':2026,'layout':1750})
        self.assertEqual(2152-120-6,2026);self.assertEqual(2026-270-6,1750);self.assertEqual(2220-2152,68)
    def test_exact_full_configure_window_admitted_before_inventory(self):
        original=self.f.budget.enter
        def enter(phase):
            deadline=original(phase);self.f.clock.now=deadline-2152;return deadline
        self.f.budget.enter=enter;self.configure()
        self.assertEqual(len(self.f.calls),3)
        self.assertEqual(self.controller.record['row_admissions']['configure']['required_seconds'],2152)
    def test_insufficient_full_configure_window_stops_before_inventory(self):
        original=self.f.budget.enter
        def enter(phase):
            deadline=original(phase);self.f.clock.now=deadline-2152+.01;return deadline
        self.f.budget.enter=enter
        with self.assertRaises(ValueError):self.f.configure()
        self.assertEqual(self.f.calls,[])
    def test_exact2026_after_clean_configure_admitted(self):
        self.configure();self.f.clock.now=self.controller.deadline-2026;self.bootstrap()
        self.assertEqual(len(self.f.calls),6)
        self.assertEqual(self.controller.record['row_admissions']['first_bootstrap']['completed_configure_debit_seconds'],126)
    def test_insufficient2026_after_configure_stops_before_precheck(self):
        self.configure();self.f.clock.now=self.controller.deadline-2026+.01
        with self.assertRaises(ValueError):self.bootstrap()
        self.assertEqual(len(self.f.calls),3)
    def test_exact1750_after_bootstrap_admitted(self):
        self.configure();self.bootstrap();self.f.clock.now=self.controller.deadline-1750
        handoff.qualified_first_bootstrap(self.controller,base.DEVICE,self.receipt)
        mini.admit_full_ios_first_row(self.f.budget,self.controller.deadline,'layout')
        self.assertEqual(self.controller.record['row_admissions']['layout']['required_seconds'],1750)
    def test_insufficient1750_after_bootstrap_stops_before_layout(self):
        self.configure();self.bootstrap();self.f.clock.now=self.controller.deadline-1750+.01
        with self.assertRaises(ValueError):mini.admit_full_ios_first_row(self.f.budget,self.controller.deadline,'layout')
        self.assertFalse(any(command[0]=='xcodebuild' for command,cap in self.f.calls))
    def test_missing_wrong_late_or_unclean_configure_operation_stops_precheck(self):
        self.configure();original=copy.deepcopy(self.controller.record['operations'])
        variants=[original[:2]]
        for index,change in [(0,{'cap':31}),(0,{'timeout_seconds':31}),(1,{'created_device':'11111111-2222-4333-8444-555555555555'}),(0,{'output_sha256':'f'*64}),(1,{'command':['xcrun','simctl','create','foreign']}),
                             (1,{'exit':True}),(1,{'elapsed_seconds':62}),(2,{'cleanup_confirmed':False}),
                             (2,{'state':'unknown'}),(2,{'elapsed_seconds':float('nan')})]:
            rows=copy.deepcopy(original);rows[index].update(change);variants.append(rows)
        for rows in variants:
            with self.subTest(rows=rows):
                self.controller.record['operations']=rows
                with self.assertRaises(ValueError):self.bootstrap()
                self.assertEqual(len(self.f.calls),3)
        self.controller.record['operations']=original
    def test_missing_original_full_row_admission_refuses_bootstrap(self):
        self.configure();self.controller.record['row_admissions'].pop('configure')
        with self.assertRaises(ValueError):self.bootstrap()
        self.assertEqual(len(self.f.calls),3)
    def test_changed_original_receipt_or_inventory_identity_stops(self):
        self.configure();path=self.f.root/'build/ipad-mini-owned-device.json';original=path.read_bytes()
        path.write_text('{}')
        with self.assertRaises(ValueError):self.bootstrap()
        self.assertEqual(len(self.f.calls),3);path.write_bytes(original)
        self.f.readback_edit=lambda value:value['devices'][base.RUNTIME][0].update(isAvailable=False)
        with self.assertRaises(ValueError):self.bootstrap()
        self.assertEqual(len(self.f.calls),4)
    def test_unknown_first_state_or_completion_stops_all_later_commands(self):
        self.configure();self.state='Booting'
        with self.assertRaises(ValueError):self.bootstrap()
        self.assertEqual(len(self.f.calls),4)
        self.assertFalse(any(command[0]=='xcodebuild' for command,cap in self.f.calls))
    def test_first210_reuses_exact_already_booted_parser(self):
        self.configure();self.boot_raw='Monitoring boot status for QRCatcher Mini 123-1 ('+base.DEVICE+').\nDevice already booted, nothing to do.\n\n'
        record=self.bootstrap();handoff.qualified_first_bootstrap(self.controller,base.DEVICE,self.receipt)
        self.assertEqual(record['bootstatus_completion']['completion_kind'],'already_booted_no_work')
        self.assertNotIn('terminal_status',record['bootstatus_completion'])
    def test_unknown_first_bootstatus_stops_before_layout(self):
        self.configure();self.boot_raw='Finished\n'
        with self.assertRaises(ValueError):self.bootstrap()
        self.assertEqual(len(self.f.calls),6)
    def test_late_unclean_or_unknown_first_bootstatus_stops(self):
        self.configure();self.edit_operation=lambda operation,command:operation.update(elapsed_seconds=212) if command[2]=='bootstatus' else None
        with self.assertRaises(ValueError):self.bootstrap()
        self.assertEqual(len(self.f.calls),6)
    def test_wrong_first_bootstrap_proof_stops_before_layout_command(self):
        self.configure(owned=False);original=handoff.ensure_owned_booted
        def changed(*args):
            result=original(*args)
            if args[-1]==handoff.FIRST_HANDOFF:result['bootstatus_completion']['stdout_sha256']='f'*64
            return result
        from unittest.mock import patch
        with patch.object(handoff,'ensure_owned_booted',side_effect=changed),self.assertRaises(ValueError):self.f.row()
        self.assertEqual(len(self.f.calls),6)
        self.assertFalse(any(command[0]=='xcodebuild' for command,cap in self.f.calls))
    def test_unclean_first_precheck_stops_all_row_commands(self):
        self.configure(owned=False)
        self.edit_operation=lambda operation,command:operation.update(cleanup_confirmed=False) if command==['xcrun','simctl','list','devices','available','-j'] else None
        with self.assertRaises(ValueError):self.f.row()
        self.assertEqual(len(self.f.calls),4);self.assertTrue(barrier.blocked())
    def test_unknown_first_bootstatus_operation_stops_all_row_commands(self):
        self.configure(owned=False)
        self.edit_operation=lambda operation,command:operation.update(state='unknown') if command[2]=='bootstatus' else None
        with self.assertRaises(ValueError):self.f.row()
        self.assertEqual(len(self.f.calls),6);self.assertTrue(barrier.blocked())
    def test_wrong_first_boot_timeout_stops_before_bootstatus(self):
        self.configure(owned=False)
        self.edit_operation=lambda operation,command:operation.update(timeout_seconds=90) if command[2]=='boot' else None
        with self.assertRaises(ValueError):self.f.row()
        self.assertEqual(len(self.f.calls),5)
    def test_actual_late_first_bootstatus_return_stops_all_row_commands(self):
        self.configure(owned=False)
        self.edit_operation=lambda operation,command:setattr(self.f.clock,'now',self.f.clock.now+212) if command[2]=='bootstatus' else None
        with self.assertRaises(ValueError):self.f.row()
        self.assertEqual(len(self.f.calls),6);self.assertTrue(barrier.blocked())
    def test_first_bootstrap_is_ios_first_only(self):
        self.configure()
        from unittest.mock import patch
        with patch.dict(os.environ,{'GITHUB_REF':'refs/heads/codex/apple-platforms'}):
            with self.assertRaises(ValueError):self.bootstrap()
        self.assertEqual(len(self.f.calls),3)


if __name__=='__main__':unittest.main()
