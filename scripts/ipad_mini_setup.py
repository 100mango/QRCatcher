"""Closed canonical Mini setup/full-row controller; never a one-case driver.

The immutable workflow clock covers checkout/main and its separately bounded
post action. Configuration and all four original cases share one 1620s clock.
No deadline reset, destination fallback, daemon cleanup or installed-byte claim.
"""
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import runpy
import selectors
import stat
import subprocess
import sys
import time
import uuid

from atomic_json import write_json
from owned_process_group import stop_group
from owned_process_barrier import blocked, mark_unconfirmed
from watch_process import execute

CAPS = {'checkout_main':60, 'prepare':120, 'build':480, 'mini':1620,
        'export':180, 'validate':30, 'upload':60, 'summary':30,
        'final':30, 'checkout_post':60, 'overhead':30}
DIAGNOSTIC_CAPS = {**CAPS, 'mini':1920}  # Dedicated full-Mini diagnostic only.
IOS_FIRST_CAPS = {**DIAGNOSTIC_CAPS, 'build':180, 'mini':2220}
# All configuration, four cases, three summaries, fixture queries and all
# three possible Shutdown bootstrap pairs, with every post-return allowance.
IOS_FIRST_ROW_COMMAND_SECONDS = 2090
IOS_FIRST_ROW_OPERATIONS = 21
IOS_FIRST_ROW_RESERVATION = IOS_FIRST_ROW_COMMAND_SECONDS+2*IOS_FIRST_ROW_OPERATIONS+20
IOS_FIRST_RESERVATIONS = {'configure':2152,'first_bootstrap':2026,'layout':1750}
ORDER = ['prepare','build','mini','export','validate','upload','summary','final']
ROW_SECONDS = 1620
CLEANUP = 20                 # Admission reserve; existing 1s/1s cleanup unchanged.
PENDING = 'ipad-mini-inflight.json'
STOP = 'ipad-mini-row-dispatched.json'
_ACTIVE = None
_ROW_LEASE = None
LAYOUT = ['-only-testing:QRCatcherUITests/QRCatcherPadUITests',
          '-skip-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords']
FILES = ['-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealFilesImportAndReopen']
PHOTOS = ['-only-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords']


def require(value, message):
    if not value: raise ValueError(message)


def strict_json(raw):
    def pairs(rows):
        d = {}
        for key,value in rows:
            require(key not in d, 'Duplicate JSON key'); d[key] = value
        return d
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def signature(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_nlink,info.st_uid,
            info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def read_regular(path, cap=16384):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path,*path.parents)), 'Linked evidence path')
    fd = os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                before.st_uid == os.getuid() and 0 < before.st_size <= cap, 'Invalid evidence file')
        raw = os.read(fd,cap+1)
        require(len(raw)==before.st_size and signature(os.fstat(fd))==signature(before) and
                signature(path.stat())==signature(before), 'Evidence changed during read')
        return raw
    finally: os.close(fd)


def valid_uuid(value):
    try: return isinstance(value,str) and str(uuid.UUID(value)).upper()==value
    except (ValueError,TypeError): return False


