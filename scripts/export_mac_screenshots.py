#!/usr/bin/env python3
"""Bounded native XCTest evidence. No app binaries or full xcresult upload."""
import hashlib,json,os,pathlib,struct,subprocess
def validate_supporting_layout_receipt(data):
 if len(data)>4096:raise ValueError('Supporting text receipt exceeds 4 KiB')
 value=json.loads(data)
 if value.get('locale') not in {'en','zh-Hans'} or value.get('phase') not in {'full','minimum-long-content'}:raise ValueError('Unknown supporting text checkpoint')
 if value.get('contrast_qualified') is not False or value.get('reference_font_is_resolved_element_font') is not False:raise ValueError('Unsupported native contrast/font claim')
 rows=value.get('roles')
 if not isinstance(rows,list) or [row.get('role') for row in rows]!=['link-policy','saved-count']:raise ValueError('Missing supporting text roles')
 expected_policy={'en':'Links open only when you choose Open in Browser.','zh-Hans':'只有点击「在浏览器中打开」才会打开链接。'}[value['locale']]
 count=1 if value['phase']=='full' else 2
 expected_count=f'{count} saved on this Mac' if value['locale']=='en' else f'本机已保存 {count} 条记录'
 if [row.get('text') for row in rows]!=[expected_policy,expected_count]:raise ValueError('Changed or truncated supporting strings')
 return value
limit=json.loads(pathlib.Path('scripts/evidence-allocation.json').read_text())['scope_limits_bytes']['macos']
out=pathlib.Path('build/mac-evidence');out.mkdir(parents=True,exist_ok=True)
barrier=pathlib.Path('build/owned-process-cleanup.json')
if barrier.exists():
 assert not barrier.is_symlink() and barrier.stat().st_size<=2048
 (out/barrier.name).write_bytes(barrier.read_bytes())
provenance={'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),'workflow_sha':os.environ.get('GITHUB_WORKFLOW_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),'toolchain':subprocess.check_output(['xcodebuild','-version'],text=True).strip(),'architecture':subprocess.check_output(['uname','-m'],text=True).strip()}
icon=pathlib.Path('build/icon-verification/mac-bundled-icon.png')
package=pathlib.Path('build/native-release-evidence/mac-release.json')
if package.is_file():
 data=package.read_bytes();assert len(data)<8192;(out/package.name).write_bytes(data)
if icon.exists():
 data=icon.read_bytes();assert len(data)<=600*1024;(out/icon.name).write_bytes(data);provenance['bundled_icon_sha256']=hashlib.sha256(data).hexdigest()
for name in ['mac-test.log','mac-sandbox-test.log','mac-sandbox-build.log']:
 path=pathlib.Path(name)
 if path.exists():(out/name.replace('.log','-tail.log')).write_bytes(path.read_bytes()[-256*1024:])
for name in ['mac-sandbox-entitlements.plist','mac-sandbox-signature.txt']:
 path=pathlib.Path('build')/name
 if path.exists():
  data=path.read_bytes();assert len(data)<16384;(out/name).write_bytes(data)
