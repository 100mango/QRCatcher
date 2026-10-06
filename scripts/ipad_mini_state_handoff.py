"""Closed diagnostic-only state handoffs for the original full Mini row.

The parent must admit the diagnostic identity/profile and wire these two fixed
handoffs. This module creates no device, installs no app and resets no clock.
A Booted inventory is a momentary observation, not service/daemon-cleanup proof.
The Shutdown path observes a closed exact-owned bootstatus completion and a clean,
timely process return, not a fresh Booted JSON snapshot or continuous state.
Human CLI output is not a general stable API: only the retained Xcode27 output
shape is admitted here; current authoritative help bytes were not available.
"""
import hashlib
import math
import os
import re

import ipad_mini_setup as mini

HANDOFFS=('before_files_fixture','before_photos_seed')
CAPS={'precheck':30,'boot':30,'bootstatus':90}
READINESS={'booted_snapshot_only':'fresh_unique_owned_booted_inventory',
           'bootstatus_completion_observation_only':'exact_owned_uuid_bootstatus_completion'}


def ownership(controller,device,receipt):
    mini.require(controller.phase=='mini' and controller.record.get('status')=='row_running' and
                 controller.record.get('deadline')==controller.deadline,'Original running full-row clock required')
    mini.require(mini._ROW_LEASE is not None,'Original full-row ownership lease required')
    mini._ROW_LEASE.current()
    mini.require(mini.valid_uuid(device) and os.environ.get('MINI_SIMULATOR_ID')==device and isinstance(receipt,dict),
                 'Exact original owned Mini destination required')
    expected={'name':'QRCatcher Mini '+controller.budget.identity['run_id']+'-'+controller.budget.identity['run_attempt'],
              'device':device,'runtime':'com.apple.CoreSimulator.SimRuntime.iOS-27-0',
              'row_started_monotonic':controller.record['started'],'row_deadline_monotonic':controller.deadline,
              'state':'configured_shutdown_device_only','deployment_owner':'xcodebuild',
              'pretest_boot_completion':'not_requested','pretest_installed_bytes':'not_observed',
              **controller.budget.identity}
    mini.require(all(receipt.get(key)==value for key,value in expected.items()),'Foreign or stale configuration ownership')
    kind=receipt.get('device_type')
    mini.require(isinstance(kind,str) and re.fullmatch(r'com\.apple\.CoreSimulator\.SimDeviceType\.[A-Za-z0-9-]{1,100}',kind),
                 'Unknown original Mini device type')
    return {'device':device,'name':expected['name'],'runtime':expected['runtime'],'device_type':kind}


def read_state(controller,expected,cap,record):
    command=['xcrun','simctl','list','devices','available','-j']
    code,raw=controller.command(command,cap)
    mini.require(code==0,'Owned device state inventory failed')
    value=mini.strict_json(raw)
    mini.require(isinstance(value,dict) and isinstance(value.get('devices'),dict) and len(value['devices'])<=128,
                 'Invalid state inventory')
    matches=[]
    for runtime,rows in value['devices'].items():
        mini.require(isinstance(runtime,str) and isinstance(rows,list) and len(rows)<=512,'Invalid runtime device rows')
        mini.require(all(isinstance(row,dict) and mini.valid_uuid(row.get('udid')) and isinstance(row.get('name'),str)
                         for row in rows),'Invalid inventory device identities')
        matches.extend((runtime,row) for row in rows if row['udid']==expected['device'] or row['name']==expected['name'])
    mini.require(len(matches)==1,'Missing or ambiguous owned device state')
    runtime,row=matches[0]
    mini.require(runtime==expected['runtime'] and row.get('udid')==expected['device'] and row.get('name')==expected['name'] and
                 row.get('deviceTypeIdentifier')==expected['device_type'] and row.get('isAvailable') is True,
                 'Foreign runtime/type/name or unavailable owned device')
    observed={**expected,'isAvailable':True,'state':row.get('state'),'inventory_sha256':hashlib.sha256(raw.encode()).hexdigest(),
              'observed_monotonic':controller.budget.clock(),'service_completion_claimed':False,'daemon_cleanup_claimed':False}
    record['observations'].append(observed);controller.budget.persist()
    mini.require(observed['state'] in ('Booted','Shutdown'),'Unknown owned device state')
    return observed['state']


