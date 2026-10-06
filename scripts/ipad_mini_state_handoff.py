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
FIRST_HANDOFF='before_first_layout'
FIRST_CAPS={'precheck':30,'boot':30,'bootstatus':210}
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
    if record['handoff']==FIRST_HANDOFF:
        operation=completed_owned_command(controller,command,cap,3)
        mini.require(operation.get('timeout_seconds')==cap and operation.get('output_bytes')==len(raw.encode()),
                     'Incomplete or wrong-cap first owned precheck output')
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
    if mini.supplement_profile():
        mini.require(handoff=='before_photos_seed','The supplement selects no Files fixture handoff')
        result='MiniUIResults-warmup.xcresult';selectors=mini.WARMUP;cap=480
    else:
        result='MiniUIResults-layout.xcresult' if handoff=='before_files_fixture' else 'MiniUIResults-files.xcresult'
        selectors=mini.LAYOUT if handoff=='before_files_fixture' else mini.FILES
        cap=480 if handoff=='before_files_fixture' else 240
    case=mini.test_command(device,selectors,result)
    summary=['xcrun','xcresulttool','get','test-results','summary','--path',result]
    for command,limit,exits in [(case,cap,(0,) if mini.supplement_profile() or handoff=='before_files_fixture' else (0,65)),(summary,mini.result_summary_limit(result),(0,))]:
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


def qualified_configuration(controller,expected,receipt):
    """The first precheck has no prior test; bind the original clean configure."""
    retained=mini.strict_json(mini.read_regular(controller.budget.root/'build/ipad-mini-owned-device.json',4096))
    mini.require(retained==receipt and receipt.get('absent_from_initial_inventory') is True and
                 type(receipt.get('initial_device_count')) is int and 0<=receipt['initial_device_count']<=4096 and
                 not controller.record.get('results') and not controller.record.get('state_handoffs'),
                 'Original first-bootstrap configuration receipt required')
    admission=controller.record.get('row_admissions',{}).get('configure',{})
    admitted=admission.get('admitted_monotonic')
    mini.require(admission.get('required_seconds')==2152 and admission.get('cleanup_reserve_seconds')==mini.CLEANUP and
                 admission.get('row_started_monotonic')==controller.record['started'] and
                 admission.get('row_deadline_monotonic')==controller.deadline and
                 admission.get('completed_configure_debit_seconds')==0 and admission.get('first_bootstrap_removed_seconds')==0 and
                 type(admitted) in (int,float) and math.isfinite(admitted) and
                 controller.record['started']<=admitted<=controller.deadline-2152,
                 'Original complete configure admission receipt required')
    commands=[(['xcrun','simctl','list','-j'],30,'initial_inventory_sha256'),
              (['xcrun','simctl','create',expected['name'],expected['device_type'],expected['runtime']],60,None),
              (['xcrun','simctl','list','devices','available','-j'],30,'readback_sha256')]
    operations=controller.record['operations']
    mini.require(len(operations)==3,'Only original configure operations may precede first bootstrap')
    for operation,(command,cap,hash_key) in zip(operations,commands):
        elapsed=operation.get('elapsed_seconds');digest=operation.get('output_sha256')
        mini.require(operation.get('command')==command and operation.get('cap')==cap and
                     operation.get('timeout_seconds')==cap and
                     operation.get('state')=='completed' and operation.get('cleanup_confirmed') is True and
                     type(operation.get('exit')) is int and operation['exit']==0 and
                     type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<=elapsed<cap+2 and
                     type(operation.get('output_bytes')) is int and operation['output_bytes']>0 and
                     isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) is not None and
                     (hash_key is None or receipt.get(hash_key)==digest),
                     'First bootstrap requires exact clean timely configure operations')
    mini.require(operations[1].get('created_device')==expected['device'],'First bootstrap must use the exact configured UUID')


