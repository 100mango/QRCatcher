#!/usr/bin/env python3
"""Bounded synthetic phone/iPad evidence. Never uploads full xcresult archives."""
import hashlib,json,math,os,pathlib,re,struct,subprocess,sys,time
from export_settings_discovery import export_settings
export_started=time.monotonic()
def required_phone_result_endpoints(mode):
 if mode=='scrolled':return {'phone-largest-history-result-top','phone-largest-history-result-end'}
 if mode=='unscrolled':return {'phone-largest-history-result'}
 raise ValueError('Unknown app-owned result evidence mode')
def missing_phone_result_endpoints(requirements,screenshots,expected_results):
 missing=[];seen=set()
 for requirement in requirements:
  label=requirement['result_label']
  if label not in {'pro-max','SE3'} or label in seen:raise ValueError('Unknown or duplicate app-owned result evidence result')
  seen.add(label)
  required=required_phone_result_endpoints(requirement['mode'])
  retained={item.get('checkpoint') for item in screenshots if item.get('result_label')==label}
  absent=sorted(required-retained)
  if absent:missing.append({'result_label':label,'missing':absent})
 for label in sorted(set(expected_results)-seen):missing.append({'result_label':label,'missing':['app-owned result evidence mode and required pixels']})
 return missing
def missing_import_audit_pairs(requirements,screenshots,attachments,expected_results=()):
 missing=[];seen=set()
 allowed={'pro-max-imports','pro-max-files','SE3-imports','SE3-files'}
 for label in requirements:
  if label not in allowed or label in seen:raise ValueError('Unknown or duplicate phone audit-pair receipt')
  seen.add(label)
  before='image-import-real-files' if label.endswith('-files') else 'image-import-real-photos'
  required={before,'image-import-history-after-cancel','image-import-result-audit-tree','image-import-history-audit-tree','image-import-audit-pair-receipts'}
  retained={row['checkpoint'] for row in screenshots+attachments if row['result_label']==label}
  absent=sorted(required-retained)
  if absent:missing.append({'result_label':label,'missing':absent})
 for label in sorted(set(expected_results)-seen):missing.append({'result_label':label,'missing':['audit-pair requirement and paired evidence']})
 return missing

def validate_import_audit_pair_receipts(data):
 # Retain audit failures honestly. This validates evidence shape, never a pass.
 if len(data)>4096:raise ValueError('Audit-pair receipt exceeded 4KB')
 receipts=json.loads(data)
 if not isinstance(receipts,list) or len(receipts)!=2:raise ValueError('Missing distinct audit phases')
 required={'phase','callback_issues','registered_failure_delta','api_returned_success','error'}
 if any(not isinstance(row,dict) or set(row)!=required for row in receipts):raise ValueError('Unknown audit receipt fields')
 if [row['phase'] for row in receipts]!=['app-owned-result','same-history-after-cancel']:raise ValueError('Missing distinct audit phases')
 for row in receipts:
  if any(type(row[key]) is not int or row[key]<0 for key in ['callback_issues','registered_failure_delta']):raise ValueError('Invalid raw audit counts')
  if type(row['api_returned_success']) is not bool:raise ValueError('Missing audit API outcome')
  if not isinstance(row['error'],str):raise ValueError('Missing audit error text')
 return receipts

def validate_ipad_share_trace(data):
 if len(data)>4096:raise ValueError('iPad share trace exceeds4KiB')
 value=json.loads(data)
 order=['popover_count','popover_exists','activity_exists','caption_exists','caption_matches','copy_count','copy_exists','copy_enabled','copy_hittable']
 if not isinstance(value,dict) or type(value.get('version')) is not int or value.get('version')!=1 or value.get('timeout_seconds')!=10 or value.get('observations_qualify_pass') is not False or value.get('term_order')!=order or value.get('retained_attempt_limit')!=2:raise ValueError('Unknown iPad share diagnostic protocol')
 attempts=value.get('attempts');count=value.get('attempt_count')
 if not isinstance(attempts,list) or len(attempts)>2 or type(count) is not int or count<len(attempts):raise ValueError('Unbounded iPad share attempts')
 def finite(number):return type(number) in {int,float} and math.isfinite(number) and number>=0
 if value.get('waiter_result') is not None and (type(value['waiter_result']) is not int or value['waiter_result'] not in {1,2,3,4,5}):raise ValueError('Unknown native waiter result')
 if value.get('wait_elapsed') is not None and not finite(value['wait_elapsed']):raise ValueError('Invalid waiter duration')
 previous=0
 for attempt in attempts:
  index=attempt.get('index');terms=attempt.get('terms')
  if type(index) is not int or not previous<index<=count or not isinstance(terms,dict) or set(terms)!=set(order):raise ValueError('Invalid iPad share attempt identity')
  previous=index;stopped=False;all_true=True;completed_false=False;entered=None;last_finished=0
  for name in order:
   term=terms[name]
   if not isinstance(term,dict):raise ValueError('Invalid condition record')
   state=term.get('state')
   if state=='not_evaluated':
    if set(term)!={'state'}:raise ValueError('Unevaluated condition cannot claim a value')
    stopped=True;all_true=False;continue
   if stopped or state not in {'entered','completed'} or not finite(term.get('started')) or term['started']<last_finished:raise ValueError('Invalid short-circuit term order/timing')
   if state=='entered':
    if 'result' in term or 'finished' in term:raise ValueError('In-flight condition cannot claim completion')
    entered=name;stopped=True;all_true=False;continue
   result=term.get('result')
   if type(result) is not bool or not finite(term.get('finished')) or term['finished']<term['started']:raise ValueError('Missing actual condition result/timing')
   last_finished=term['finished']
   if name in {'popover_count','copy_count'}:
    actual=term.get('observed_count')
    if type(actual) is not int or actual<0 or result!=(actual==1):raise ValueError('Uniqueness result differs from observed count')
   if name=='caption_matches':
    size=term.get('caption_utf8_bytes')
    if size is not None and (type(size) is not int or size<0):raise ValueError('Invalid observed caption length')
   if not result:stopped=True;all_true=False;completed_false=True
  if attempt.get('active_term')!=entered:raise ValueError('Unknown active condition')
  returned=attempt.get('predicate_returned');ready=attempt.get('ready')
  if type(returned) is not bool or (returned and (type(ready) is not bool or ready!=all_true or (not ready and not completed_false) or entered is not None)) or (not returned and ready is not None):raise ValueError('Unobserved predicate cannot claim readiness')
 return value

def is_ipad_share_trace(entry):
 pattern=r'ipad-share-readiness-trace(?:_(?:0|[1-9][0-9]*)_[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\.json)?'
 return any(isinstance(value,str) and re.fullmatch(pattern,value) for value in entry.values())

def supplement_identity():
 if os.environ.get('GITHUB_REF')=='refs/heads/codex/ios-original-supplement' or os.environ.get('QRCATCHER_IOS_SUPPLEMENT_ONLY'):
  from ios_original_supplement_route import current_identity
  value=current_identity()
  if value.get('diagnostic_only') is not True or value.get('full_original_row_qualification') is not False or value.get('job')!='platform':raise ValueError('Exact supplemental platform identity required')
  root=pathlib.Path(os.environ.get('GITHUB_WORKSPACE',''))
  if not root.is_absolute() or root.resolve(strict=True)!=root or root!=pathlib.Path.cwd():raise ValueError('Canonical supplemental source checkout required')
  return value
 return None

def strict_record(raw):
 def pairs(rows):
  value={}
  for key,item in rows:
   if key in value:raise ValueError('Duplicate supplemental evidence field')
   value[key]=item
  return value
 value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite supplemental evidence')))
 if not isinstance(value,dict):raise ValueError('Supplemental evidence must be a JSON object')
 return value

