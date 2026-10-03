#!/usr/bin/env python3
"""Bounded native XCTest evidence, with exact bytes and runner-side SHA-256."""
import base64,hashlib,json,pathlib,subprocess
result='MacTestResults.xcresult'
if not pathlib.Path(result,'Info.plist').is_file():
 print('No Mac test result bundle was produced',flush=True)
 raise SystemExit(0)
destination=pathlib.Path('build/mac-screenshots');destination.mkdir(parents=True,exist_ok=True)
subprocess.run(['xcrun','xcresulttool','export','attachments','--path',result,'--output-path',str(destination)],check=True)
def records(value):
 if isinstance(value,dict):
  if 'exportedFileName' in value:yield value
  for v in value.values():yield from records(v)
 elif isinstance(value,list):
  for v in value:yield from records(v)
manifest=json.loads((destination/'manifest.json').read_text());count=0
for item in records(manifest):
 label=' '.join(v for v in item.values() if isinstance(v,str))
 name=next((n for n in ['mac-imported-unicode','mac-reopened-history','mac-camera-unavailable','mac-failure'] if n in label),None)
 if not name:continue
 path=(destination/item['exportedFileName']).resolve();assert path.is_relative_to(destination.resolve())
 data=path.read_bytes();assert data.startswith(b'\xff\xd8') and len(data)<=800*1024
 print('SCREENSHOT_BEGIN:'+name,flush=True);print('SCREENSHOT_BYTES:'+str(len(data)),flush=True);print('SCREENSHOT_SHA256:'+hashlib.sha256(data).hexdigest(),flush=True)
 encoded=base64.b64encode(data).decode()
 for offset in range(0,len(encoded),4096):print('SCREENSHOT_CHUNK:'+encoded[offset:offset+4096],flush=True)
 print('SCREENSHOT_END:'+name,flush=True);count+=1
print('Exported screenshots:',count,flush=True)
if count==0:print(json.dumps(manifest)[:12000],flush=True)