def context():
    root = Path(os.environ['GITHUB_WORKSPACE'])
    require(root.is_absolute() and root.resolve(strict=True)==root and Path.cwd()==root,
            'Canonical current checkout required')
    sha = os.environ.get('GITHUB_SHA','')
    require(re.fullmatch('[0-9a-f]{40}',sha) is not None and
            os.environ.get('GITHUB_WORKFLOW_SHA')==sha and
            os.environ.get('GITHUB_REPOSITORY')=='100mango/QRCatcher' and
            os.environ.get('GITHUB_REF') in ('refs/heads/codex/apple-platforms','refs/heads/codex/mini-managed-full-row','refs/heads/codex/ios-original-release') and
            os.environ.get('GITHUB_EVENT_NAME')=='push' and
            os.environ.get('EVIDENCE_SCOPE')=='ipad_mini', 'Wrong Mini source/workflow/scope')
    if os.environ.get('GITHUB_REF')=='refs/heads/codex/mini-managed-full-row':
        from diagnostic_mini_managed_route import current_identity
        current_identity()  # Exact diagnostic source/workflow/ref; no process.
    if os.environ.get('GITHUB_REF')=='refs/heads/codex/ios-original-release':
        from ios_original_release_route import current_identity
        current_identity()  # Closed original iPhone/iPad profile; no process.
    for key in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):
        require(re.fullmatch('[1-9][0-9]{0,19}',os.environ.get(key,'')) is not None,
                'Missing run identity')
    require(os.environ.get('QRCATCHER_OWNED_PROCESS_BARRIER')==str(root/'build/owned-process-cleanup.json'),
            'Wrong process barrier')
    return root, {'source':sha,'workflow_sha':sha,'run_id':os.environ['GITHUB_RUN_ID'],
                  'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],'scope':'ipad_mini'}


def ios_first_profile():
    if os.environ.get('GITHUB_REF')!='refs/heads/codex/ios-original-release':
        return False
    from ios_original_release_route import current_identity
    current_identity()  # Explicit new source/workflow/ref/job/scope binding.
    return True


def extended_mini_profile():
    if os.environ.get('GITHUB_REF')=='refs/heads/codex/mini-managed-full-row':
        from diagnostic_mini_managed_route import current_identity
        current_identity()
        return True
    return ios_first_profile()


def schedule_caps():
    if ios_first_profile(): return IOS_FIRST_CAPS
    return DIAGNOSTIC_CAPS if extended_mini_profile() else CAPS


def admit_full_ios_first_row(budget,deadline,stage='configure'):
    if not ios_first_profile(): return
    require(budget.caps==IOS_FIRST_CAPS and deadline==budget.state['phases']['mini']['deadline'] and
            deadline==budget.state['phases']['mini']['started']+IOS_FIRST_CAPS['mini'],
            'Original iOS-first Mini schedule required')
    require(stage in IOS_FIRST_RESERVATIONS,'Unknown fixed full-row admission stage')
    reservation=IOS_FIRST_RESERVATIONS[stage]
    budget.next('mini',reservation-CLEANUP,deadline)
    record=budget.state['phases']['mini']
    admissions=record.setdefault('row_admissions',{})
    require(stage not in admissions,'Original full-row admission cannot reset')
    admissions[stage]={'required_seconds':reservation,'row_started_monotonic':record['started'],
                       'row_deadline_monotonic':deadline,'admitted_monotonic':budget.clock(),
                       'completed_configure_debit_seconds':0 if stage=='configure' else 126,
                       'first_bootstrap_removed_seconds':276 if stage=='layout' else 0,
                       'cleanup_reserve_seconds':CLEANUP}
    if stage=='layout':
        booted=record['state_handoffs']['before_first_layout']['state']=='booted_snapshot_only'
        admissions[stage]['completed_first_bootstrap_debit_seconds']=32 if booted else 276
        admissions[stage]['skipped_first_boot_pair_seconds']=244 if booted else 0
    budget.persist();budget.next('mini',reservation-CLEANUP,deadline)


def mini_project():
    if ios_first_profile():
        from ios_original_release_route import PROJECT
        return PROJECT
    return 'QRCatcher.xcodeproj'


def job_ledger_limit():
    # Only the existing exact diagnostic route gets the explicit32KiB ledger.
    # All other read/output/evidence limits and canonical16KiB stay unchanged.
    if extended_mini_profile():
        return 32768
    return 16384


class Budget:
    def __init__(self, clock=time.monotonic):
        self.clock = clock; self.root,self.identity = context()
        self.caps = schedule_caps()
        self.job_seconds = sum(self.caps.values())
        self.ledger_limit = job_ledger_limit()
        tmp = Path(os.environ['RUNNER_TEMP'])
        require(tmp.is_absolute() and tmp.resolve(strict=True)==tmp, 'Canonical runner temporary root')
        self.origin_path = tmp/('qrcatcher-mini-'+self.identity['run_id']+'-'+self.identity['run_attempt']+'.json')
        require(os.environ.get('QRCATCHER_MINI_JOB_ORIGIN')==str(self.origin_path), 'Wrong original clock path')
        self.origin_raw = read_regular(self.origin_path,2048)
        value = strict_json(self.origin_raw)
        expected = {'version':1,**self.identity,'caps':self.caps}
        require(isinstance(value,dict) and set(value)==set(expected)|{'started_monotonic'} and
                all(value[k]==v for k,v in expected.items()), 'Stale or foreign job clock')
        start = value['started_monotonic']; now = clock()
        require(type(start) in (int,float) and math.isfinite(start) and 0 < start <= now and
                math.isfinite(now), 'Invalid/nonpositive/future original clock')
        self.start = start; self.deadline = start+self.job_seconds
        (self.root/'build').mkdir(exist_ok=True)
        build=self.root/'build'
        require(build.resolve(strict=True)==build and not build.is_symlink(),'Canonical build directory required')
        self.build_identity=(build.stat().st_dev,build.stat().st_ino)
        self.path = self.root/'build/ipad-mini-job-state.json'
        self.state = strict_json(read_regular(self.path,self.ledger_limit)) if self.path.exists() else {
            'version':1,**self.identity,'started_monotonic':start,'deadline_monotonic':self.deadline,
            'phases':{},'post_checkout':{'owner':'actions-runner','separate_limit_seconds':60,
                                     'status':'pending_platform_post_action'},'full_job_accepted':False}
        require(all(self.state.get(k)==v for k,v in {**self.identity,
                'started_monotonic':start,'deadline_monotonic':self.deadline}.items()), 'Reset or stale phase state')
        require(isinstance(self.state.get('phases'),dict), 'Invalid phase ledger')
        for phase,item in self.state['phases'].items():
            require(phase in ORDER and isinstance(item,dict) and type(item.get('started')) in (int,float) and
                    math.isfinite(item['started']) and start <= item['started'] <= now and
                    item.get('deadline')==item['started']+self.caps[phase], 'Reset or extended phase clock')

    def current(self):
        build=self.root/'build'
        require(build.resolve(strict=True)==build and (build.stat().st_dev,build.stat().st_ino)==self.build_identity,
                'Original build directory changed')
        require(read_regular(self.origin_path,2048)==self.origin_raw, 'Original job clock changed')
        require(self.clock() < self.deadline, 'Original controlled job deadline expired')

    def persist(self):
        self.current(); write_json(self.path,self.state,limit=self.ledger_limit)

    def enter(self, phase):
        self.current(); require(phase in ORDER, 'Unknown fixed phase')
        old = self.state['phases'].get(phase)
        if phase=='mini' and old:
            require(old.get('status')=='configuration_ready', 'Mini row cannot restart')
            return old['deadline']
        require(old is None, 'Phase cannot restart')
        if phase in ('prepare','build','mini'):
            require(not blocked(), 'Inherited cleanup uncertainty')
            if phase=='prepare': require(self.clock()-self.start <= 90, 'Checkout/main or startup budget exceeded')
            else:
                previous = 'prepare' if phase=='build' else 'build'
                require(self.state['phases'].get(previous,{}).get('status')=='completed', 'Missing successful prerequisite')
        tail = sum(self.caps[name] for name in ORDER[ORDER.index(phase)+1:])+self.caps['checkout_post']+self.caps['overhead']
        now = self.clock()
        require(now+self.caps[phase]+tail <= self.deadline, 'Whole phase and fixed future reserves unavailable')
        deadline = now+self.caps[phase]
        self.state['phases'][phase]={'started':now,'deadline':deadline,'status':'pending','operations':[]}
        self.persist(); require(self.clock()+self.caps[phase]+tail <= self.deadline,
                                'Persistence consumed required whole phase window')
        return deadline

    def next(self, phase, cap, deadline):
        self.current(); require(self.clock()+cap+CLEANUP <= deadline,
                                'Full next-command plus cleanup window unavailable')


class Claim:
    def __init__(self, budget, command, phase, name=PENDING):
        self.budget,self.command,self.phase = budget,command,phase
        self.owner_pid=os.getpid()
        self.path = budget.root/'build'/name
        budget.current()
        require(self.path.parent.resolve(strict=True)==self.path.parent,'Canonical latch parent required')
        self.directory=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        parent=os.fstat(self.directory)
        self.parent_identity=(parent.st_dev,parent.st_ino)
        require(self.parent_identity==budget.build_identity,'Latch parent is not the original build directory')
        raw = (json.dumps({**budget.identity,'phase':phase,'owner_pid':os.getpid(),
                           'command':command},sort_keys=True)+'\n').encode()
        self.fd = os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.directory)
        os.write(self.fd,raw); os.fsync(self.fd)
        self.raw,self.initial = raw,signature(os.fstat(self.fd)); self.precheck=False
        self.dispatch_window=None

    def current(self):
        self.budget.current()
        require(os.getpid()==self.owner_pid,'Mini claim belongs to another process')
        if self.dispatch_window is not None:
            cap,deadline=self.dispatch_window
            self.budget.next(self.phase,cap,deadline)
        require(self.path.parent.resolve(strict=True)==self.path.parent, 'Fence parent changed')
        require((self.path.parent.stat().st_dev,self.path.parent.stat().st_ino)==self.parent_identity,
                'Fence parent replaced')
        os.lseek(self.fd,0,os.SEEK_SET)
        require(os.read(self.fd,4097)==self.raw and signature(os.fstat(self.fd))==self.initial and
                signature(os.stat(self.path.name,dir_fd=self.directory,follow_symlinks=False))==self.initial,
                'Mini latch changed or disappeared')

    def close(self, observed):
        global _ACTIVE
        try:
            if observed: self.current(); os.unlink(self.path.name,dir_fd=self.directory)
        except BaseException:
            mark_unconfirmed({'state':'mini_fence_identity_unconfirmed','exit':126,'cleanup_confirmed':False})
            raise
        finally: os.close(self.fd); os.close(self.directory); _ACTIVE=None