def supplement_contract(scope,stem):
 # A fixed inventory of the selected invocations, not a new launcher.
 from ios_original_supplement_route import PROJECT,PHONE_CHECKS,FILES,PHONE_PHOTOS,PAD_PHOTOS,MINI_WARMUP
 device_key={'iphone_pro':'SIMULATOR_ID','iphone_se3':'COMPACT_SIMULATOR_ID','ipad_pro':'IPAD_SIMULATOR_ID','ipad_mini':'MINI_SIMULATOR_ID'}[scope]
 device=os.environ.get(device_key,'')
 import uuid
 if str(uuid.UUID(device)).upper()!=device:raise ValueError('Exact supplemental destination required')
 base={'iphone_pro':'PhoneUIResults','iphone_se3':'CompactPhoneUIResults','ipad_pro':'PadUIResults','ipad_mini':'MiniUIResults'}[scope]
 if scope=='ipad_mini':
  inventory={'MiniUIResults-warmup':(480,1,[MINI_WARMUP],30),'MiniUIResults':(360,1,[PAD_PHOTOS],10)}
 elif scope=='ipad_pro':
  inventory={base+'-layout':(480,2,None,30),base+'-files':(240,1,[FILES],10),base:(360,1,[PAD_PHOTOS],10)}
 else:
  inventory={base:(570,2,list(PHONE_CHECKS),30 if scope=='iphone_se3' else 10),base+'-files':(360 if scope=='iphone_pro' else 240,1,[FILES],10),base+'-imports':(360,1,[PHONE_PHOTOS],10)}
 result=stem+'.xcresult'
 if stem=='iOSUnitResults' and scope=='iphone_pro':
  return {'command':['xcodebuild','test-without-building','-project',PROJECT,'-scheme','QRCatcher','-configuration','Debug','-derivedDataPath','build/iOS','-destination','platform=iOS Simulator,id='+device,'-only-testing:QRCatcherTests','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','90','-maximum-test-execution-time-allowance','120','-resultBundlePath',result,'CODE_SIGNING_ALLOWED=NO'],'cap':855,'expected':30,'summary_cap':30,'device':device}
 if stem not in inventory:raise ValueError('Unselected supplemental result')
 cap,expected,selectors,summary_cap=inventory[stem]
 flags=['-only-testing:'+case for case in selectors] if selectors is not None else ['-only-testing:QRCatcherUITests/QRCatcherPadUITests','-skip-testing:'+PAD_PHOTOS]
 command=['xcodebuild','test-without-building','-project',PROJECT,'-scheme','QRCatcher','-configuration','Debug','-derivedDataPath','build/iOS','-destination','platform=iOS Simulator,id='+device,'-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','180','-maximum-test-execution-time-allowance','240','CODE_SIGNING_ALLOWED=NO',*flags,'-resultBundlePath',result]
 return {'command':command,'cap':cap,'expected':expected,'summary_cap':summary_cap,'device':device}

def classify_supplement_result(scope,stem,records,summary_raw):
 # Each receipt remains independently classified. Native Passed text alone
 # cannot convert an unknown/unclean invocation into accepted case evidence.
 result={'diagnostic_only':True,'full_original_row_qualification':False,'acceptance':False,'native_command':'missing','summary_command':'missing','native_summary':'missing'}
 try:contract=supplement_contract(scope,stem)
 except (ValueError,KeyError,TypeError) as error:
  result['reason']=str(error);return result
 def complete(operation,command,cap,exits):
  elapsed=operation.get('elapsed_seconds')
  return operation.get('command')==command and type(operation.get('timeout_seconds')) is int and operation['timeout_seconds']==cap and operation.get('state')=='completed' and type(operation.get('exit')) is int and operation['exit'] in exits and operation.get('cleanup_confirmed') is True and type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<=elapsed<cap+2 and type(operation.get('output_bytes')) is int and operation['output_bytes']>=0
 native=records.get(stem+'-command.json');reader=records.get(stem+'-summary-command.json');value=records.get(stem+'-summary.json')
 if native is not None:result['native_command']='completed' if complete(native,contract['command'],contract['cap'],(0,65)) else 'unqualified'
 summary_command=['xcrun','xcresulttool','get','test-results','summary','--path',stem+'.xcresult']
 if reader is not None:result['summary_command']='completed' if complete(reader,summary_command,contract['summary_cap'],(0,)) and summary_raw is not None and reader['output_bytes']==len(summary_raw) else 'unqualified'
 if value is None:return result
 result['native_summary']='retained_unqualified'
 counts={key:value.get(key) for key in ('totalTestCount','passedTests','failedTests','skippedTests','expectedFailures')};rows=value.get('devicesAndConfigurations');expected=contract['expected']
 valid=all(type(v) is int and v>=0 for v in counts.values()) and counts['totalTestCount']==expected and counts['skippedTests']==0 and counts['expectedFailures']==0 and counts['passedTests']+counts['failedTests']==expected and isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict) and isinstance(rows[0].get('device'),dict) and rows[0]['device'].get('deviceId')==contract['device'] and value.get('runtimeWarnings')==[]
 if not valid or result['native_command']!='completed' or result['summary_command']!='completed':return result
 passed=native['exit']==0 and value.get('result')=='Passed' and counts['passedTests']==expected and counts['failedTests']==0 and value.get('testFailures')==[]
 failed=native['exit']==65 and value.get('result')=='Failed' and counts['failedTests']>0 and isinstance(value.get('testFailures'),list) and bool(value['testFailures'])
 if not (passed or failed):return result
 result.update(acceptance=True,native_summary='finalized_selected_cases',native_outcome='Passed' if passed else 'Failed',counts=counts)
 return result

def supplement_export_blocked(identity):
 from owned_process_barrier import blocked,KEY,barrier_path
 if not blocked():return False
 if identity['scope']!='ipad_mini' or os.environ.get(KEY)=='true':return True
 # The healthy Mini host exporter has its own existing lease and the durable
 # completed-row marker. Validate that one envelope; never clear either lease
 # or permit export through a pending device command or uncertainty marker.
 try:
  from ipad_mini_setup import Budget,read_regular,signature
  barrier=barrier_path()
  if barrier is None or barrier.exists() or barrier.is_symlink():return True
  if any(pathlib.Path('build',name).exists() or pathlib.Path('build',name).is_symlink() for name in ('ipad-mini-inflight.json','fixture-query-inflight.json','settings-discovery-inflight.json','vision-command-inflight.json')):return True
  budget=Budget();budget.current()
  row_path=pathlib.Path('build/ipad-mini-row-dispatched.json');host_path=pathlib.Path('build/ipad-mini-host-inflight.json')
  ledger_raw=read_regular(budget.path,budget.ledger_limit);lease_raw=read_regular(row_path,4096);host_raw=read_regular(host_path,4096)
  if strict_record(ledger_raw)!=budget.state:return True
  lease=strict_record(lease_raw);host=strict_record(host_raw)
  proofs=[(budget.path,ledger_raw,budget.ledger_limit),(row_path,lease_raw,4096),(host_path,host_raw,4096)]
  identities=[signature(path.stat()) for path,raw,cap in proofs]
  command=[__import__('sys').executable,'scripts/export_ios_platform_screenshots.py']
  if set(lease)!=set(budget.identity)|{'phase','owner_pid','command'} or any(lease.get(key)!=value for key,value in budget.identity.items()) or lease.get('phase')!='full_row_dispatched_once' or type(lease.get('owner_pid')) is not int or lease['owner_pid']<=0 or lease.get('command') is not None:return True
  if host!={**budget.identity,'phase':'host-export','owner_pid':os.getppid(),'command':command}:return True
  row=budget.state['phases'].get('mini',{});export=budget.state['phases'].get('export',{})
  if row.get('status') not in ('completed','completed_failed') or export.get('status')!='pending' or budget.clock()>=export['deadline']:return True
  operations=export.get('operations')
  if not isinstance(operations,list) or not operations or operations[-1]!={'command':command,'cap':155,'status':'pending'}:return True
  for index,(path,raw,cap) in enumerate(proofs):
   if read_regular(path,cap)!=raw or signature(path.stat())!=identities[index]:return True
  budget.current()
  return False
 except (OSError,ValueError,KeyError,TypeError):return True