def qualified_first_bootstrap(controller,device,receipt):
    expected=ownership(controller,device,receipt)
    record=controller.record.get('state_handoffs',{}).get(FIRST_HANDOFF,{})
    mini.require(record.get('state') in READINESS and record.get('readiness_basis')==READINESS[record['state']] and
                 record.get('caps')==FIRST_CAPS and record.get('device')==device and
                 record.get('row_started_monotonic')==controller.record['started'] and
                 record.get('row_deadline_monotonic')==controller.deadline and
                 len(record.get('observations',[]))==1,'Original qualified first-bootstrap receipt required')
    observation=record['observations'][0]
    mini.require(all(observation.get(key)==value for key,value in expected.items()) and observation.get('isAvailable') is True,
                 'First-bootstrap observation belongs to another device')
    precheck=['xcrun','simctl','list','devices','available','-j']
    operation=completed_owned_command(controller,precheck,30,3)
    mini.require(operation.get('timeout_seconds')==30 and operation.get('output_sha256')==observation.get('inventory_sha256'),
                 'First-bootstrap precheck receipt is not the current output')
    if record['state']=='bootstatus_completion_observation_only':
        mini.require(observation.get('state')=='Shutdown' and len(controller.record['operations'])==6 and
                     record.get('boot_attempts')==1 and record.get('bootstatus_attempts')==1,
                     'Original once-only first-bootstrap chain required')
        boot=completed_owned_command(controller,['xcrun','simctl','boot',device],30,3)
        operation=completed_owned_command(controller,['xcrun','simctl','bootstatus',device,'-b'],210,3)
        proof=record.get('bootstatus_completion',{})
        mini.require(boot.get('timeout_seconds')==30 and operation.get('timeout_seconds')==210 and
                     isinstance(operation.get('output_sha256'),str) and re.fullmatch('[0-9a-f]{64}',operation['output_sha256']) is not None and
                     all(proof.get(key)==value for key,value in expected.items()) and
                     proof.get('stdout_sha256')==operation.get('output_sha256') and
                     proof.get('stdout_bytes')==operation.get('output_bytes') and
                     proof.get('state')=='completed' and type(proof.get('exit')) is int and proof['exit']==0 and
                     proof.get('cleanup_confirmed') is True and proof.get('elapsed_seconds')==operation.get('elapsed_seconds') and
                     ((proof.get('completion_kind')=='terminal_finished' and proof.get('terminal_status')==4294967295 and
                       proof.get('isTerminal') is True and proof.get('terminal_message')=='Finished') or
                      (proof.get('completion_kind')=='already_booted_no_work' and
                       proof.get('completion_message')=='Device already booted, nothing to do.' and
                       not any(key in proof for key in ('terminal_status','isTerminal','terminal_message')))),
                     'First-bootstrap exact completion proof changed before layout')
    else:
        mini.require(observation.get('state')=='Booted' and len(controller.record['operations'])==4 and
                     record.get('boot_attempts')==0 and record.get('bootstatus_attempts')==0,
                     'Original first Booted snapshot required')
    mini.require(mini.strict_json(mini.read_regular(controller.budget.root/'build/ipad-mini-owned-device.json',4096))==receipt,
                 'Original configure receipt changed before layout')