def active_claim_exists(): return _ACTIVE is not None or _ROW_LEASE is not None


def active_claim_is_current(command):
    try:
        if _ACTIVE is not None:
            _ACTIVE.current()
            return command==_ACTIVE.command or (command is None and _ACTIVE.precheck)
        if _ROW_LEASE is not None:
            _ROW_LEASE.current()
            return command is None
        return False
    except (OSError,ValueError): return False


class Controller:
    def __init__(self,budget,phase,deadline,executor=execute):
        self.budget,self.phase,self.deadline,self.executor = budget,phase,deadline,executor
        self.record = budget.state['phases'][phase]

    def command(self,command,cap,log=None):
        global _ACTIVE
        require(not blocked(), 'Inherited device uncertainty')
        self.budget.next(self.phase,cap,self.deadline)
        require(_ACTIVE is None,'Concurrent Mini controller')
        claim=Claim(self.budget,command,self.phase); _ACTIVE=claim
        claim.dispatch_window=(cap,self.deadline)
        event={'command':command,'cap':cap,'status':'pending'}; self.record['operations'].append(event)
        self.budget.persist(); observed=False
        try:
            claim.current(); self.budget.next(self.phase,cap,self.deadline)
            print('BOUNDED_COMMAND_START '+json.dumps({'seconds':cap,'command':command}),flush=True)
            began=self.budget.clock()
            tail_cap=512*1024 if command[:3]==['xcrun','simctl','list'] else 65536
            code,tail,operation=self.executor(command,cap,output_limit=16*1024*1024,tail_limit=tail_cap)
            claim.dispatch_window=None
            print('BOUNDED_COMMAND_END '+json.dumps(operation),flush=True)
            event.update(operation)
            configuring=self.record.get('status')=='pending'
            first_bootstrapping=self.record.get('state_handoffs',{}).get('before_first_layout',{}).get('state')=='pending'
            if ios_first_profile() and self.phase=='mini' and (configuring or first_bootstrapping):
                require(operation.get('output_bytes')==len(tail.encode()),'Incomplete original configure/bootstrap output')
                event['output_sha256']=hashlib.sha256(tail.encode()).hexdigest()
            observed=(operation.get('state')=='completed' and operation.get('cleanup_confirmed') is True and
                      self.budget.clock() < self.deadline and self.budget.clock()<began+cap+2)
            if log: (self.budget.root/log).write_text('BOUNDED_COMMAND_START '+json.dumps({'seconds':cap,'command':command})+'\n'+tail+'\nBOUNDED_COMMAND_END '+json.dumps(operation)+'\n')
            require(observed,'Owned command incomplete/late/cleanup unknown')
            self.budget.persist(); return code,tail
        except BaseException:
            if not observed: mark_unconfirmed({'state':'mini_command_unresolved','exit':126,'cleanup_confirmed':False})
            raise
        finally: claim.close(observed)


