#!/usr/bin/env python3
"""Bounded native XCTest evidence. No app binaries or full xcresult upload."""
import hashlib,json,os,pathlib,re,struct,subprocess
def validate_supporting_layout_receipt(data):
 if len(data)>4096:raise ValueError('Supporting text receipt exceeds 4 KiB')
 value=json.loads(data)
 if value.get('locale') not in {'en','zh-Hans'} or value.get('phase') not in {'full','minimum-long-content'}:raise ValueError('Unknown supporting text checkpoint')
 if value.get('contrast_qualified') is not False or value.get('reference_font_is_resolved_element_font') is not False:raise ValueError('Unsupported native contrast/font claim')
 if value.get('height_proxy_used_as_acceptance') is not False:raise ValueError('Reference font cannot qualify actual wrapping')
 rows=value.get('roles')
 if not isinstance(rows,list) or [row.get('role') for row in rows]!=['link-policy','saved-count']:raise ValueError('Missing supporting text roles')
 expected_policy={'en':'Links open only when you choose Open in Browser.','zh-Hans':'只有点击「在浏览器中打开」才会打开链接。'}[value['locale']]
 count=1 if value['phase']=='full' else 2
 expected_count=f'{count} saved on this Mac' if value['locale']=='en' else f'本机已保存 {count} 条记录'
 if [row.get('text') for row in rows]!=[expected_policy,expected_count]:raise ValueError('Changed or truncated supporting strings')
 return value
def validate_payload_transition(data):
 if len(data)>4096:raise ValueError('Payload transition receipt exceeds 4 KiB')
 value=json.loads(data)
 if value.get('locale') not in {'en','zh-Hans'} or value.get('phase') not in {'prepared','copy-observed'}:raise ValueError('Unknown payload transition checkpoint')
 if type(value.get('full_equality_verified')) is not bool or type(value.get('fixture_control_exact')) is not bool:raise ValueError('Unknown transition outcome')
 if value.get('wrapper_identity_refresh_scope')!='selectable Text only':raise ValueError('Unexpected payload identity scope')
 for key in ['raster_width','raster_height','clipboard_tiff_bytes','expected_payload_utf8_bytes']:
  if type(value.get(key)) is not int or value[key]<=0:raise ValueError('Missing actual fixture/raster evidence')
 for key in ['expected_payload_sha256','clipboard_tiff_sha256']:
  if not isinstance(value.get(key),str) or len(value[key])!=64 or any(c not in '0123456789abcdef' for c in value[key]):raise ValueError('Invalid source fingerprint')
 expected_before={'en':'https://example.com/qrcatcher?source=golden','zh-Hans':'QRCatcher 你好 🌈 123'}[value['locale']]
 if value.get('wrapper_before')!=expected_before or value.get('copy_before')!=expected_before:raise ValueError('Missing exact first payload/Copy state')
 if value['phase']=='prepared' and value['full_equality_verified']:raise ValueError('Preparation cannot qualify product equality')
 if value['phase']=='copy-observed' and value['full_equality_verified']:
  after=value.get('wrapper_after')
  if (not value['fixture_control_exact'] or not isinstance(after,str) or
      hashlib.sha256(after.encode()).hexdigest()!=value['expected_payload_sha256'] or
      len(after.encode())!=value['expected_payload_utf8_bytes'] or
      value.get('copy_after_sha256')!=value['expected_payload_sha256'] or
      value.get('copy_after_utf8_bytes')!=value['expected_payload_utf8_bytes']):raise ValueError('Claimed full equality lacks exact readback')
 return value
def missing_required_frames(screenshots,required):
 retained=set()
 for item in screenshots:
  retained.update(item.get('additional_checkpoint_names',[]))
  if item.get('checkpoint') in required:retained.add(item['checkpoint'])
 return sorted(set(required)-retained)
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
names=['mac-system-picker-before-selection','mac-system-picker-after-selection','mac-real-photos-import','mac-sandbox-legacy-reopened','mac-chinese-policy','mac-english-policy','mac-reopened-history','mac-camera-unavailable','mac-pasted-url','mac-chinese-reopened','mac-minimum-window','mac-before-resize','mac-before-export','mac-imported-unicode','mac-minimum-long-text-en','mac-minimum-long-text-zh-Hans','mac-failure']
image_limit=16
def checkpoint_name(entry):
 # The current xcresulttool prints suggestions in this exact decorated form:
 # mac-minimum-window_0_C17CB4FC-D16E-4FA8-9551-EDA6E400A4D2.png.
 # Resolve each metadata field independently; never substring-match a longer
 # checkpoint or silently choose between conflicting recognized identities.
 found=set()
 uuid=r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}'
 for key,value in entry.items():
  if not isinstance(value,str):continue
  if value in names:found.add(value);continue
  match=re.fullmatch(r'('+ '|'.join(re.escape(name) for name in names)+r')_(?:0|[1-9][0-9]*)_'+uuid+r'\.(?:png|jpeg|jpg)',value)
  if match:found.add(match.group(1))
  elif key in {'name','suggestedHumanReadableName'} and any(value.startswith(name) for name in names):
   raise ValueError('Malformed Mac checkpoint metadata')
 if len(found)>1:raise ValueError('Conflicting Mac checkpoint metadata')
 return next(iter(found),None)
