#!/usr/bin/env python3
"""Bounded synthetic phone/iPad evidence. Never uploads full xcresult archives."""
import hashlib,json,math,os,pathlib,re,struct,subprocess,time
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

scope=os.environ['EVIDENCE_SCOPE']
limit=json.loads(pathlib.Path('scripts/evidence-allocation.json').read_text())['scope_limits_bytes'][scope]
out=pathlib.Path('build/ios-platform-evidence');out.mkdir(parents=True,exist_ok=True)
summary={'scope':scope,'scope_limit_bytes':limit,'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),'run_id':os.environ.get('GITHUB_RUN_ID'),'screenshots':[],'omitted':[],'results':{},'phone_result_evidence_requirements':[],'import_audit_pair_requirements':[],'import_audit_attachments':[],'ipad_share_traces':[]}
if scope=='ipad_mini':
 from ipad_mini_setup import job_ledger_limit
 for name,cap in [('ipad-mini-job-state.json',job_ledger_limit()),('ipad-mini-owned-device.json',4096),('ipad-mini-inflight.json',4096),('ipad-mini-host-inflight.json',4096),('ipad-mini-row-dispatched.json',4096)]:
  path=pathlib.Path('build')/name
  if path.exists() or path.is_symlink():
   from ipad_mini_setup import read_regular
   data=read_regular(path,cap);(out/name).write_bytes(data)
barrier=pathlib.Path('build/owned-process-cleanup.json')
if barrier.exists():
 assert not barrier.is_symlink() and barrier.stat().st_size<=2048
 (out/barrier.name).write_bytes(barrier.read_bytes())
pending_fixture=pathlib.Path('build/fixture-query-inflight.json')
if pending_fixture.exists() or pending_fixture.is_symlink():
 if pending_fixture.is_symlink() or not pending_fixture.is_file() or pending_fixture.stat().st_size>2048:raise ValueError('Invalid pending fixture-query evidence')
 (out/pending_fixture.name).write_bytes(pending_fixture.read_bytes())
fixture=pathlib.Path('build/import-fixture/fixture.json')
if fixture.is_file():
 data=fixture.read_bytes();assert len(data)<4096;(out/'owned-import-fixture.json').write_bytes(data)
setup=pathlib.Path('build/ios-platform-setup.json')
if setup.exists():
 data=setup.read_bytes();assert len(data)<16384;(out/setup.name).write_bytes(data)
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
 path=pathlib.Path(name)
 if path.is_file():(out/name).write_bytes(path.read_bytes()[-64*1024:])
names=('image-import-history-after-cancel','phone-largest-history-result-top','phone-largest-history-result-end','phone-largest-history-result','watch-trait-initial-payload-top','watch-trait-initial-payload-bottom','watch-trait-reopened-payload-top','watch-trait-reopened-payload-bottom','image-import-files-decoded','image-import-photos-decoded','image-import-real-photos','image-import-real-files','image-import-failure','tv-history-after-removal','tv-history-focused-record','tv-history-focused-delete','tv-history-list','tv-offline-policy','tv-chinese-result','watch-recovered-journal','watch-saved-preview','phone-failure','tv-revoked-photos','watch-empty','watch-offline-policy','watch-fixture-offline-result','watch-system-picker-unavailable','watch-reopened-qr','watch-failure','tv-real-photo-result','tv-verified-photos-output','tv-reopened-history','tv-failure','vision-imported-qr','vision-reopened-history','vision-failure','synthetic-scan-result','synthetic-history','privacy-open-diagnostic','privacy-return-diagnostic','ipad-anchored-share','ipad-split-portrait','ipad-large-text','ipad-imported-photo','ipad-failure','view-layout-320x568-largest-text','view-layout-568x320-largest-text')
def records(value):
 if isinstance(value,dict):
  if 'exportedFileName' in value:yield value
  for child in value.values():yield from records(child)
 elif isinstance(value,list):
  for child in value:yield from records(child)
for result,label in [('WatchUnitResults.xcresult','watch-unit'),('WatchUIResults.xcresult','watch-ui'),('WatchLargestUIResults.xcresult','watch-largest'),('WatchTraitStressUIResults.xcresult','watch-trait-stress'),('TVTestResults.xcresult','apple-tv'),('TVAuthorizedUIResults.xcresult','apple-tv-pregranted'),('TVRevokedUIResults.xcresult','apple-tv-revoked'),('TVLargestUIResults.xcresult','apple-tv-largest'),('TVTraitStressUIResults.xcresult','apple-tv-trait-stress'),('VisionTestResults.xcresult','vision-pro-unit'),('VisionUIResults.xcresult','vision-pro-ui'),('VisionPhotosUIResults.xcresult','vision-photos-ui'),('VisionFilesUIResults.xcresult','vision-files-ui'),('VisionChineseUIResults.xcresult','vision-chinese-ui'),('VisionLargestUIResults.xcresult','vision-largest'),('iOSUnitResults.xcresult','view-layout-host'),('PhoneUIResults.xcresult','pro-max'),('CompactPhoneUIResults.xcresult','SE3'),('PhoneUIResults-imports.xcresult','pro-max-imports'),('CompactPhoneUIResults-imports.xcresult','SE3-imports'),('PhoneUIResults-files.xcresult','pro-max-files'),('CompactPhoneUIResults-files.xcresult','SE3-files'),('PadUIResults-files.xcresult','ipad-pro-13-files'),('MiniUIResults-files.xcresult','ipad-mini-files'),('PadUIResults-layout.xcresult','ipad-pro-13-layout'),('MiniUIResults-layout.xcresult','ipad-mini-layout'),('PadUIResults.xcresult','ipad-pro-13'),('MiniUIResults.xcresult','ipad-mini')]:
 if not pathlib.Path(result,'Info.plist').is_file():
  summary['results'][label]={'not_produced':True};continue
 report=subprocess.run(['xcrun','xcresulttool','get','test-results','summary','--path',result],capture_output=True,text=True)
 summary['results'][label]=json.loads(report.stdout) if report.returncode==0 else {'summary_error':report.stderr}
 folder=pathlib.Path('build/ios-platform-attachments')/label;folder.mkdir(parents=True,exist_ok=True)
 subprocess.run(['xcrun','xcresulttool','export','attachments','--path',result,'--output-path',str(folder)],check=True)
 for entry in records(json.loads((folder/'manifest.json').read_text())):
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
   data=path.read_bytes()
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
   data=path.read_bytes();assert len(data)<=64*1024
   (out/(label+'-app-owned-result-hierarchy.txt')).write_bytes(data);continue
  if 'phone-largest-result-evidence-requirement' in text:
   path=(folder/entry['exportedFileName']).resolve();assert path.is_relative_to(folder.resolve())
   data=path.read_bytes();assert len(data)<=32
   mode=data.decode('utf-8').strip();required_phone_result_endpoints(mode)
   summary['phone_result_evidence_requirements'].append({'result_label':label,'mode':mode})
   (out/(label+'-app-owned-result-evidence-mode.txt')).write_bytes(data);continue
  if not name or 'accessibility' in text:continue
  # Keep the complete largest-size case result, with representative actual
  # result/focus/Chinese pixels inside the unchanged TV evidence allocation.
  if label in {'apple-tv-largest','apple-tv-trait-stress'} and name not in ['tv-chinese-result','tv-history-focused-delete','tv-real-photo-result','tv-failure']:continue
  path=(folder/entry['exportedFileName']).resolve();assert path.is_relative_to(folder.resolve())
  data=path.read_bytes()
  source_bytes=len(data)
  native_watch_png=label.startswith('watch-') and data.startswith(b'\x89PNG')
  native_dimensions=None
  if native_watch_png:
   assert len(data)>24 and data[12:16]==b'IHDR'
   native_dimensions=list(struct.unpack('>II',data[16:24]));assert all(0<v<=1024 for v in native_dimensions)
  if data.startswith(b'\x89PNG') and not native_watch_png:
   converted=path.with_suffix('.bounded.jpg')
   subprocess.run(['sips','-s','format','jpeg','-s','formatOptions','55','-Z','1440',str(path),'--out',str(converted)],check=True,capture_output=True)
   data=converted.read_bytes()
  elif label.startswith('apple-tv') and data.startswith(b'\xff\xd8'):
   # Preserve the whole actual TV frame, but bound its long edge so the enlarged
   # focus/localization/policy set fits this platform's fixed artifact allocation.
   converted=path.with_suffix('.bounded.jpg')
   subprocess.run(['sips','-s','format','jpeg','-s','formatOptions','50','-Z','1920',str(path),'--out',str(converted)],check=True,capture_output=True,timeout=30)
   data=converted.read_bytes()
  elif not label.startswith('watch-') and data.startswith(b'\xff\xd8'):
   # Full phone/iPad frames retain both real import routes within the unchanged
   # per-row allocation; Watch endpoint pixels above remain byte-for-byte native.
   converted=path.with_suffix('.bounded.jpg')
   subprocess.run(['sips','-s','format','jpeg','-s','formatOptions','55','-Z','1440',str(path),'--out',str(converted)],check=True,capture_output=True,timeout=30)
   data=converted.read_bytes()
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
  summary['screenshots'].append(item);print(json.dumps(item),flush=True)
expected_phone_result_results=[label for label in ['pro-max','SE3'] if not summary['results'].get(label,{'not_produced':True}).get('not_produced')]
summary['missing_phone_result_endpoints']=missing_phone_result_endpoints(summary['phone_result_evidence_requirements'],summary['screenshots'],expected_phone_result_results)
expected_import_pairs=[label for label in ['pro-max-imports','pro-max-files','SE3-imports','SE3-files'] if not summary['results'].get(label,{'not_produced':True}).get('not_produced')]
summary['missing_import_audit_pairs']=missing_import_audit_pairs(summary['import_audit_pair_requirements'],summary['screenshots'],summary['import_audit_attachments'],expected_import_pairs)
ordinary_summary_bytes=len((json.dumps(summary,indent=2)+'\n').encode())
ordinary_used=sum(p.stat().st_size for p in out.iterdir())
summary['settings_discovery']=export_settings(scope,out,limit-ordinary_used-ordinary_summary_bytes-8192,export_started)
encoded=json.dumps(summary,indent=2)+'\n'
assert len(encoded.encode())<=(128*1024 if scope.startswith('watchos_') else 512*1024)
(out/'manifest.json').write_text(encoded)
size=sum(p.stat().st_size for p in out.iterdir())
mac=sum(p.stat().st_size for p in pathlib.Path('build/mac-evidence').glob('*') if p.is_file())
print(json.dumps({'ios_evidence_bytes':size,'mac_evidence_bytes':mac,'combined_bytes':size+mac}),flush=True)
assert size<=limit and size+mac<=20_000_000
if summary['omitted']:raise SystemExit('Required named screenshots exceeded the cap; review omitted entries instead of claiming complete visual evidence')

if summary['missing_phone_result_endpoints']:raise SystemExit('App-owned result endpoint evidence incomplete: '+json.dumps(summary['missing_phone_result_endpoints']))

if summary['missing_import_audit_pairs']:raise SystemExit('Native import audit-pair evidence incomplete: '+json.dumps(summary['missing_import_audit_pairs']))