# These two fixed phone phases must survive a later independent Photos fence.
# The same exporter runs once per closed phase, inside the original UI clock.
def closed_phone_stems(identity):
 if os.environ.get('PHONE_COMPLETION_ONLY')!='true':return ()
 base={'iphone_pro':'PhoneUIResults','iphone_se3':'CompactPhoneUIResults'}.get(identity['scope'])
 if base is None:raise ValueError('Closed phase retention requires the selected phone route')
 return (base,base+'-files')

def closed_phone_binding(identity,stem):
 from ipad_mini_setup import read_regular
 from ios_original_release_route import RECEIPT,INITIAL_HASH_KEY
 if stem not in closed_phone_stems(identity):raise ValueError('Unselected closed phone phase')
 step_raw=read_regular(pathlib.Path('build/ios-platform-step.json'),16*1024);step=strict_record(step_raw)
 expected=supplement_contract(identity['scope'],stem)
 if set(step)!={'identity','device','owner_pid','step_started_monotonic'} or step['identity']!=identity or step['device']!=expected['device'] or type(step['owner_pid']) is not int or step['owner_pid']<=0:raise ValueError('Foreign original phone step owner')
 started=step['step_started_monotonic']
 if type(started) not in (int,float) or not math.isfinite(started) or not 0<started<=time.monotonic():raise ValueError('Invalid original phone step clock')
 source_raw=read_regular(RECEIPT,4096);prepared=strict_record(source_raw)
 if hashlib.sha256(source_raw).hexdigest()!=os.environ.get(INITIAL_HASH_KEY) or set(prepared)!=set(identity)|{'tested_tree','source_readback_phase'} or any(prepared[key]!=value for key,value in identity.items()) or re.fullmatch('[0-9a-f]{40}',prepared['tested_tree']) is None or prepared['source_readback_phase']!='bounded initial original iOS HEAD/tree/diff/status':raise ValueError('Foreign prepared source/run/attempt/profile receipt')
 raw={name:read_regular(pathlib.Path('build')/(stem+name),cap) for name,cap in (('-command.json',16384),('-summary-command.json',16384),('-summary.json',65536))}
 records={stem+name:strict_record(data) for name,data in raw.items()}
 if not classify_supplement_result(identity['scope'],stem,records,raw['-summary.json'])['acceptance']:raise ValueError('Closed phone phase has no timely clean selected result')
 bundle=pathlib.Path(stem+'.xcresult')
 if bundle.is_symlink() or bundle.resolve(strict=True)!=pathlib.Path.cwd()/bundle:raise ValueError('Redirected closed result bundle')
 info=read_regular(bundle/'Info.plist',65536)
 return {'identity':identity,'stem':stem,'device':expected['device'],'step':step,
  'step_sha256':hashlib.sha256(step_raw).hexdigest(),'source_receipt_sha256':hashlib.sha256(source_raw).hexdigest(),
  'tested_tree':prepared['tested_tree'],'result_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in raw.items()},
  'result_info_sha256':hashlib.sha256(info).hexdigest()}

def closed_phone_deadline(binding,full=False):
 from ios_original_supplement_route import SUMMARY_PHASE_SECONDS,SUMMARY_POST_RETURN_SECONDS,SUMMARY_CLEANUP_SECONDS
 deadline=binding['step']['step_started_monotonic']+SUMMARY_PHASE_SECONDS[binding['identity']['scope']]
 required=(155+SUMMARY_POST_RETURN_SECONDS if full else 0)+SUMMARY_CLEANUP_SECONDS
 if time.monotonic()+required>deadline:raise ValueError('Full closed-phase export and cleanup reserve unavailable inside original native phase')
 return deadline

def retain_closed_phone_phase(identity,stem,raw_start):
 from atomic_json import write_json
 from ipad_mini_setup import read_regular
 from watch_process import execute
 binding=closed_phone_binding(identity,stem)
 if float(raw_start)!=binding['step']['step_started_monotonic'] or os.getppid()!=binding['step']['owner_pid'] or supplement_export_blocked(identity):raise ValueError('Closed phase exporter owner/clock/fence mismatch')
 closed_phone_deadline(binding,full=True)
 folder=pathlib.Path('build/ios-platform-closed-phase')/stem
 folder.parent.mkdir(exist_ok=True)
 if folder.parent.is_symlink() or folder.parent.resolve(strict=True)!=pathlib.Path.cwd()/folder.parent or folder.exists() or folder.is_symlink():raise ValueError('Closed phone phase cannot retry or reuse stale evidence')
 if any(path.name not in closed_phone_stems(identity) for path in folder.parent.iterdir()):raise ValueError('Unknown closed phone phase cache')
 folder.mkdir()
 command=[sys.executable,'scripts/export_ios_platform_screenshots.py','--export-closed-phone-phase',stem,raw_start]
 pending={'binding':binding,'owner_pid':os.getpid(),'command':command}
 write_json(folder/'pending.json',pending,limit=16*1024)
 closed_phone_deadline(binding,full=True)
 began=time.monotonic()
 code,raw,operation=execute(command,155,output_limit=512*1024,tail_limit=64*1024,echo=False)
 finished=time.monotonic()
 (folder/'export.log').write_text(raw)
 write_json(folder/'export-command.json',operation,limit=16*1024)
 elapsed=operation.get('elapsed_seconds')
 if code!=0 or operation.get('command')!=command or type(operation.get('timeout_seconds')) is not int or operation['timeout_seconds']!=155 or operation.get('state')!='completed' or type(operation.get('exit')) is not int or operation['exit']!=0 or operation.get('cleanup_confirmed') is not True or type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0<=elapsed<157 or supplement_export_blocked(identity):raise ValueError('Closed phase export is late, incomplete or unclean')
 closed_phone_deadline(binding)
 if closed_phone_binding(identity,stem)!=binding or strict_record(read_regular(folder/'pending.json',16384))!=pending:raise ValueError('Closed phone phase binding changed during export')
 evidence=folder/'evidence'
 inventory={path.name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for path in evidence.iterdir() for data in [read_regular(path,800*1024)]}
 write_json(folder/'receipt.json',{'binding':binding,'owner_pid':pending['owner_pid'],'command':command,'operation':operation,'export_started_monotonic':began,'export_finished_monotonic':finished,'files':inventory},limit=32*1024)
 print('IOS_SUPPLEMENT_CLOSED_PHASE_RETAINED '+stem,flush=True)

