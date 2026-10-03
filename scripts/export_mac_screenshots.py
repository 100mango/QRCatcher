#!/usr/bin/env python3
"""Bounded native XCTest evidence, with exact bytes and runner-side SHA-256.
Runs after Mac XCTest, before unrelated platform stages. No large xcresult upload.
"""
import hashlib,json,os,pathlib,subprocess
result='MacTestResults.xcresult'
evidence=pathlib.Path('build/mac-evidence');evidence.mkdir(parents=True,exist_ok=True)
provenance={'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),'workflow_sha':os.environ.get('GITHUB_WORKFLOW_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),'toolchain':subprocess.check_output(['xcodebuild','-version'],text=True).strip(),'architecture':subprocess.check_output(['uname','-m'],text=True).strip()}
(evidence/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
log=pathlib.Path('mac-test.log')
if log.exists():(evidence/'mac-test-tail.log').write_bytes(log.read_bytes()[-1024*1024:])
if not pathlib.Path(result,'Info.plist').is_file():
 print('No Mac test result bundle was produced',flush=True)
 raise SystemExit(0)
summary=subprocess.run(['xcrun','xcresulttool','get','test-results','summary','--path',result],capture_output=True,text=True)
(evidence/'test-summary.json').write_text(summary.stdout if summary.returncode==0 else json.dumps({'summary_error':summary.stderr}))
destination=pathlib.Path('build/mac-screenshots');destination.mkdir(parents=True,exist_ok=True)
subprocess.run(['xcrun','xcresulttool','export','attachments','--path',result,'--output-path',str(destination)],check=True)
def records(value):
 if isinstance(value,dict):
  if 'exportedFileName' in value:yield value
  for v in value.values():yield from records(v)
 elif isinstance(value,list):
  for v in value:yield from records(v)
manifest=json.loads((destination/'manifest.json').read_text());screenshots=[]
for item in records(manifest):
 label=' '.join(v for v in item.values() if isinstance(v,str))
 name=next((n for n in ['mac-imported-unicode','mac-reopened-history','mac-camera-unavailable','mac-pasted-url','mac-chinese-reopened','mac-minimum-window','mac-failure'] if n in label),None)
 if not name:continue
 assert len(screenshots)<6,'Screenshot evidence budget exceeded'
 path=(destination/item['exportedFileName']).resolve();assert path.is_relative_to(destination.resolve())
 data=path.read_bytes();assert data.startswith(b'\xff\xd8') and len(data)<=800*1024
 name=f'{len(screenshots)+1}-{name}.jpg';(evidence/name).write_bytes(data)
 entry={'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()};screenshots.append(entry);print(json.dumps(entry),flush=True)
(evidence/'screenshots.json').write_text(json.dumps(screenshots,indent=2)+'\n')
assert sum(p.stat().st_size for p in evidence.iterdir())<=6*1024*1024,'Total evidence budget exceeded'
print('Exported screenshots:',len(screenshots),flush=True)
if not screenshots:print(json.dumps(manifest)[:12000],flush=True)

if summary.returncode == 0:
 warnings=json.loads(summary.stdout).get('runtimeWarnings',[])
 if any('Publishing changes from within view updates' in x.get('message','') for x in warnings):
  raise SystemExit('SwiftUI re-entrant publication warning is a release blocker')
