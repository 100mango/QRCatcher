#!/usr/bin/env python3
"""Capture actual simulator pixels while XCTest holds a UUID request/ack checkpoint.
Only the exact built runner's own temporary files are read/written, via public
simctl get_app_container; no accessibility/TCC/database mutation is involved.
"""
import hashlib,json,plistlib,re,subprocess,sys,time,uuid
from pathlib import Path
udid,log=sys.argv[1:];log=Path(log);out=Path('build/vision-runtime');out.mkdir(parents=True,exist_ok=True)
runner=Path('build/VisionTests/Build/Products/Debug-xrsimulator/QRCatcherVisionUITests-Runner.app/Info.plist')
runner_id=plistlib.loads(runner.read_bytes())['CFBundleIdentifier']
seen=set();report=[];deadline=time.monotonic()+900
while time.monotonic()<deadline:
 text=log.read_text(errors='replace') if log.exists() else ''
 for request_id in re.findall(r'QRCATCHER_VISION_CAPTURE_REQUEST:([A-F0-9-]{36})',text):
  if request_id in seen:continue
  assert str(uuid.UUID(request_id)).upper()==request_id
  seen.add(request_id);row={'id':request_id,'source':'public simctl screenshot at held XCTest checkpoint','success':False};ack=None;raw=None
  try:
   container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',udid,runner_id,'data'],text=True,timeout=20).strip())
   request=container/'tmp'/('QRCatcher-capture-'+request_id+'.json');ack=request.with_suffix('.ack')
   assert not request.is_symlink() and request.stat().st_size<1024
   descriptor=json.loads(request.read_text());name=descriptor['name']
   assert descriptor['id']==request_id and name in ['vision-imported-qr','vision-reopened-history','vision-exported-qr','vision-exported-history','vision-files-import-reopened','vision-chinese-empty','vision-chinese-result','vision-chinese-policy','vision-failure']
   if name in ['vision-exported-qr','vision-exported-history']:
    test_store=descriptor['test_store'];assert str(uuid.UUID(test_store)).upper()==test_store
    app_container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',udid,'100mango.QRCatcher','data'],text=True,timeout=20).strip())
    receipts=app_container/'Documents/QRCatcherExportTestReceipts'/test_store
    kind='png' if name=='vision-exported-qr' else 'json'
    receipt_file=receipts/(kind+'.json');saved=receipts/('saved.'+kind)
    assert not receipt_file.is_symlink() and receipt_file.stat().st_size<2048
    receipt=json.loads(receipt_file.read_text());assert receipt['test_store']==test_store and receipt['type']==kind
    assert not saved.is_symlink() and 0<saved.stat().st_size<=2*1024*1024
    saved_bytes=saved.read_bytes();assert len(saved_bytes)==receipt['bytes'] and hashlib.sha256(saved_bytes).hexdigest()==receipt['sha256']
    if kind=='png':
     subprocess.run(['xcrun','swift','scripts/verify_vision_export_pixels.swift',str(saved)],check=True,timeout=30)
    else:
     history=json.loads(saved_bytes);assert history['format']=='QRCatcher.history' and history['version']==1
     assert len(history['records'])==1 and history['records'][0]['payload']=='QRCatcher 你好 🌈 123'
    assert len(saved_bytes)<128*1024,'Synthetic output evidence exceeded its separate cap'
    (out/('actual-export.'+kind)).write_bytes(saved_bytes)
    row['actual_export_readback']=receipt
   row['checkpoint']=name;raw=out/(request_id+'.raw.png');jpeg=out/(name+'.jpg')
   # simctl can write complete pixels before its process times out. Preserve a
   # valid bounded image as evidence, while keeping that command/ACK gate red.
   try:
    result=subprocess.run(['xcrun','simctl','io',udid,'screenshot',str(raw)],capture_output=True,text=True,timeout=20)
    row['screenshot_exit']=result.returncode;row['message']=(result.stdout+result.stderr)[-1600:]
   except subprocess.TimeoutExpired:
    row['screenshot_exit']=124;row['error']='Public simctl screenshot timed out after 20 seconds'
   assert raw.exists() and not raw.is_symlink() and 0<raw.stat().st_size<=32*1024*1024,'No bounded screenshot file was produced'
   subprocess.run(['sips','-s','format','jpeg','-s','formatOptions','50','-Z','1440',str(raw),'--out',str(jpeg)],check=True,capture_output=True,timeout=12)
   data=jpeg.read_bytes()
   if len(data)>800*1024:jpeg.unlink();raise ValueError('Checkpoint image exceeded per-file evidence cap')
   row.update(success=row['screenshot_exit']==0,pixels_retained=True,file=jpeg.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
   if row['screenshot_exit']!=0:row.setdefault('error','Public simctl screenshot did not complete successfully')
  except Exception as e:row['error']=str(e)
  finally:
   if raw and raw.exists():raw.unlink()
   if ack:ack.write_text(json.dumps(row)+'\n')
  report.append(row);(out/'checkpoint-captures.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
 if (out/'ui-completed.marker').exists():break
 time.sleep(.25)
if not report or any(not row['success'] for row in report):raise SystemExit('A held Vision screenshot checkpoint was not captured')