(out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
def records(value):
 if isinstance(value,dict):
  if 'exportedFileName' in value:yield value
  for child in value.values():yield from records(child)
 elif isinstance(value,list):
  for child in value:yield from records(child)
screenshots=[];warnings=[]
names=['mac-system-picker-before-selection','mac-system-picker-after-selection','mac-real-photos-import','mac-sandbox-legacy-reopened','mac-chinese-policy','mac-english-policy','mac-reopened-history','mac-camera-unavailable','mac-pasted-url','mac-chinese-reopened','mac-minimum-window','mac-before-resize','mac-before-export','mac-imported-unicode','mac-failure']
def checkpoint_name(entry):
 text=' '.join(v for v in entry.values() if isinstance(v,str))
 return next((n for n in names if n in text),None)
lossless_controls={'mac-before-resize','mac-minimum-window','mac-before-export','mac-pasted-url'}
first_failure_retained=False
# Prefer the stricter sandbox's actual pixels; keep both full structured summaries.
for result,label in [('MacSandboxResults.xcresult','sandbox'),('MacTestResults.xcresult','native')]:
 if not pathlib.Path(result,'Info.plist').is_file():
  print(label,'No test result bundle produced',flush=True);continue
 summary=subprocess.run(['xcrun','xcresulttool','get','test-results','summary','--path',result],capture_output=True,text=True)
 (out/('sandbox-test-summary.json' if label=='sandbox' else 'test-summary.json')).write_text(summary.stdout if summary.returncode==0 else json.dumps({'summary_error':summary.stderr}))
 if summary.returncode==0:warnings.extend(json.loads(summary.stdout).get('runtimeWarnings',[]))
 folder=pathlib.Path('build/mac-screenshots')/label;folder.mkdir(parents=True,exist_ok=True)
 subprocess.run(['xcrun','xcresulttool','export','attachments','--path',result,'--output-path',str(folder)],check=True)
 entries=list(records(json.loads((folder/'manifest.json').read_text())))
 first_failure=next((entry for entry in entries if checkpoint_name(entry)=='mac-failure'),None)
 # Seven nearly duplicate failure frames previously consumed the image slots
 # before the real Photos picker checkpoints. Preserve the first failure and
 # then the explicit workflow priorities, within the fourteen-image cap and unchanged three-megabyte allocation.
 entries.sort(key=lambda entry:-1 if entry is first_failure else names.index(checkpoint_name(entry)) if checkpoint_name(entry) in names else len(names))
 for entry in entries:
  text=' '.join(v for v in entry.values() if isinstance(v,str));name=next((n for n in names if n in text),None)
  path=(folder/entry['exportedFileName']).resolve();assert path.is_relative_to(folder.resolve())
  if 'mac-audit-element' in text:
   data=path.read_bytes();assert len(data)<=64*1024
   count=len(list(out.glob('*-audit-*.txt')))
   (out/f'{label}-audit-{count+1}.txt').write_bytes(data);continue
  if 'mac-supporting-text-layout' in text:
   data=path.read_bytes();receipt=validate_supporting_layout_receipt(data)
   filename=f'{label}-supporting-text-{receipt["locale"]}-{receipt["phase"]}.json'
   if len(list(out.glob('*-supporting-text-*.json')))>=4:raise ValueError('Supporting text evidence exceeds four bounded receipts')
   if (out/filename).exists():raise ValueError('Duplicate supporting text checkpoint')
   (out/filename).write_bytes(data);continue
  if not name:continue
  if name=='mac-failure':
   if first_failure_retained:continue
   first_failure_retained=True
  data=path.read_bytes()
  if len(data)>800*1024:raise ValueError('Oversized native Mac screenshot')
  dimensions=None
  if name in lossless_controls:
   if not (data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>24 and data[12:16]==b'IHDR'):raise ValueError('Paired Mac controls require native PNG bytes')
   dimensions=list(struct.unpack('>II',data[16:24]))
   if not all(0<v<=4096 for v in dimensions):raise ValueError('Invalid native Mac screenshot dimensions')
  elif not data.startswith(b'\xff\xd8'):raise ValueError('Only the four paired Mac controls may use PNG')
  digest=hashlib.sha256(data).hexdigest()
  existing=next((item for item in screenshots if item['sha256']==digest),None)
  if existing:
   existing.setdefault('additional_checkpoint_names',[]).append(name);continue
  if len(screenshots)>=14 or sum(p.stat().st_size for p in out.iterdir())+len(data)>limit-256*1024:
   print('OMITTED_AT_BOUNDED_CAP',label,name,flush=True);continue
  suffix='png' if dimensions else 'jpg'
  filename=f'{len(screenshots)+1}-{label}-{name}.{suffix}';(out/filename).write_bytes(data)
  item={'name':filename,'scope':label,'bytes':len(data),'sha256':digest}
  if dimensions:item.update(native_pixel_dimensions=dimensions,source_bytes_preserved=True)
  screenshots.append(item);print(json.dumps(item),flush=True)
(out/'screenshots.json').write_text(json.dumps(screenshots,indent=2)+'\n')
# These four exact checkpoints form two fixed-state controls. Missing one must
# stay visible as an evidence failure, including when a prerequisite stopped it.
required_controls={'mac-before-resize','mac-minimum-window','mac-before-export','mac-pasted-url'}
retained_controls=set()
for item in screenshots:
 for checkpoint in required_controls:
  if checkpoint in item['name'] or checkpoint in item.get('additional_checkpoint_names',[]):retained_controls.add(checkpoint)
missing_controls=sorted(required_controls-retained_controls)
if missing_controls:raise SystemExit('Required fixed-state Mac control evidence missing: '+', '.join(missing_controls))
size=sum(p.stat().st_size for p in out.iterdir());assert size<=limit
print(json.dumps({'mac_evidence_bytes':size,'exported_screenshots':len(screenshots)}),flush=True)
if any('Publishing changes from within view updates' in item.get('message','') for item in warnings):
 raise SystemExit('SwiftUI re-entrant publication warning is a release blocker')
for name in ['mac-test.log','mac-sandbox-test.log']:
 path=pathlib.Path(name)
 if path.exists() and 'vnode unlinked' in path.read_text(errors='replace'):
  raise SystemExit('SQLite files were unlinked while open; close fixture stores before cleanup')