def inventory(controller):
    code,raw=controller.command(['xcrun','simctl','list','-j'],30)
    require(code==0,'Inventory failed'); value=strict_json(raw)
    require(isinstance(value,dict) and isinstance(value.get('runtimes'),list) and
            isinstance(value.get('devicetypes'),list) and isinstance(value.get('devices'),dict), 'Invalid inventory')
    require(len(value['runtimes'])<=128 and len(value['devicetypes'])<=1024 and len(value['devices'])<=128,'Inventory bounds')
    runtimes=[r for r in value['runtimes'] if isinstance(r,dict) and r.get('identifier')=='com.apple.CoreSimulator.SimRuntime.iOS-27-0']
    types=[t for t in value['devicetypes'] if isinstance(t,dict) and t.get('name')=='iPad mini (A17 Pro)']
    require(len(runtimes)==1 and runtimes[0].get('isAvailable') is True and len(types)==1,'Exact Mini type/runtime required')
    device_type=types[0].get('identifier'); runtime=runtimes[0]['identifier']
    require(isinstance(device_type,str) and re.fullmatch(r'com\.apple\.CoreSimulator\.SimDeviceType\.[A-Za-z0-9-]{1,100}',device_type) and
            sum(isinstance(t,dict) and t.get('identifier')==device_type for t in value['devicetypes'])==1,'Ambiguous type identifier')
    rows=[]
    for devices in value['devices'].values():
        require(isinstance(devices,list) and len(devices)<=512,'Invalid device rows'); rows.extend(devices)
    require(len(rows)<=4096 and all(isinstance(d,dict) and valid_uuid(d.get('udid')) and
            isinstance(d.get('name'),str) for d in rows),'Invalid initial device identities')
    ids=[d['udid'] for d in rows]; require(len(set(ids))==len(ids),'Duplicate device UUID')
    return runtime,device_type,rows,hashlib.sha256(raw.encode()).hexdigest()