def verified_closed_phone_phase(identity,stem):
 from ipad_mini_setup import read_regular
 binding=closed_phone_binding(identity,stem);folder=pathlib.Path('build/ios-platform-closed-phase')/stem
 receipt_raw=read_regular(folder/'receipt.json',32*1024);receipt=strict_record(receipt_raw);pending=strict_record(read_regular(folder/'pending.json',16*1024))
 command=[sys.executable,'scripts/export_ios_platform_screenshots.py','--export-closed-phone-phase',stem,str(binding['step']['step_started_monotonic'])]
 if set(receipt)!={'binding','owner_pid','command','operation','export_started_monotonic','export_finished_monotonic','files'} or receipt['binding']!=binding or type(receipt['owner_pid']) is not int or receipt['owner_pid']<=0 or receipt['command']!=command or pending!={'binding':binding,'owner_pid':receipt['owner_pid'],'command':command}:raise ValueError('Foreign or stale closed-phase receipt')
 operation=receipt['operation'];elapsed=operation.get('elapsed_seconds')
 if strict_record(read_regular(folder/'export-command.json',16384))!=operation or operation.get('command')!=command or type(operation.get('timeout_seconds')) is not int or operation['timeout_seconds']!=155 or operation.get('state')!='completed' or type(operation.get('exit')) is not int or operation['exit']!=0 or operation.get('cleanup_confirmed') is not True or type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0<=elapsed<157:raise ValueError('Unqualified closed-phase exporter receipt')
 from ios_original_supplement_route import SUMMARY_PHASE_SECONDS
 began=receipt['export_started_monotonic'];finished=receipt['export_finished_monotonic'];started=binding['step']['step_started_monotonic'];deadline=started+SUMMARY_PHASE_SECONDS[identity['scope']]
 if any(type(value) not in (int,float) or not math.isfinite(value) for value in (began,finished)) or not started<=began<=finished<=time.monotonic() or began+177>deadline or finished+20>deadline or finished-began>=157:raise ValueError('Closed-phase cache exceeded its original native clock')
 if set(path.name for path in folder.iterdir())!={'pending.json','export.log','export-command.json','receipt.json','evidence'}:raise ValueError('Unknown closed-phase cache entry')
 files=receipt['files'];evidence=folder/'evidence'
 if not isinstance(files,dict) or not 1<=len(files)<=128 or set(files)!={path.name for path in evidence.iterdir()}:raise ValueError('Missing or extra closed-phase cache files')
 data={}
 for name,record in files.items():
  if not isinstance(name,str) or pathlib.Path(name).name!=name or not isinstance(record,dict) or set(record)!={'bytes','sha256'} or type(record['bytes']) is not int or not 0<record['bytes']<=800*1024:raise ValueError('Invalid fixed cache file')
  raw=read_regular(evidence/name,800*1024)
  if name.endswith('.jpg') and not raw.startswith(b'\xff\xd8'):raise ValueError('Invalid cached selected JPEG')
  if len(raw)!=record['bytes'] or hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('Closed-phase cache bytes changed')
  data[name]=raw
 manifest=strict_record(data['manifest.json'])
 if manifest.get('scope')!=identity['scope'] or manifest.get('commit')!=identity['source_sha'] or manifest.get('tree')!=binding['tested_tree'] or manifest.get('run_id')!=identity['run_id'] or manifest.get('closed_phone_phase_binding')!=binding or manifest.get('closed_phone_phase_owner_pid')!=receipt['owner_pid'] or manifest.get('evidence_complete') is not True:raise ValueError('Incomplete or foreign closed-phase manifest')
 return manifest,data,receipt_raw

def reuse_closed_phone_phase(identity,stem,label,summary,out,limit):
 manifest,data,receipt_data=verified_closed_phone_phase(identity,stem)
 receipt_name=stem+'-closed-phase-export.json'
 for key in ('screenshots','import_audit_attachments'):
  rows=manifest[key]
  if not isinstance(rows,list):raise ValueError('Invalid retained closed-phase attachment list')
  for item in rows:
   if not isinstance(item,dict) or item.get('result_label')!=label or item.get('name') not in data or item.get('bytes')!=len(data[item['name']]) or item.get('sha256')!=hashlib.sha256(data[item['name']]).hexdigest():raise ValueError('Foreign retained closed-phase attachment')
 for item in manifest['import_audit_attachments']:
  raw=data[item['name']]
  if len(raw)>64*1024:raise ValueError('Cached audit attachment exceeded original allocation')
  if item['checkpoint']=='image-import-audit-pair-required' and raw.decode().strip()!='phone-result-history':raise ValueError('Invalid cached audit-pair requirement')
  if item['checkpoint']=='image-import-audit-pair-receipts':validate_import_audit_pair_receipts(raw)
 if missing_import_audit_pairs(manifest['import_audit_pair_requirements'],manifest['screenshots'],manifest['import_audit_attachments'],[label] if label.endswith('-files') else []):raise ValueError('Missing cached Files paired evidence')
 if manifest['import_audit_pair_requirements'] not in ([],[label]) or manifest['phone_result_evidence_requirements']!=[] or manifest['missing_import_audit_pairs'] or manifest['omitted']:raise ValueError('Incomplete retained closed-phase requirements')
 names=[row['name'] for key in ('screenshots','import_audit_attachments') for row in manifest[key]]
 if len(names)!=len(set(names)) or len(summary['screenshots'])+len(manifest['screenshots'])>28:raise ValueError('Duplicate or excessive retained closed-phase attachments')
 names.append(receipt_name);data[receipt_name]=receipt_data
 if sum(path.stat().st_size for path in out.iterdir())+sum(len(data[name]) for name in names)>limit-512*1024 or len(list(out.iterdir()))+len(names)>126:raise ValueError('Retained closed-phase evidence exceeds original scope allocation')
 for name in names:
  target=out/name
  if target.exists() or target.is_symlink():raise ValueError('Duplicate retained closed-phase output')
 for name in names:(out/name).write_bytes(data[name])
 for key in ('screenshots','import_audit_attachments','import_audit_pair_requirements'):summary[key].extend(manifest[key])