def qualified_prior(controller,device,handoff):
    result='MiniUIResults-layout.xcresult' if handoff=='before_files_fixture' else 'MiniUIResults-files.xcresult'
    selectors=mini.LAYOUT if handoff=='before_files_fixture' else mini.FILES
    cap=480 if handoff=='before_files_fixture' else 240
    case=mini.test_command(device,selectors,result)
    summary=['xcrun','xcresulttool','get','test-results','summary','--path',result]
    for command,limit,exits in [(case,cap,(0,) if handoff=='before_files_fixture' else (0,65)),(summary,mini.result_summary_limit(result),(0,))]:
        matches=[operation for operation in controller.record['operations'] if operation.get('command')==command]
        mini.require(len(matches)==1,'Exact completed prior case/summary operation required')
        operation=matches[0];elapsed=operation.get('elapsed_seconds')
        mini.require(operation.get('cap')==limit and operation.get('state')=='completed' and
                     operation.get('cleanup_confirmed') is True and operation.get('exit') in exits and
                     type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<=elapsed<limit+2,
                     'Prior case/summary is late, unclean, incomplete or conflicting')


def completed_owned_command(controller,command,cap,offset):
    matches=[operation for operation in controller.record['operations'][offset:] if operation.get('command')==command]
    mini.require(len(matches)==1,'Exact once-only owned boot operation required')
    operation=matches[0];elapsed=operation.get('elapsed_seconds')
    mini.require(operation.get('cap')==cap and operation.get('state')=='completed' and
                 operation.get('cleanup_confirmed') is True and type(operation.get('exit')) is int and operation['exit']==0 and
                 type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<=elapsed<cap+2,
                 'Owned boot operation is nonzero, late, unclean or incomplete')
    return operation


def completed_bootstatus(raw,expected):
    """Fail closed on any output outside the retained public Xcode27 shape."""
    mini.require(isinstance(raw,str) and 0<len(raw.encode())<=65536,'Missing or oversized bootstatus output')
    header='Monitoring boot status for '+expected['name']+' ('+expected['device']+').\n'
    proof={'stdout_sha256':hashlib.sha256(raw.encode()).hexdigest(),'stdout_bytes':len(raw.encode())}
    # This wording is separately retained from an actual Xcode27 bootstatus -b
    # stdout. It proves no terminal status/Finished field; current operation
    # completion/cleanup and the original lease are still checked by the caller.
    if raw==header+'Device already booted, nothing to do.\n\n':
        return {**proof,'completion_kind':'already_booted_no_work',
                'completion_message':'Device already booted, nothing to do.'}
    stamp=r'\[[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} \+[0-9]{4}\] '
    elapsed=r'Elapsed=[0-9]{2}:[0-5][0-9]\.\n'
    # Intermediate status/detail blocks are bounded, unqualified progress.
    # Only the final known terminal outcome contributes readiness evidence.
    progress=stamp+r'Status=(?!4294967295,)[0-9]{1,10}, isTerminal=NO, '+elapsed+\
             r'(?:\t{1,4}(?!Finished\n)[^\x00-\x1f\x7f]{1,1024}\n){1,16}\n'
    finished=stamp+r'Status=4294967295, isTerminal=YES, '+elapsed+r'\tFinished\n\n'
    mini.require(re.fullmatch(re.escape(header)+'(?:'+progress+')*'+finished,raw) is not None,
                 'Unknown bootstatus output or missing exact owned terminal Finished')
    return {**proof,'completion_kind':'terminal_finished','terminal_status':4294967295,'isTerminal':True,'terminal_message':'Finished'}