def configure(budget=None,executor=execute):
    budget=budget or Budget(); deadline=budget.enter('mini'); c=Controller(budget,'mini',deadline,executor)
    admit_full_ios_first_row(budget,deadline)
    runtime,device_type,rows,digest=inventory(c)
    name='QRCatcher Mini '+budget.identity['run_id']+'-'+budget.identity['run_attempt']
    require(not any(d['name']==name for d in rows),'Owned name already exists')
    code,raw=c.command(['xcrun','simctl','create',name,device_type,runtime],60)
    device=raw.strip(); require(code==0 and valid_uuid(device) and device not in [d['udid'] for d in rows], 'Invalid or pre-existing created UUID')
    if ios_first_profile():c.record['operations'][-1]['created_device']=device;budget.persist()
    code,raw=c.command(['xcrun','simctl','list','devices','available','-j'],30)
    require(code==0,'Created-device readback failed'); after=strict_json(raw)
    require(isinstance(after,dict) and isinstance(after.get('devices'),dict) and len(after['devices'])<=128,'Invalid readback')
    matches=[]
    for key,devices in after['devices'].items():
        require(isinstance(devices,list) and len(devices)<=512 and all(isinstance(d,dict) and
                valid_uuid(d.get('udid')) and isinstance(d.get('name'),str) for d in devices),'Invalid readback rows')
        matches.extend((key,d) for d in devices if d['udid']==device or d['name']==name)
    require(len(matches)==1,'Missing/ambiguous owned readback')
    key,row=matches[0]
    require(key==runtime and row.get('udid')==device and row.get('name')==name and
            row.get('deviceTypeIdentifier')==device_type and row.get('isAvailable') is True and
            row.get('state')=='Shutdown','Foreign or non-Shutdown owned device')
    receipt={**budget.identity,'device':device,'name':name,'runtime':runtime,'device_type':device_type,
             'initial_inventory_sha256':digest,'readback_sha256':hashlib.sha256(raw.encode()).hexdigest(),
             'initial_device_count':len(rows),'absent_from_initial_inventory':True,
             'row_started_monotonic':c.record['started'],'row_deadline_monotonic':deadline,
             'deployment_owner':'xcodebuild','pretest_boot_completion':'not_requested',
             'pretest_installed_bytes':'not_observed','state':'configured_shutdown_device_only'}
    write_json(budget.root/'build/ipad-mini-owned-device.json',receipt,limit=4096)
    c.record['status']='configuration_ready'; budget.persist()
    with open(os.environ['GITHUB_ENV'],'a') as f: f.write('MINI_SIMULATOR_ID='+device+'\n')
    print(json.dumps(receipt),flush=True); return receipt


def test_command(device,selectors,result):
    require(valid_uuid(device),'Invalid destination')
    return ['xcodebuild','test-without-building','-project',mini_project(),'-scheme','QRCatcher',
            '-configuration','Debug','-derivedDataPath','build/iOS','-destination','platform=iOS Simulator,id='+device,
            '-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-test-timeouts-enabled','YES',
            '-default-test-execution-time-allowance','180','-maximum-test-execution-time-allowance','240',
            'CODE_SIGNING_ALLOWED=NO',*selectors,'-resultBundlePath',result]


def result_summary_limit(result):
    # The observed first Mini reader needs a complete30s window. Only the exact
    # diagnostic route receives it; canonical and later summaries keep10s.
    if result=='MiniUIResults-layout.xcresult' and extended_mini_profile():
        return 30
    return 10