def ensure_owned_booted(controller,device,receipt,handoff):
    """One precheck; Shutdown permits one bounded exact-owned boot/status pair."""
    first=handoff==FIRST_HANDOFF
    mini.require(handoff in HANDOFFS or (first and mini.ios_first_profile()),
                 'Only admitted original full-row handoffs are permitted')
    expected=ownership(controller,device,receipt)
    lease=mini._ROW_LEASE
    if first:
        qualified_configuration(controller,expected,receipt)
        mini.admit_full_ios_first_row(controller.budget,controller.deadline,'first_bootstrap')
    else:
        qualified_prior(controller,device,handoff)
        if mini.supplement_profile():
            warmup=controller.record.get('results',{}).get('MiniUIResults-warmup.xcresult',{})
            mini.require(warmup=={'totalTestCount':1,'passedTests':1,'failedTests':0,'skippedTests':0,'expectedFailures':0},
                         'The selected original picker warmup must qualify before the seed handoff')
            prior=controller.record.get('state_handoffs',{}).get(FIRST_HANDOFF,{})
            mini.require(prior.get('state') in READINESS and prior.get('readiness_basis')==READINESS[prior['state']] and
                         prior.get('selected_case_stage')=='picker_warmup',
                         'The selected warmup bootstrap must complete first')
        else:
            layout=controller.record.get('results',{}).get('MiniUIResults-layout.xcresult',{})
            mini.require(layout=={'totalTestCount':2,'passedTests':2,'failedTests':0,'skippedTests':0,'expectedFailures':0},
                         'The two original layout cases must qualify before either handoff')
    if handoff=='before_photos_seed' and not mini.supplement_profile():
        files=controller.record.get('results',{}).get('MiniUIResults-files.xcresult',{})
        mini.require(files.get('totalTestCount')==1 and files.get('skippedTests')==0 and files.get('expectedFailures')==0 and
                     type(files.get('passedTests')) is int and type(files.get('failedTests')) is int and
                     files['passedTests']+files['failedTests']==1,'The original Files case must qualify before seed handoff')
        prior=controller.record.get('state_handoffs',{}).get('before_files_fixture',{})
        mini.require(prior.get('state') in READINESS and prior.get('readiness_basis')==READINESS[prior['state']],
                     'The original fixture handoff must complete first')
    records=controller.record.setdefault('state_handoffs',{})
    mini.require(handoff not in records,'This handoff cannot retry or reset its clock')
    caps=FIRST_CAPS if first else CAPS
    record={'handoff':handoff,'device':device,'state':'pending','boot_attempts':0,'bootstatus_attempts':0,
            'caps':dict(caps),'started_monotonic':controller.budget.clock(),'row_deadline_monotonic':controller.deadline,
            'observations':[],'service_completion_claimed':False,'daemon_cleanup_claimed':False}
    if first:
        record['row_started_monotonic']=controller.record['started']
        record['automation_session_stability_claimed']=False
        record['full_row_reservation_seconds']=mini.IOS_FIRST_RESERVATIONS['first_bootstrap']
        if mini.supplement_profile():record['selected_case_stage']='picker_warmup'
    records[handoff]=record;controller.budget.persist()
    operation_start=len(controller.record['operations'])
    try:
        if first:controller.budget.next('mini',mini.IOS_FIRST_RESERVATIONS['first_bootstrap']-mini.CLEANUP,controller.deadline)
        state=read_state(controller,expected,caps['precheck'],record)
        if state=='Shutdown':
            # Refuse before the first mutation if the entire once-only recovery
            # pair, its two existing two-second cleanup bounds and the
            # original twenty-second admission reserve cannot still fit.
            controller.budget.next('mini',caps['boot']+caps['bootstatus']+4,controller.deadline)
            record['boot_attempts']=1;controller.budget.persist()
            boot=['xcrun','simctl','boot',device]
            code,_=controller.command(boot,caps['boot'])
            mini.require(type(code) is int and code==0,'The one permitted owned boot did not complete successfully')
            operation=completed_owned_command(controller,boot,caps['boot'],operation_start)
            if first:mini.require(operation.get('timeout_seconds')==caps['boot'],'Wrong original first boot cap')
            record['bootstatus_attempts']=1;controller.budget.persist()
            status=['xcrun','simctl','bootstatus',device,'-b']
            code,raw=controller.command(status,caps['bootstatus'])
            mini.require(type(code) is int and code==0,'The one permitted bootstatus did not return successfully')
            operation=completed_owned_command(controller,status,caps['bootstatus'],operation_start)
            if first:mini.require(operation.get('timeout_seconds')==caps['bootstatus'],'Wrong original first bootstatus cap')
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
        if state=='Shutdown' or first:
            mini.require(mini._ROW_LEASE is lease and ownership(controller,device,receipt)==expected,
                         'Original owned Mini lease changed during bootstatus')
        if first:
            mini.require(mini.strict_json(mini.read_regular(controller.budget.root/'build/ipad-mini-owned-device.json',4096))==receipt,
                         'Original configure receipt changed during first bootstrap')
        return record
    except BaseException as error:
        record['state']='failed_or_refused';record['stop_reason']=str(error)[:200];controller.budget.persist();raise