def ensure_owned_booted(controller,device,receipt,handoff):
    """One precheck; Shutdown permits one bounded exact-owned boot/status pair."""
    mini.require(handoff in HANDOFFS,'Only the two original full-row handoffs are permitted')
    expected=ownership(controller,device,receipt)
    lease=mini._ROW_LEASE
    qualified_prior(controller,device,handoff)
    layout=controller.record.get('results',{}).get('MiniUIResults-layout.xcresult',{})
    mini.require(layout=={'totalTestCount':2,'passedTests':2,'failedTests':0,'skippedTests':0,'expectedFailures':0},
                 'The two original layout cases must qualify before either handoff')
    if handoff=='before_photos_seed':
        files=controller.record.get('results',{}).get('MiniUIResults-files.xcresult',{})
        mini.require(files.get('totalTestCount')==1 and files.get('skippedTests')==0 and files.get('expectedFailures')==0 and
                     type(files.get('passedTests')) is int and type(files.get('failedTests')) is int and
                     files['passedTests']+files['failedTests']==1,'The original Files case must qualify before seed handoff')
        prior=controller.record.get('state_handoffs',{}).get('before_files_fixture',{})
        mini.require(prior.get('state') in READINESS and prior.get('readiness_basis')==READINESS[prior['state']],
                     'The original fixture handoff must complete first')
    records=controller.record.setdefault('state_handoffs',{})
    mini.require(handoff not in records,'This handoff cannot retry or reset its clock')
    record={'handoff':handoff,'device':device,'state':'pending','boot_attempts':0,'bootstatus_attempts':0,
            'caps':dict(CAPS),'started_monotonic':controller.budget.clock(),'row_deadline_monotonic':controller.deadline,
            'observations':[],'service_completion_claimed':False,'daemon_cleanup_claimed':False}
    records[handoff]=record;controller.budget.persist()
    operation_start=len(controller.record['operations'])
    try:
        state=read_state(controller,expected,CAPS['precheck'],record)
        if state=='Shutdown':
            # Refuse before the first mutation if the entire once-only recovery
            # pair, its two existing two-second cleanup bounds and the
            # original twenty-second admission reserve cannot still fit.
            controller.budget.next('mini',CAPS['boot']+CAPS['bootstatus']+4,controller.deadline)
            record['boot_attempts']=1;controller.budget.persist()
            boot=['xcrun','simctl','boot',device]
            code,_=controller.command(boot,CAPS['boot'])
            mini.require(type(code) is int and code==0,'The one permitted owned boot did not complete successfully')
            completed_owned_command(controller,boot,CAPS['boot'],operation_start)
            record['bootstatus_attempts']=1;controller.budget.persist()
            status=['xcrun','simctl','bootstatus',device,'-b']
            code,raw=controller.command(status,CAPS['bootstatus'])
            mini.require(type(code) is int and code==0,'The one permitted bootstatus did not return successfully')
            operation=completed_owned_command(controller,status,CAPS['bootstatus'],operation_start)
            proof=completed_bootstatus(raw,expected)
            mini.require(type(operation.get('output_bytes')) is int and operation['output_bytes']==proof['stdout_bytes'],
                         'Bootstatus output is incomplete or its size is unknown')
            record['bootstatus_completion']={**expected,**proof,'state':operation['state'],'exit':operation['exit'],
                                            'elapsed_seconds':operation['elapsed_seconds'],'cleanup_confirmed':True,
                                            'observed_monotonic':controller.budget.clock()}
            record['state']='bootstatus_completion_observation_only'
        else:record['state']='booted_snapshot_only'
        record['readiness_basis']=READINESS[record['state']]
        record['completed_monotonic']=controller.budget.clock();controller.budget.persist()
        if state=='Shutdown':
            mini.require(mini._ROW_LEASE is lease and ownership(controller,device,receipt)==expected,
                         'Original owned Mini lease changed during bootstatus')
        return record
    except BaseException as error:
        record['state']='failed_or_refused';record['stop_reason']=str(error)[:200];controller.budget.persist();raise