def qualify_result(controller,device,result,expected,exit_code):
    """A returned Xcode process is not proof that the requested cases executed."""
    code,raw=controller.command(['xcrun','xcresulttool','get','test-results','summary','--path',result],result_summary_limit(result))
    require(code==0,'Result summary unavailable'); value=strict_json(raw)
    require(isinstance(value,dict),'Invalid result summary')
    counts={key:value.get(key) for key in ['totalTestCount','passedTests','failedTests','skippedTests','expectedFailures']}
    require(all(type(v) is int and v>=0 for v in counts.values()) and
            counts['totalTestCount']==expected and counts['skippedTests']==0 and counts['expectedFailures']==0 and
            counts['passedTests']+counts['failedTests']==expected,'Missing, skipped or conflicting required cases')
    rows=value.get('devicesAndConfigurations')
    require(isinstance(rows,list) and len(rows)==1 and rows[0].get('device',{}).get('deviceId')==device,
            'Result belongs to another destination')
    require(value.get('runtimeWarnings')==[],'Runtime warnings retained; result cannot qualify')
    if exit_code==0:
        require(value.get('result')=='Passed' and counts['passedTests']==expected and counts['failedTests']==0 and
                value.get('testFailures')==[],'Command exit conflicts with complete successful cases')
    else:
        require(exit_code==65 and value.get('result')=='Failed' and counts['failedTests']>0 and
                isinstance(value.get('testFailures'),list) and bool(value['testFailures']),
                'Nonzero command is not a finalized observed test failure')
    controller.record.setdefault('results',{})[result]=counts
    controller.budget.persist()


_FIXTURE = None


@contextlib.contextmanager
def fixture_query(command):
    global _ACTIVE
    if _FIXTURE is None:
        yield; return
    c,device,index=_FIXTURE
    require(type(index[0]) is int and 0 <= index[0] < 2, 'Fixture query sequence exhausted')
    expected=['xcrun','simctl','get_app_container',device,'100mango.QRCatcher',('app','data')[index[0]]]
    require(index[0]<2 and command==expected,'Unexpected Mini fixture query')
    c.budget.next('mini',30,c.deadline); claim=Claim(c.budget,command,'mini-fixture'); claim.precheck=True; _ACTIVE=claim
    c.budget.persist(); c.budget.next('mini',30,c.deadline); started=c.budget.clock(); observed=False
    try:
        yield
        require(c.budget.clock()<started+30 and c.budget.clock()<c.deadline,'Late fixture query')
        claim.current(); observed=True; index[0]+=1
    except BaseException:
        mark_unconfirmed({'state':'mini_fixture_query_unresolved','exit':126,'cleanup_confirmed':False}); raise
    finally: claim.close(observed)


def row(args,budget=None,executor=execute,stager=None):
    global _ROW_LEASE
    budget=budget or Budget(); require(len(args)==3 and args[1:] == ['MiniUIResults.xcresult','QRCatcherPadUITests'],'Fixed full Mini row only')
    device=args[0]; require(valid_uuid(device) and os.environ.get('MINI_SIMULATOR_ID')==device,'Bound Mini destination required')
    receipt=strict_json(read_regular(budget.root/'build/ipad-mini-owned-device.json',4096))
    deadline=budget.enter('mini'); require(all(receipt.get(k)==v for k,v in budget.identity.items()) and
            receipt.get('device')==device and receipt.get('row_deadline_monotonic')==deadline and
            receipt.get('row_started_monotonic')==budget.state['phases']['mini']['started'] and
            receipt.get('state')=='configured_shutdown_device_only','Stale or reset Mini ownership')
    require(_ROW_LEASE is None,'Row lease already active')
    lease=Claim(budget,None,'full_row_dispatched_once',STOP); _ROW_LEASE=lease
    try: return row_body(device,budget,deadline,executor,stager)
    finally:
        lease.close(False); _ROW_LEASE=None


