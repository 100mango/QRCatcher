#!/usr/bin/env python3
"""Bounded read-only app inventory; optional GUI launch never gates XCTest."""
import json,os,plistlib,subprocess,sys
from pathlib import Path
from owned_process_barrier import blocked
if blocked(): raise SystemExit(126)
out=Path('build/vision-runtime');out.mkdir(parents=True,exist_ok=True)
roots=[Path('/Applications'),Path('/System/Applications'),Path(os.environ['DEVELOPER_DIR'])/'Applications']
report={'bundle_identifier':'com.apple.iphonesimulator','visited_directories':0,'candidates':[],'launched':False}
seen=set()
for root in roots:
 if not root.is_dir():continue
 for folder,dirs,_ in os.walk(root):
  if report['visited_directories']>=400:break
  path=Path(folder);depth=len(path.relative_to(root).parts);report['visited_directories']+=1
  dirs[:]=[d for d in dirs if not d.startswith('.') and not (path/d).is_symlink()]
  if depth>6:dirs[:]=[];continue
  if path.suffix=='.app':
   identifier=None
   try:
    info=plistlib.loads((path/'Contents/Info.plist').read_bytes());identifier=info.get('CFBundleIdentifier')
    if identifier=='com.apple.iphonesimulator' and str(path) not in seen:
     seen.add(str(path));report['candidates'].append({'path':str(path),'version':info.get('CFBundleShortVersionString'),'identifier':identifier})
   except (OSError,ValueError):pass
   if identifier!='com.apple.dt.Xcode':dirs[:]=[]
 if report['visited_directories']>=400:break
if report['candidates']:
 candidate=sorted(report['candidates'],key=lambda row:not str(row['version']).startswith('27'))[0]
 command=['open',candidate['path'],'--args','-CurrentDeviceUDID',sys.argv[1]]
 try:
  result=subprocess.run(command,text=True,capture_output=True,timeout=30)
  report.update(command=command,exit=result.returncode,diagnostic=(result.stdout+result.stderr)[-2000:],launched=result.returncode==0)
 except subprocess.TimeoutExpired:report.update(command=command,exit=124,diagnostic='Optional GUI launch timed out')
else:report['diagnostic']='No installed matching Simulator app bundle found within bounded standard app inventory; CLI/XCTest continue independently'
encoded=json.dumps(report,indent=2)+'\n';assert len(encoded.encode())<16384
(out/'optional-simulator.json').write_text(encoded);print(encoded,flush=True)