def retain_supplement_records(identity,out,limit,closed_stem=None):
 from ipad_mini_setup import read_regular
 scope=identity['scope']
 stems={'iphone_pro':('iOSUnitResults','PhoneUIResults','PhoneUIResults-files','PhoneUIResults-imports'),'iphone_se3':('CompactPhoneUIResults','CompactPhoneUIResults-files','CompactPhoneUIResults-imports'),'ipad_pro':('PadUIResults-layout','PadUIResults-files','PadUIResults'),'ipad_mini':('MiniUIResults-warmup','MiniUIResults')}[scope]
 if closed_stem is not None:
  if closed_stem not in closed_phone_stems(identity):raise ValueError('Unselected closed retention result')
  stems=(closed_stem,)
 report={'diagnostic_only':True,'full_original_row_qualification':False,'historical_component_reference':identity['historical_component_reference'],'runtime_precise_safari_url':'UNKNOWN','files':[],'missing':[],'invalid':[],'results':{},'owned_process_uncertainty_observed':False}
 records={};raw_summaries={}
 def retain(path,cap,tail=None):
  if not path.exists() and not path.is_symlink():report['missing'].append(str(path));return
  try:
   data=read_regular(path,cap)
   value=strict_record(data) if path.suffix=='.json' else None
   name=path.name;target=out/name
   if target.exists() or target.is_symlink():raise ValueError('Duplicate fixed supplemental output record')
   retained=data[-tail:] if tail else data
   if tail and scope in ('iphone_pro','iphone_se3') and os.environ.get('PHONE_COMPLETION_ONLY')=='true':
    # Keep fixed native diagnostic lines when a long failure hierarchy pushes
    # them outside the original tail. They never qualify a pass.
    base={'iphone_pro':'PhoneUIResults','iphone_se3':'CompactPhoneUIResults'}[scope]
    markers=(b'PRIVACY_SYSTEM_OPEN_BASELINE:',b'PRIVACY_SYSTEM_OPEN_RECEIPT:') if path.name==base+'.log' else (b'PHOTO_IMPORT_WAIT_V1',b'PHOTO_IMPORT_WAIT_RETURN_V1',b'PHOTO_IMPORT_OBSERVATION_V1:',b'PHOTO_IMPORT_OBSERVATION_READ_V1') if path.name==base+'-imports.log' else ()
    marker_lines=[]
    for marker in markers:
     matches=[line for line in data.splitlines() if marker in line]
     maximum=2 if marker==b'PHOTO_IMPORT_OBSERVATION_V1:' else 1
     if len(matches)>maximum or any(len(line)>2048 for line in matches):raise ValueError('Duplicate or oversized fixed native diagnostic log marker')
     marker_lines.extend(line+b'\n' for line in matches)
    if marker_lines and len(data)>tail:
     body=data[-(tail-sum(map(len,marker_lines))):]
     prefix=b''.join(line for line in marker_lines if line.rstrip(b'\n') not in body.splitlines())
     retained=prefix+body
   used=sum(p.stat().st_size for p in out.iterdir())
   if used+len(retained)>limit-512*1024 or len(list(out.iterdir()))>=126:raise ValueError('Supplemental metadata exceeds its unchanged evidence allocation')
   target.write_bytes(retained)
   report['files'].append({'name':name,'bytes':len(retained),'source_bytes':len(data),'truncated':len(retained)!=len(data),'sha256':hashlib.sha256(retained).hexdigest()})
   if value is not None:records[name]=value
   if name.endswith('-summary.json'):raw_summaries[name]=data
  except (OSError,ValueError,UnicodeError) as error:report['invalid'].append({'path':str(path),'reason':str(error)[:240]})
 for stem in stems:
  for suffix,cap in [('-command.json',16*1024),('-summary-command.json',16*1024),('-summary.json',64*1024)]:retain(pathlib.Path('build')/(stem+suffix),cap)
  log='ios-unit.log' if stem=='iOSUnitResults' else stem+'.log'
  retain(pathlib.Path(log),17*1024*1024,64*1024)
  if scope=='ipad_mini':retain(pathlib.Path(stem+'-summary.log'),17*1024*1024,64*1024)
 seed_stem={'iphone_pro':'PhoneUIResults-seed','iphone_se3':'CompactPhoneUIResults-seed','ipad_pro':'PadUIResults-seed','ipad_mini':'MiniUIResults-seed'}[scope]
 if closed_stem is None:
  retain(pathlib.Path('build')/(seed_stem+'-command.json'),16*1024)
  retain(pathlib.Path(seed_stem+'.log'),17*1024*1024,64*1024)
 seed=records.get(seed_stem+'-command.json')
 seed_accepted=False
 if seed is not None:
  try:
   device=supplement_contract(scope,stems[-1])['device'];elapsed=seed.get('elapsed_seconds')
   seed_accepted=seed.get('command')==['xcrun','simctl','addmedia',device,'Tests/Fixtures/unicode.png'] and type(seed.get('timeout_seconds')) is int and seed['timeout_seconds']==210 and seed.get('state')=='completed' and type(seed.get('exit')) is int and seed['exit']==0 and seed.get('cleanup_confirmed') is True and type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<=elapsed<212 and type(seed.get('output_bytes')) is int and seed['output_bytes']>=0
  except (ValueError,KeyError,TypeError):pass
 report['photos_seed']={'receipt_retained':seed is not None,'acceptance':seed_accepted,'state':seed.get('state') if seed else None,'exit':seed.get('exit') if seed else None,'cleanup_confirmed':seed.get('cleanup_confirmed') is True if seed else False,'observations_qualify_pass':False}
 for stem in stems:
  value=classify_supplement_result(scope,stem,records,raw_summaries.get(stem+'-summary.json'))
  if closed_stem is None and stem==stems[-1] and value['acceptance'] and not seed_accepted:value.update(acceptance=False,native_summary='retained_unqualified',reason='Required exact Photos seed receipt did not qualify')
  report['results'][stem]=value
 report['owned_process_uncertainty_observed']=supplement_export_blocked(identity)
 return report,records

def attachment_bytes(path,folder,cap,selected):
 if not selected:return path.resolve().read_bytes()
 from ipad_mini_setup import read_regular
 if path.resolve(strict=True)!=path.absolute() or not path.resolve(strict=True).is_relative_to(folder.resolve(strict=True)):raise ValueError('Redirected supplemental attachment')
 return read_regular(path,cap)

def attachment_command(command,identity,**options):
 if identity and supplement_export_blocked(identity):raise ValueError('Supplemental attachment command blocked by owned uncertainty')
 return subprocess.run(command,**options)

closed_phase_mode=None;closed_stem=None;closed_binding=None
if len(sys.argv)>1 and sys.argv[1] in ('--retain-closed-phone-phase','--export-closed-phone-phase'):
 if len(sys.argv)!=4:raise ValueError('Exact fixed closed-phase exporter arguments required')
 closed_phase_mode,closed_stem,closed_start=sys.argv[1:]

scope=os.environ['EVIDENCE_SCOPE']
limit=json.loads(pathlib.Path('scripts/evidence-allocation.json').read_text())['scope_limits_bytes'][scope]
selected_identity=supplement_identity()
if closed_phase_mode:
 if selected_identity is None:raise ValueError('Closed phone phase requires exact selected identity')
 if closed_phase_mode=='--retain-closed-phone-phase':
  retain_closed_phone_phase(selected_identity,closed_stem,closed_start);raise SystemExit(0)
 from ipad_mini_setup import read_regular
 closed_binding=closed_phone_binding(selected_identity,closed_stem)
 pending=strict_record(read_regular(pathlib.Path('build/ios-platform-closed-phase')/closed_stem/'pending.json',16384))
 expected_command=[sys.executable,'scripts/export_ios_platform_screenshots.py','--export-closed-phone-phase',closed_stem,closed_start]
 if pending!={'binding':closed_binding,'owner_pid':os.getppid(),'command':expected_command} or float(closed_start)!=closed_binding['step']['step_started_monotonic'] or supplement_export_blocked(selected_identity):raise ValueError('Closed phase child owner/clock/fence mismatch')
 closed_phone_deadline(closed_binding)
out=pathlib.Path('build/ios-platform-closed-phase')/closed_stem/'evidence' if closed_phase_mode else pathlib.Path('build/ios-platform-evidence')
out.mkdir(parents=True,exist_ok=True)
if closed_phase_mode:
 for earlier in out.parent.parent.glob('*/evidence/*'):
  if earlier.parent!=out:limit-=len(read_regular(earlier,800*1024))

if selected_identity and (out.is_symlink() or out.resolve()!=pathlib.Path.cwd()/out or any(out.iterdir())):raise ValueError('Fresh canonical supplemental evidence folder required')
prepared=None
if os.environ.get('GITHUB_REF') in {'refs/heads/codex/ios-original-release','refs/heads/codex/ios-original-supplement'}:
 from ios_original_release_route import current_identity,retain_prepared
 current_identity()
 report=pathlib.Path('build/ios-first-debug-package.json')
 if report.exists() or report.is_symlink():
  from ios_import_continuation import read_regular
  (out/report.name).write_bytes(read_regular(report,64*1024))
 if closed_phase_mode:
  from ios_original_release_route import RECEIPT
  prepared=strict_record(read_regular(RECEIPT,4096));(out/RECEIPT.name).write_bytes(read_regular(RECEIPT,4096))
 else:prepared=retain_prepared()