def row_body(device,budget,deadline,executor,stager):
    global _FIXTURE
    c=Controller(budget,'mini',deadline,executor); c.record['status']='row_running'
    setup={'device':device,'test_class':'QRCatcherPadUITests','layout_and_real_picker_cancel_exit':-1,
           'photo_seed_exit':-1,'real_photo_case_exit':-1,'real_files_case_exit':-1,
           'real_files_timeout_seconds':240,'photo_import_gate':'blocked_or_not_requested','seed_attempts':0,
           'timeout_does_not_prove_asset_absence':True,'independent_import_continuation':None,
           'row_started_monotonic':c.record['started'],'row_deadline_monotonic':deadline,
           'unexecuted':['layout','files','photos'],'full_job_accepted':False}
    def save():
        write_json(budget.root/'build/ios-platform-setup.json',setup,limit=4096); budget.persist()
    save()
    try:
        require(not any((budget.root/name).exists() or (budget.root/name).is_symlink() for name in
                        ['MiniUIResults-layout.xcresult','MiniUIResults-files.xcresult','MiniUIResults.xcresult']),
                'Stale result bundle cannot be reused')
        if ios_first_profile():
            from ipad_mini_state_handoff import ensure_owned_booted
            original_receipt=strict_json(read_regular(budget.root/'build/ipad-mini-owned-device.json',4096))
            ensure_owned_booted(c,device,original_receipt,'before_first_layout')
            from ipad_mini_state_handoff import qualified_first_bootstrap
            qualified_first_bootstrap(c,device,original_receipt)
            admit_full_ios_first_row(budget,deadline,'layout')
        code,_=c.command(test_command(device,LAYOUT,'MiniUIResults-layout.xcresult'),480,'MiniUIResults-layout.log')
        qualify_result(c,device,'MiniUIResults-layout.xcresult',2,code)
        setup['layout_and_real_picker_cancel_exit']=code; setup['unexecuted'].remove('layout'); save()
        if code:
            c.record['status']='completed_failed'; save(); return code
        if extended_mini_profile():
            from ipad_mini_state_handoff import ensure_owned_booted
            original_receipt=strict_json(read_regular(budget.root/'build/ipad-mini-owned-device.json',4096))
            ensure_owned_booted(c,device,original_receipt,'before_files_fixture')
        budget.next('mini',60,deadline); _FIXTURE=(c,device,[0])
        try:
            if stager: stager(device)
            else:
                previous=sys.argv; sys.argv=['scripts/stage_owned_import_fixture.py',device]
                try: runpy.run_path('scripts/stage_owned_import_fixture.py',run_name='__main__')
                finally: sys.argv=previous
            require(_FIXTURE[2][0]==2,'Both original fixture queries must complete')
        finally: _FIXTURE=None
        code,_=c.command(test_command(device,FILES,'MiniUIResults-files.xcresult'),240,'MiniUIResults-files.log')
        qualify_result(c,device,'MiniUIResults-files.xcresult',1,code)
        setup['real_files_case_exit']=code; setup['unexecuted'].remove('files'); save()
        file_exit=code
        # Timely complete failed cases remain red while independent Photos runs.
        if extended_mini_profile():
            ensure_owned_booted(c,device,original_receipt,'before_photos_seed')
        code,_=c.command(['xcrun','simctl','addmedia',device,'Tests/Fixtures/unicode.png'],210)
        setup['photo_seed_exit']=code; setup['seed_attempts']=1; setup['photo_import_gate']='ready' if code==0 else 'blocked_or_not_requested'; save()
        if code:
            c.record['status']='completed_failed'; save(); return code
        code,_=c.command(test_command(device,PHOTOS,'MiniUIResults.xcresult'),360,'MiniUIResults.log')
        qualify_result(c,device,'MiniUIResults.xcresult',1,code)
        setup['real_photo_case_exit']=code; setup['unexecuted'].remove('photos'); save()
        c.record['status']='completed' if file_exit==0 and code==0 else 'completed_failed'; save()
        return file_exit or code
    except BaseException as error:
        setup['stop_reason']=str(error)[:200]; c.record['status']='failed_or_unexecuted'; save(); raise


def host_execute(command,cap):
    """Owned host-only envelope; may retain evidence after device uncertainty."""
    require(command in host_commands().values(),'Not a fixed host-only command')
    require(_ACTIVE is not None,'Host envelope ownership required')
    _ACTIVE.current()  # Persistence/entry time cannot shorten a requested window.
    began=time.monotonic()
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    selector=selectors.DefaultSelector(); selector.register(process.stdout,selectors.EVENT_READ)
    raw=bytearray()
    try:
        while selector.get_map() or process.poll() is None:
            remaining=began+cap-time.monotonic(); require(remaining>0,'Host command timed out')
            for key,_ in selector.select(min(remaining,.1)):
                chunk=os.read(key.fileobj.fileno(),65536)
                if not chunk: selector.unregister(key.fileobj); continue
                raw.extend(chunk); require(len(raw)<=16*1024*1024,'Host output limit')
        return process.returncode,raw.decode(errors='replace')
    finally:
        clean=stop_group(process); selector.close(); process.stdout.close()
        if not clean:
            mark_unconfirmed({'state':'mini_host_cleanup_unconfirmed','exit':126,'cleanup_confirmed':False})
            raise ValueError('Host group cleanup unconfirmed')


def host_commands():
    embedding=([sys.executable,'scripts/ios_original_release_route.py','debug-package'] if ios_first_profile()
               else [sys.executable,'scripts/verify_embedded_watch.py','simulator'])
    return {'prepare':['bash','scripts/ipad_mini_prepare.sh'],
            'build':['xcodebuild','build-for-testing','-project',mini_project(),'-scheme','QRCatcher',
                     '-configuration','Debug','-derivedDataPath','build/iOS','-destination','generic/platform=iOS Simulator',
                     'ARCHS=arm64','CODE_SIGNING_ALLOWED=NO'],
            'embedding':embedding,
            'export':[sys.executable,'scripts/export_ios_platform_screenshots.py'],
            'validate':[sys.executable,'scripts/validate_evidence_budget.py','build/ios-platform-evidence',
                        '--scope','ipad_mini','--report','build/platform-evidence-budget.json'],
            'summary':[sys.executable,'scripts/ipad_mini_setup.py','summaries'],
            'final':['bash','scripts/ipad_mini_final.sh']}