lossless_controls={'mac-before-resize','mac-minimum-window','mac-before-export','mac-pasted-url'}
lossless_frames=lossless_controls|{'mac-chinese-reopened','mac-minimum-long-text-en','mac-minimum-long-text-zh-Hans'}
required_frames=lossless_frames
# Ordinary conditional checkpoints remain retained when emitted; do not invent
# a missing remote-picker fallback when the direct AX selection path succeeded.
first_failure_retained=False
seen_frames=set()
all_entries=[]
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
 all_entries.extend((entry,folder,label) for entry in entries)
# An ordinary checkpoint is emitted once. Duplicate records are ambiguous,
# including across bundles; repeated generic failure frames retain only the first.
checkpoint_counts={}
for entry,_,_ in all_entries:
 name=checkpoint_name(entry)
 if name and name!='mac-failure':
  checkpoint_counts[name]=checkpoint_counts.get(name,0)+1
  if checkpoint_counts[name]>1:raise ValueError('Duplicate Mac checkpoint: '+name)
# Prioritize all mandatory images across both bundles before optional extras.
def priority(item):
 name=checkpoint_name(item[0])
 return (0 if name in required_frames else 1 if name in names and name!='mac-failure' else 2, names.index(name) if name in names else len(names))
all_entries.sort(key=priority)
for entry,folder,label in all_entries:
 text=' '.join(v for v in entry.values() if isinstance(v,str));name=checkpoint_name(entry)
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
 if 'mac-payload-transition' in text:
  data=path.read_bytes();receipt=validate_payload_transition(data)
  filename=f'{label}-payload-transition-{receipt["locale"]}-{receipt["phase"]}.json'
  if len(list(out.glob('*-payload-transition-*.json')))>=4 or (out/filename).exists():raise ValueError('Duplicate or excessive payload transition receipts')
  (out/filename).write_bytes(data);continue
 if not name or name in seen_frames:continue
 if name=='mac-failure':
  if first_failure_retained:continue
  first_failure_retained=True
 data=path.read_bytes()
 if len(data)>800*1024:raise ValueError('Oversized native Mac screenshot')
 dimensions=None
 if name in lossless_frames:
  if not (data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>24 and data[12:16]==b'IHDR'):raise ValueError('Allowlisted lossless Mac checkpoints require native PNG bytes')
  dimensions=list(struct.unpack('>II',data[16:24]))
  if not all(0<v<=4096 for v in dimensions):raise ValueError('Invalid native Mac screenshot dimensions')
 elif not data.startswith(b'\xff\xd8'):raise ValueError('Only exact allowlisted Mac checkpoints may use PNG')
 digest=hashlib.sha256(data).hexdigest()
 existing=next((item for item in screenshots if item['sha256']==digest),None)
 if existing:
  existing.setdefault('additional_checkpoint_names',[]).append(name);seen_frames.add(name);continue
 if len(screenshots)>=image_limit or sum(p.stat().st_size for p in out.iterdir())+len(data)>limit-256*1024:
  print('OMITTED_AT_BOUNDED_CAP',label,name,flush=True);continue
 suffix='png' if dimensions else 'jpg'
 filename=f'{len(screenshots)+1}-{label}-{name}.{suffix}';(out/filename).write_bytes(data)
 item={'name':filename,'checkpoint':name,'scope':label,'bytes':len(data),'sha256':digest}
 if dimensions:item.update(native_pixel_dimensions=dimensions,source_bytes_preserved=True)
 screenshots.append(item);seen_frames.add(name);print(json.dumps(item),flush=True)
(out/'screenshots.json').write_text(json.dumps(screenshots,indent=2)+'\n')
missing_frames=missing_required_frames(screenshots,required_frames)
emitted_frames={checkpoint_name(entry) for entry,_,_ in all_entries}-{'mac-failure',None}
omitted_emitted=missing_required_frames(screenshots,emitted_frames)
(out/'frame-coverage.json').write_text(json.dumps({'required':sorted(required_frames),'missing':missing_frames,'omitted_emitted':omitted_emitted,'image_limit':image_limit,'complete':not (missing_frames or omitted_emitted)},indent=2)+'\n')
# These four exact checkpoints form two fixed-state controls. Missing one must
# stay visible as an evidence failure, including when a prerequisite stopped it.
required_controls={'mac-before-resize','mac-minimum-window','mac-before-export','mac-pasted-url'}
retained_controls=set()
for item in screenshots:
 for checkpoint in required_controls:
  if checkpoint==item.get('checkpoint') or checkpoint in item.get('additional_checkpoint_names',[]):retained_controls.add(checkpoint)
missing_controls=sorted(required_controls-retained_controls)
if missing_controls:raise SystemExit('Required fixed-state Mac control evidence missing: '+', '.join(missing_controls))
if missing_frames:raise SystemExit('Required ordinary/readability Mac evidence missing: '+', '.join(missing_frames))
if omitted_emitted:raise SystemExit('Emitted ordinary Mac evidence omitted at cap: '+', '.join(omitted_emitted))
size=sum(p.stat().st_size for p in out.iterdir());assert size<=limit
print(json.dumps({'mac_evidence_bytes':size,'exported_screenshots':len(screenshots)}),flush=True)
if any('Publishing changes from within view updates' in item.get('message','') for item in warnings):
 raise SystemExit('SwiftUI re-entrant publication warning is a release blocker')
for name in ['mac-test.log','mac-sandbox-test.log']:
 path=pathlib.Path(name)
 if path.exists() and 'vnode unlinked' in path.read_text(errors='replace'):
  raise SystemExit('SQLite files were unlinked while open; close fixture stores before cleanup')