summary={'scope':scope,'scope_limit_bytes':limit,'commit':selected_identity['source_sha'] if selected_identity else subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'tree':prepared['tested_tree'] if selected_identity else subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),'run_id':os.environ.get('GITHUB_RUN_ID'),'screenshots':[],'omitted':[],'results':{},'phone_result_evidence_requirements':[],'import_audit_pair_requirements':[],'import_audit_attachments':[],'ipad_share_traces':[]}
if scope=='ipad_mini':
 from ipad_mini_setup import job_ledger_limit
 for name,cap in [('ipad-mini-job-state.json',job_ledger_limit()),('ipad-mini-owned-device.json',4096),('ipad-mini-inflight.json',4096),('ipad-mini-host-inflight.json',4096),('ipad-mini-row-dispatched.json',4096)]:
  path=pathlib.Path('build')/name
  if path.exists() or path.is_symlink():
   from ipad_mini_setup import read_regular
   data=read_regular(path,cap);(out/name).write_bytes(data)
barrier=pathlib.Path('build/owned-process-cleanup.json')
if barrier.exists() or (selected_identity and barrier.is_symlink()):
 if selected_identity:
  from ipad_mini_setup import read_regular
  data=read_regular(barrier,2048);strict_record(data)
 else:
  assert not barrier.is_symlink() and barrier.stat().st_size<=2048
  data=barrier.read_bytes()
 (out/barrier.name).write_bytes(data)
pending_fixture=pathlib.Path('build/fixture-query-inflight.json')
if pending_fixture.exists() or pending_fixture.is_symlink():
 if pending_fixture.is_symlink() or not pending_fixture.is_file() or pending_fixture.stat().st_size>2048:raise ValueError('Invalid pending fixture-query evidence')
 (out/pending_fixture.name).write_bytes(pending_fixture.read_bytes())
fixture=pathlib.Path('build/import-fixture/fixture.json')
if fixture.is_file() or (selected_identity and fixture.is_symlink()):
 if selected_identity:
  from ipad_mini_setup import read_regular
  data=read_regular(fixture,4096);strict_record(data)
 else:data=fixture.read_bytes();assert len(data)<4096
 (out/'owned-import-fixture.json').write_bytes(data)
setup=pathlib.Path('build/ios-platform-setup.json')
if setup.exists() or (selected_identity and setup.is_symlink()):
 if selected_identity:
  from ipad_mini_setup import read_regular
  data=read_regular(setup,16384);strict_record(data)
 else:data=setup.read_bytes();assert len(data)<16384
 (out/setup.name).write_bytes(data)
selected_records={}
if selected_identity:
 selected_report,selected_records=retain_supplement_records(selected_identity,out,limit,closed_stem)
 summary.update(diagnostic_only=True,full_original_row_qualification=False,release_qualification=False,selected_evidence=selected_report,evidence_complete=False)
 summary['not_selected']=[{'checkpoint':'phone-largest-history-result','state':'not_selected'},{'checkpoint':'phone-largest-history-result-top','state':'not_selected'},{'checkpoint':'phone-largest-history-result-end','state':'not_selected'}] if scope.startswith('iphone_') else []
 if scope=='ipad_mini':summary['not_selected']=[{'result_label':'ipad-mini-layout','state':'not_selected'},{'result_label':'ipad-mini-files','state':'not_selected'}]
 # Metadata survives a later attachment/semantic export failure. All selected
 # raw summaries were read once, before any optional image can use the budget.
 (out/'manifest.json').write_text(json.dumps(summary,indent=2)+'\n')
else:
 for path in pathlib.Path('build/vision-runtime').glob('*'):
  if path.is_file() and path.suffix in {'.json','.jpg','.log','.png'}:
   data=path.read_bytes();assert len(data)<=800*1024;(out/('vision-'+path.name)).write_bytes(data)
 for path in pathlib.Path('build/watch-runtime').glob('*'):
  if path.is_file():
   data=path.read_bytes();assert len(data)<=512*1024;(out/('watch-'+path.name)).write_bytes(data)
 for path in pathlib.Path('build/native-release-evidence').glob('*.json'):
  data=path.read_bytes();assert len(data)<64*1024;(out/path.name).write_bytes(data)
# Source icon previews accompany, but do not replace, compiled-bundle checks.
for label,relative in [('watch','QRCatcherWatch/Assets.xcassets/AppIcon.appiconset/Icon-1024.png'),('vision','QRCatcherVision/Assets.xcassets/AppIcon.solidimagestack/Back.solidimagestacklayer/Content.imageset/Icon.png'),('tv','QRCatcherTV/Assets.xcassets/AppIcon.brandassets/Small.imagestack/Back.imagestacklayer/Content.imageset/Icon-2x.png')]:
 path=pathlib.Path(relative)
 if path.is_file() and scope=={'watch':'watchos','vision':'visionos','tv':'tvos'}[label]:
  data=path.read_bytes();assert len(data)<=800*1024;(out/(label+'-retained-icon-source.png')).write_bytes(data)
for name in ['release-watch.log','release-tv.log','release-vision.log','watch-test-build.log','watch-unit.log','watch-ui.log','tv-test-build.log','tv-test.log','tv-authorized-test.log','tv-revoked-test.log','vision-test-build.log','vision-test.log','vision-ui-test.log','ios-test-build.log','ios-unit.log','PhoneUIResults.log','CompactPhoneUIResults.log','PadUIResults.log','MiniUIResults.log','PadUIResults-layout.log','MiniUIResults-layout.log','PhoneUIResults-imports.log','CompactPhoneUIResults-imports.log','PhoneUIResults-files.log','CompactPhoneUIResults-files.log','PadUIResults-files.log','MiniUIResults-files.log']:
 if selected_identity:
  if name=='ios-test-build.log':
   path=pathlib.Path(name)
   if path.exists() or path.is_symlink():
    from ipad_mini_setup import read_regular
    (out/name).write_bytes(read_regular(path,17*1024*1024)[-64*1024:])
  continue
 path=pathlib.Path(name)
 if path.is_file():(out/name).write_bytes(path.read_bytes()[-64*1024:])
names=('privacy-browser-manual-review','image-import-history-after-cancel','phone-largest-history-result-top','phone-largest-history-result-end','phone-largest-history-result','watch-trait-initial-payload-top','watch-trait-initial-payload-bottom','watch-trait-reopened-payload-top','watch-trait-reopened-payload-bottom','image-import-files-decoded','image-import-photos-decoded','image-import-real-photos','image-import-real-files','image-import-failure','tv-history-after-removal','tv-history-focused-record','tv-history-focused-delete','tv-history-list','tv-offline-policy','tv-chinese-result','watch-recovered-journal','watch-saved-preview','phone-failure','tv-revoked-photos','watch-empty','watch-offline-policy','watch-fixture-offline-result','watch-system-picker-unavailable','watch-reopened-qr','watch-failure','tv-real-photo-result','tv-verified-photos-output','tv-reopened-history','tv-failure','vision-imported-qr','vision-reopened-history','vision-failure','synthetic-scan-result','synthetic-history','privacy-open-diagnostic','privacy-return-diagnostic','ipad-anchored-share','ipad-split-portrait','ipad-large-text','ipad-imported-photo','ipad-failure','view-layout-320x568-largest-text','view-layout-568x320-largest-text')
def records(value):
 if isinstance(value,dict):
  if 'exportedFileName' in value:yield value
  for child in value.values():yield from records(child)
 elif isinstance(value,list):
  for child in value:yield from records(child)