def phase(name):
    global _ACTIVE
    budget=Budget(); deadline=budget.enter(name); operations=budget.state['phases'][name]['operations']
    caps={'prepare':95,'build':435,'embedding':20,'export':155,'validate':5,'summary':5,'final':5}
    if ios_first_profile(): caps['build']=135
    try:
        if name=='build':require(not (budget.root/'build/iOS').exists() and not (budget.root/'build/iOS').is_symlink(),
                                 'Fresh Mini build products required')
        for action in ([name,'embedding'] if name=='build' else [name]):
            budget.next(name,caps[action],deadline)
            command=host_commands()[action]
            event={'command':command,'cap':caps[action],'status':'pending'}; operations.append(event); budget.persist()
            budget.next(name,caps[action],deadline)
            require(_ACTIVE is None,'Concurrent host envelope')
            claim=Claim(budget,command,'host-'+name,'ipad-mini-host-inflight.json'); _ACTIVE=claim
            claim.dispatch_window=(caps[action],deadline); observed=False
            try:
                budget.persist(); budget.next(name,caps[action],deadline); began=budget.clock()
                code,output=host_execute(command,caps[action]); claim.dispatch_window=None; print(output,flush=True)
                require(budget.clock()<began+caps[action]+2 and budget.clock()<deadline,'Late host phase')
                observed=True
                event.update(status='completed',exit=code,cleanup_confirmed=True,elapsed=budget.clock()-began)
                if action=='build': (budget.root/'ios-test-build.log').write_text(output[-65536:])
                require(code==0,'Host prerequisite failed')
            except BaseException:
                if not observed:mark_unconfirmed({'state':'mini_host_command_unresolved','exit':126,'cleanup_confirmed':False})
                raise
            finally:claim.close(observed)
        if name=='export' and os.environ.get('GITHUB_REF')=='refs/heads/codex/mini-managed-full-row':
            from diagnostic_mini_managed_route import retain_prepared
            retain_prepared()  # Small sealed receipt inside the original export cap.
        budget.state['phases'][name]['status']='completed'; budget.persist()
    except BaseException:
        budget.state['phases'][name]['status']='failed_or_incomplete'; budget.persist(); raise


def summaries():
    budget=Budget(); value=strict_json(read_regular(budget.root/'build/ios-platform-evidence/manifest.json',512*1024))
    require(value.get('scope')=='ipad_mini' and value.get('commit')==budget.identity['source'] and
            str(value.get('run_id'))==budget.identity['run_id'],'Wrong summary source/run')
    for label,count in [('ipad-mini-layout',2),('ipad-mini-files',1),('ipad-mini',1)]:
        result=value.get('results',{}).get(label,{'not_produced':True})
        print(json.dumps({'label':label,'required_cases':count,'observed':result}),flush=True)


def action_gate(name):
    budget=Budget(); require(name in ('upload-enter','upload-exit'),'Unknown platform action gate')
    if name=='upload-enter':
        budget.enter('upload')
    else:
        item=budget.state['phases'].get('upload',{})
        require(item.get('status')=='pending' and budget.clock()<item['deadline'],'Upload action late/unobserved')
        item.update(status='platform_action_returned',owner='actions-runner',host_group_cleanup_claimed=False)
        budget.persist()


def main(args):
    if args==['source-identity']: context(); return 0
    if args==['configure']: configure(); return 0
    if args and args[0]=='row': return row(args[1:])
    if len(args)==2 and args[0]=='phase' and args[1] in ('prepare','build','export','validate','summary','final'):
        phase(args[1]); return 0
    if args==['summaries']: summaries(); return 0
    if len(args)==1 and args[0] in ('upload-enter','upload-exit'): action_gate(args[0]); return 0
    raise ValueError('Fixed canonical Mini operations only')


if __name__=='__main__':
    require(sys.modules.get('ipad_mini_setup') in (None,sys.modules[__name__]), 'Conflicting Mini controller module')
    sys.modules['ipad_mini_setup']=sys.modules[__name__]
    try: raise SystemExit(main(sys.argv[1:]))
    except Exception as error:
        print('IPAD_MINI_REFUSED '+type(error).__name__+': '+str(error),file=sys.stderr,flush=True)
        raise SystemExit(126 if blocked() else 2)
