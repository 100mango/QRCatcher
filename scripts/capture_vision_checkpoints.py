#!/usr/bin/env python3
"""Capture actual simulator pixels while XCTest holds a UUID request/ack checkpoint.
Only the exact built runner's own temporary files are read/written, via public
simctl get_app_container; no accessibility/TCC/database mutation is involved.
"""
import hashlib,json,os,plistlib,re,subprocess,sys,time,uuid
from pathlib import Path
from atomic_json import write_json
from owned_process_barrier import blocked
from vision_runner_binding import RunnerBinding, exact_uuid
from vision_case_contract import select_case
from vision_failure_diagnostic import FailureDiagnostic
udid,log,scope=sys.argv[1:];log=Path(log);out=Path('build/vision-runtime');out.mkdir(parents=True,exist_ok=True)
case=select_case(scope)
runner=Path('build/VisionTests/Build/Products/Debug-xrsimulator/QRCatcherVisionUITests-Runner.app/Info.plist')
runner_id=plistlib.loads(runner.read_bytes())['CFBundleIdentifier']
binding=RunnerBinding(udid,runner_id,os.environ['GITHUB_SHA'],case)
failure=FailureDiagnostic(binding,out)
names=set(case.frames)|{'vision-failure'}
seen=set();report=[];bindings=[];deadline=time.monotonic()+1650
while time.monotonic()<deadline:
 if blocked():raise SystemExit('Owned command cleanup is unresolved; no further simulator capture command')
 text=log.read_text(errors='replace') if log.exists() else ''
 for event,request_id in re.findall(r'QRCATCHER_VISION_(RUNNER_READY|CAPTURE_REQUEST):([A-F0-9-]{36})',text):
  if (event,request_id) in seen:continue
  if len(seen)>=64:raise SystemExit('Bounded Vision capture event limit exceeded')
  exact_uuid(request_id)
  seen.add((event,request_id))
  if event=='RUNNER_READY':
   try:
    if bindings:
     binding.bound=None
     raise ValueError('A second runner lease is forbidden for the sole selected case')
    row=binding.prime(request_id)
   except Exception as error:row={**binding.case_identity,'lease':request_id,'success':False,'error':str(error)[:1600]}
   bindings.append(row);write_json(out/'runner-bindings.json',bindings);print('VISION_RUNNER_BINDING '+json.dumps(row),flush=True)
   continue
  row={**binding.case_identity,'id':request_id,'source':'public simctl screenshot at held XCTest checkpoint','success':False};ack=None;raw=None;staged=None
  try:
   descriptor,ack=binding.request(request_id,names);name=descriptor['name']
   row.update(lease=descriptor['lease'],source_commit=descriptor['source_commit'],device=descriptor['device'],runner=descriptor['runner'],pid=descriptor['pid'])
   if name=='vision-failure':
    diagnostic=failure.capture('native failure teardown request')
    row.update(checkpoint=name,diagnostic_only=True,diagnostic_report='host-failure-capture.json')
    row['error']='Original XCTest failure retained; failure pixels cannot qualify a success checkpoint'
    # The finally block sends only success=false to release failure teardown.
    # No success screenshot, audit, export receipt or required frame is replaced.
    continue
   if name in ['vision-exported-qr','vision-exported-history']:
    test_store=exact_uuid(descriptor['test_store'])
    kind='png' if name=='vision-exported-qr' else 'json'
    receipt_bytes,saved_bytes=binding.export_bytes(test_store,kind)
    receipt=json.loads(receipt_bytes)
    if not isinstance(receipt,dict) or receipt.get('test_store')!=test_store or receipt.get('type')!=kind:
     raise ValueError('Export receipt identity/type mismatch')
    if type(receipt.get('bytes')) is not int or len(saved_bytes)!=receipt['bytes'] or hashlib.sha256(saved_bytes).hexdigest()!=receipt.get('sha256'):
     raise ValueError('Export receipt byte/hash mismatch')
    if len(saved_bytes)>=128*1024:raise ValueError('Synthetic output evidence exceeded its separate cap')
    if kind=='png':
     # Verify the exact bytes obtained through no-follow file descriptors, never
     # reopen a potentially replaced path in the simulator container.
     staged=out/(request_id+'.export.png')
     with staged.open('xb') as stream:stream.write(saved_bytes)
     if blocked():raise RuntimeError('Owned cleanup barrier forbids export verification command')
     subprocess.run(['xcrun','swift','scripts/verify_vision_export_pixels.swift',str(staged)],check=True,timeout=30)
    else:
     history=json.loads(saved_bytes)
     if not isinstance(history,dict) or history.get('format')!='QRCatcher.history' or type(history.get('version')) is not int or history['version']!=1:
      raise ValueError('Export history format/version mismatch')
     records=history.get('records')
     if not isinstance(records,list) or len(records)!=1 or not isinstance(records[0],dict) or records[0].get('payload')!='QRCatcher 你好 🌈 123':
      raise ValueError('Export history payload mismatch')
    (out/('actual-export.'+kind)).write_bytes(saved_bytes)
    row['actual_export_readback']=receipt
   row['checkpoint']=name;raw=out/(request_id+'.raw.png');jpeg=out/(name+'.jpg')
   # A separate largest-system-size case repeats existing named checkpoints;
   # retain both proven states instead of overwriting earlier pixels/hashes.
   index=2
   while jpeg.exists():jpeg=out/(name+'-'+str(index)+'.jpg');index+=1
   # simctl can write complete pixels before its process times out. Preserve a
   # valid bounded image as evidence, while keeping that command/ACK gate red.
   try:
    if blocked():raise RuntimeError('Owned cleanup barrier forbids screenshot command')
    result=subprocess.run(['xcrun','simctl','io',udid,'screenshot',str(raw)],capture_output=True,text=True,timeout=20)
    row['screenshot_exit']=result.returncode;row['message']=(result.stdout+result.stderr)[-1600:]
   except subprocess.TimeoutExpired:
    row['screenshot_exit']=124;row['error']='Public simctl screenshot timed out after 20 seconds'
   assert raw.exists() and not raw.is_symlink() and 0<raw.stat().st_size<=32*1024*1024,'No bounded screenshot file was produced'
   if blocked():raise RuntimeError('Owned cleanup barrier forbids image conversion command')
   subprocess.run(['sips','-s','format','jpeg','-s','formatOptions','50','-Z','1440',str(raw),'--out',str(jpeg)],check=True,capture_output=True,timeout=12)
   data=jpeg.read_bytes()
   if len(data)>800*1024:jpeg.unlink();raise ValueError('Checkpoint image exceeded per-file evidence cap')
   row.update(success=row['screenshot_exit']==0,pixels_retained=True,file=jpeg.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
   if row['screenshot_exit']!=0:row.setdefault('error','Public simctl screenshot did not complete successfully')
  except Exception as e:row['error']=str(e)
  finally:
   if staged and staged.exists():staged.unlink()
   if raw and raw.exists():raw.unlink()
   if ack:
    try:binding.acknowledge(request_id,names,row)
    except Exception as error:row.update(success=False,acknowledgement_error=str(error)[:1600])
   report.append(row);write_json(out/'checkpoint-captures.json',report);print(json.dumps(row),flush=True)
 failure.observe(text)
 if (out/'ui-completed.marker').exists():break
 time.sleep(.25)
if not bindings or any(not row['success'] for row in bindings):raise SystemExit('A pre-UI Vision runner binding failed')
if failure.attempted:raise SystemExit('Original XCTest failure retained after diagnostic-only capture')
if not report or any(not row['success'] for row in report):raise SystemExit('A held Vision screenshot checkpoint was not captured')
