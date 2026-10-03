#!/usr/bin/env python3
"""Public simctl screenshot at explicit post-assertion XCTest checkpoints.
Native visionOS reports manual XCTest screenshots unsupported. Keep actual
simulator pixels separately and never treat an empty XCTest bitmap as proof.
"""
import hashlib,json,re,subprocess,sys,time
from pathlib import Path
udid,log=sys.argv[1:];log=Path(log);out=Path('build/vision-runtime');out.mkdir(parents=True,exist_ok=True)
seen=set();report=[];deadline=time.monotonic()+420
while time.monotonic()<deadline:
 text=log.read_text(errors='replace') if log.exists() else ''
 for name in re.findall(r'QRCATCHER_VISION_CAPTURE:(vision-[a-z-]+)',text):
  if name in seen or name not in ['vision-imported-qr','vision-reopened-history','vision-failure']:continue
  seen.add(name);row={'checkpoint':name,'source':'public simctl io screenshot','status':'failed'}
  try:
   raw=out/(name+'.raw.png');jpeg=out/(name+'.jpg')
   result=subprocess.run(['xcrun','simctl','io',udid,'screenshot',str(raw)],capture_output=True,text=True,timeout=30)
   row['screenshot_exit']=result.returncode;row['message']=(result.stdout+result.stderr)[-2000:]
   if result.returncode==0:
    subprocess.run(['sips','-s','format','jpeg','-s','formatOptions','50','-Z','1440',str(raw),'--out',str(jpeg)],check=True,capture_output=True,timeout=20)
    data=jpeg.read_bytes()
    if len(data)>800*1024:jpeg.unlink();raise ValueError('Checkpoint image exceeded per-file evidence cap')
    row.update(status='captured',file=jpeg.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
   if raw.exists():raw.unlink()
  except Exception as e:row['error']=str(e)
  report.append(row);(out/'checkpoint-captures.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
 if (out/'ui-completed.marker').exists():break
 time.sleep(.25)