for result,label in [('WatchUnitResults.xcresult','watch-unit'),('WatchUIResults.xcresult','watch-ui'),('WatchLargestUIResults.xcresult','watch-largest'),('WatchTraitStressUIResults.xcresult','watch-trait-stress'),('TVTestResults.xcresult','apple-tv'),('TVAuthorizedUIResults.xcresult','apple-tv-pregranted'),('TVRevokedUIResults.xcresult','apple-tv-revoked'),('TVLargestUIResults.xcresult','apple-tv-largest'),('TVTraitStressUIResults.xcresult','apple-tv-trait-stress'),('VisionTestResults.xcresult','vision-pro-unit'),('VisionUIResults.xcresult','vision-pro-ui'),('VisionPhotosUIResults.xcresult','vision-photos-ui'),('VisionFilesUIResults.xcresult','vision-files-ui'),('VisionChineseUIResults.xcresult','vision-chinese-ui'),('VisionLargestUIResults.xcresult','vision-largest'),('iOSUnitResults.xcresult','view-layout-host'),('PhoneUIResults.xcresult','pro-max'),('CompactPhoneUIResults.xcresult','SE3'),('PhoneUIResults-imports.xcresult','pro-max-imports'),('CompactPhoneUIResults-imports.xcresult','SE3-imports'),('PhoneUIResults-files.xcresult','pro-max-files'),('CompactPhoneUIResults-files.xcresult','SE3-files'),('PadUIResults-files.xcresult','ipad-pro-13-files'),('MiniUIResults-files.xcresult','ipad-mini-files'),('PadUIResults-layout.xcresult','ipad-pro-13-layout'),('MiniUIResults-layout.xcresult','ipad-mini-layout'),('MiniUIResults-warmup.xcresult','ipad-mini-warmup'),('PadUIResults.xcresult','ipad-pro-13'),('MiniUIResults.xcresult','ipad-mini')]:
 if label=='ipad-mini-warmup' and not selected_identity:continue
 if selected_identity:
  stem=result.removesuffix('.xcresult')
  if closed_stem and stem!=closed_stem:continue
  classification=summary['selected_evidence']['results'].get(stem)
  if classification is None:
   summary['results'][label]={'not_produced':True,'not_selected':True};continue
  retained=selected_records.get(stem+'-summary.json')
  summary['results'][label]=dict(retained) if retained is not None else {'summary_unavailable':True,'not_produced':not pathlib.Path(result,'Info.plist').is_file()}
  summary['results'][label]['selected_case_acceptance']=classification['acceptance']
  summary['results'][label]['full_original_row_qualification']=False
  if not closed_phase_mode and stem in closed_phone_stems(selected_identity):
   try:
    reuse_closed_phone_phase(selected_identity,stem,label,summary,out,limit)
    classification['attachments']='retained_closed_phase_before_later_uncertainty'
   except (OSError,ValueError,KeyError,TypeError) as error:
    classification['attachments']='missing_closed_phase_evidence_UNKNOWN'
    summary['selected_evidence']['missing'].append({'closed_phase':stem,'reason':str(error)[:240]})
   continue
  export_blocked=supplement_export_blocked(selected_identity)
  if export_blocked or not classification['acceptance'] or not pathlib.Path(result,'Info.plist').is_file():
   classification['attachments']='not_exported_owned_uncertainty' if export_blocked else 'not_exported_unqualified_or_missing_result'
   continue
  try:
   from ipad_mini_setup import read_regular
   bundle=pathlib.Path(result)
   if bundle.is_symlink() or bundle.resolve(strict=True)!=pathlib.Path.cwd()/bundle:raise ValueError('Redirected supplemental result bundle')
   read_regular(bundle/'Info.plist',64*1024)
  except (OSError,ValueError) as error:
   classification['attachments']='not_exported_invalid_result'
   summary['selected_evidence']['invalid'].append({'path':result,'reason':str(error)[:240]});continue
 if not pathlib.Path(result,'Info.plist').is_file():
  summary['results'][label]={'not_produced':True};continue
 if not selected_identity:
  report=subprocess.run(['xcrun','xcresulttool','get','test-results','summary','--path',result],capture_output=True,text=True)
  summary['results'][label]=json.loads(report.stdout) if report.returncode==0 else {'summary_error':report.stderr}
 folder=pathlib.Path('build/ios-platform-attachments')/label;folder.mkdir(parents=True,exist_ok=True)
 if selected_identity and (folder.is_symlink() or folder.resolve()!=pathlib.Path.cwd()/folder or any(folder.iterdir())):raise ValueError('Fresh canonical supplemental attachment folder required')
 attachment_command(['xcrun','xcresulttool','export','attachments','--path',result,'--output-path',str(folder)],selected_identity,check=True)
 if selected_identity:
  from ipad_mini_setup import read_regular,strict_json
  entries=list(records(strict_json(read_regular(folder/'manifest.json',128*1024))))
  if len(entries)>128:raise ValueError('Supplemental attachment inventory exceeded its bound')
 else:entries=records(json.loads((folder/'manifest.json').read_text()))
 for entry in entries:
  text=' '.join(v for v in entry.values() if isinstance(v,str));name=next((n for n in names if n in text),None)
  if is_ipad_share_trace(entry):
   allowed={'ipad_pro':{'ipad-pro-13-layout','ipad-pro-13'},'ipad_mini':{'ipad-mini-layout','ipad-mini'}}
   if label not in allowed.get(scope,set()) or summary['ipad_share_traces']:raise ValueError('Wrong or duplicate iPad share diagnostic result')
   raw=folder/entry['exportedFileName'];path=raw.resolve()
   if path!=raw.absolute() or not path.is_relative_to(folder.resolve()) or not path.is_file() or path.stat().st_nlink!=1 or path.stat().st_size>4096:raise ValueError('Invalid iPad share diagnostic file')
   with path.open('rb') as stream:data=stream.read(4097)
   trace=validate_ipad_share_trace(data)
   filename=label+'-share-readiness-trace.json';(out/filename).write_bytes(data)
   summary['ipad_share_traces'].append({'result_label':label,'name':filename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'observations_qualify_pass':False})
   continue
  audit_name=next((value for value in ['image-import-audit-pair-required','image-import-result-audit-tree','image-import-history-audit-tree','image-import-audit-pair-receipts'] if value in text),None)
  if audit_name:
   path=(folder/entry['exportedFileName']).resolve()
   if not path.is_relative_to(folder.resolve()):raise ValueError('Audit-pair attachment escaped its result directory')
   data=attachment_bytes(folder/entry['exportedFileName'],folder,64*1024,selected_identity)
   if len(data)>64*1024:raise ValueError('Audit-pair text exceeded its bounded allocation')
   if audit_name=='image-import-audit-pair-required':
    if data.decode('utf-8').strip()!='phone-result-history':raise ValueError('Unknown import audit-pair requirement')
    summary['import_audit_pair_requirements'].append(label)
   elif audit_name=='image-import-audit-pair-receipts':
    validate_import_audit_pair_receipts(data)
   filename=label+'-'+audit_name+'.txt';(out/filename).write_bytes(data)
   summary['import_audit_attachments'].append({'result_label':label,'checkpoint':audit_name,'name':filename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
   continue
  if 'phone-largest-result-hierarchy' in text:
   path=(folder/entry['exportedFileName']).resolve();assert path.is_relative_to(folder.resolve())
   data=attachment_bytes(folder/entry['exportedFileName'],folder,64*1024,selected_identity);assert len(data)<=64*1024
   (out/(label+'-app-owned-result-hierarchy.txt')).write_bytes(data);continue
  if 'phone-largest-result-evidence-requirement' in text:
   path=(folder/entry['exportedFileName']).resolve();assert path.is_relative_to(folder.resolve())
   data=attachment_bytes(folder/entry['exportedFileName'],folder,32,selected_identity);assert len(data)<=32
   mode=data.decode('utf-8').strip();required_phone_result_endpoints(mode)
   summary['phone_result_evidence_requirements'].append({'result_label':label,'mode':mode})
   (out/(label+'-app-owned-result-evidence-mode.txt')).write_bytes(data);continue
  if not name or 'accessibility' in text:continue
  # Keep the complete largest-size case result, with representative actual
  # result/focus/Chinese pixels inside the unchanged TV evidence allocation.
  if label in {'apple-tv-largest','apple-tv-trait-stress'} and name not in ['tv-chinese-result','tv-history-focused-delete','tv-real-photo-result','tv-failure']:continue
  path=(folder/entry['exportedFileName']).resolve();assert path.is_relative_to(folder.resolve())
  data=attachment_bytes(folder/entry['exportedFileName'],folder,16*1024*1024,selected_identity)
  source_bytes=len(data)
  native_manual_browser_jpeg=name=='privacy-browser-manual-review'
  if native_manual_browser_jpeg:
   expected_label={'iphone_pro':'pro-max','iphone_se3':'SE3'}.get(scope)
   if label!=expected_label or not data.startswith(b'\xff\xd8') or not 0<len(data)<=500*1024:raise ValueError('Invalid fixed native browser review image')
  native_watch_png=label.startswith('watch-') and data.startswith(b'\x89PNG')
  native_dimensions=None
  if native_watch_png:
   assert len(data)>24 and data[12:16]==b'IHDR'
   native_dimensions=list(struct.unpack('>II',data[16:24]));assert all(0<v<=1024 for v in native_dimensions)
  if data.startswith(b'\x89PNG') and not native_watch_png:
   converted=path.with_suffix('.bounded.jpg')
   attachment_command(['sips','-s','format','jpeg','-s','formatOptions','55','-Z','1440',str(path),'--out',str(converted)],selected_identity,check=True,capture_output=True,**({'timeout':30} if selected_identity else {}))
   data=attachment_bytes(converted,folder,800*1024,selected_identity)
  elif label.startswith('apple-tv') and data.startswith(b'\xff\xd8'):
   # Preserve the whole actual TV frame, but bound its long edge so the enlarged
   # focus/localization/policy set fits this platform's fixed artifact allocation.
   converted=path.with_suffix('.bounded.jpg')
   attachment_command(['sips','-s','format','jpeg','-s','formatOptions','50','-Z','1920',str(path),'--out',str(converted)],selected_identity,check=True,capture_output=True,timeout=30)
   data=attachment_bytes(converted,folder,800*1024,selected_identity)
  elif not label.startswith('watch-') and data.startswith(b'\xff\xd8') and not native_manual_browser_jpeg:
   # Full phone/iPad frames retain both real import routes within the unchanged
   # per-row allocation; Watch endpoint pixels above remain byte-for-byte native.
   converted=path.with_suffix('.bounded.jpg')
   attachment_command(['sips','-s','format','jpeg','-s','formatOptions','55','-Z','1440',str(path),'--out',str(converted)],selected_identity,check=True,capture_output=True,timeout=30)
   data=attachment_bytes(converted,folder,800*1024,selected_identity)
  if selected_identity and (not data.startswith(b'\xff\xd8') or len(data)>800*1024):raise ValueError('Invalid or oversized supplemental screenshot')
  assert (native_watch_png or data.startswith(b'\xff\xd8')) and len(data)<=800*1024,'Invalid or oversized synthetic screenshot'
  suffix='png' if native_watch_png else 'jpg'
  filename=f'{label}-{name}-{len(summary["screenshots"])+1}.{suffix}'
  # Endpoint rows omit duplicate icon/Release evidence and have a smaller,
  # explicitly bounded summary; all rows still undergo strict pre-upload checks.
  reserve=128*1024 if scope.startswith('watchos_') else 512*1024
  used=sum(p.stat().st_size for p in out.iterdir())
  if used+len(data)>limit-reserve or len(summary['screenshots'])>=28:
   summary['omitted'].append({'name':filename,'reason':'bounded evidence cap'});print('OMITTED_AT_CAP',filename,flush=True);continue
  (out/filename).write_bytes(data)
  item={'name':filename,'result_label':label,'checkpoint':name,'bytes':len(data),'source_attachment_bytes':source_bytes,'sha256':hashlib.sha256(data).hexdigest()}
  if native_dimensions:item.update(native_pixel_dimensions=native_dimensions,source_bytes_preserved=True)
  if native_manual_browser_jpeg:item.update(source_bytes_preserved=True,manual_review_required=True,automatic_page_qualification=False,runtime_precise_url='UNKNOWN')
  summary['screenshots'].append(item);print(json.dumps(item),flush=True)
expected_phone_result_results=[] if selected_identity else [label for label in ['pro-max','SE3'] if not summary['results'].get(label,{'not_produced':True}).get('not_produced')]
summary['missing_phone_result_endpoints']=missing_phone_result_endpoints(summary['phone_result_evidence_requirements'],summary['screenshots'],expected_phone_result_results)
expected_import_pairs=[label for label in ['pro-max-imports','pro-max-files','SE3-imports','SE3-files'] if not summary['results'].get(label,{'not_produced':True}).get('not_produced')]
summary['missing_import_audit_pairs']=missing_import_audit_pairs(summary['import_audit_pair_requirements'],summary['screenshots'],summary['import_audit_attachments'],expected_import_pairs)
if selected_identity:
 summary['evidence_complete']=not (summary['selected_evidence']['missing'] or summary['selected_evidence']['invalid'] or summary['selected_evidence']['owned_process_uncertainty_observed'] or summary['omitted'] or summary['missing_phone_result_endpoints'] or summary['missing_import_audit_pairs']) and all(item['acceptance'] for item in summary['selected_evidence']['results'].values())
ordinary_summary_bytes=len((json.dumps(summary,indent=2)+'\n').encode())
ordinary_used=sum(p.stat().st_size for p in out.iterdir())
if closed_phase_mode:
 closed_phone_deadline(closed_binding)
 summary.update(closed_phone_phase_binding=closed_binding,closed_phone_phase_owner_pid=os.getppid())
else:summary['settings_discovery']=export_settings(scope,out,limit-ordinary_used-ordinary_summary_bytes-8192,export_started)
encoded=json.dumps(summary,indent=2)+'\n'
assert len(encoded.encode())<=(128*1024 if scope.startswith('watchos_') else 512*1024)
(out/'manifest.json').write_text(encoded)
size=sum(p.stat().st_size for p in out.iterdir())
if closed_phase_mode and (size>limit or len(encoded.encode())>512*1024):raise ValueError('Closed-phase evidence exceeded unchanged allocation')
mac=sum(p.stat().st_size for p in pathlib.Path('build/mac-evidence').glob('*') if p.is_file())
print(json.dumps({'ios_evidence_bytes':size,'mac_evidence_bytes':mac,'combined_bytes':size+mac}),flush=True)
assert size<=limit and size+mac<=20_000_000
if summary['omitted']:raise SystemExit('Required named screenshots exceeded the cap; review omitted entries instead of claiming complete visual evidence')

if summary['missing_phone_result_endpoints']:raise SystemExit('App-owned result endpoint evidence incomplete: '+json.dumps(summary['missing_phone_result_endpoints']))

if summary['missing_import_audit_pairs']:raise SystemExit('Native import audit-pair evidence incomplete: '+json.dumps(summary['missing_import_audit_pairs']))

if selected_identity and summary['selected_evidence']['invalid']:raise SystemExit('Invalid fixed supplemental evidence retained only as an explicit incomplete diagnostic')
