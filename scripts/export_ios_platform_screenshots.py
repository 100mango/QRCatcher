#!/usr/bin/env python3
"""Bounded synthetic phone/iPad evidence. Never uploads full xcresult archives."""
import hashlib,json,os,pathlib,struct,subprocess
scope=os.environ['EVIDENCE_SCOPE']
limit=json.loads(pathlib.Path('scripts/evidence-allocation.json').read_text())['scope_limits_bytes'][scope]
out=pathlib.Path('build/ios-platform-evidence');out.mkdir(parents=True,exist_ok=True)
summary={'scope':scope,'scope_limit_bytes':limit,'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),'run_id':os.environ.get('GITHUB_RUN_ID'),'screenshots':[],'omitted':[],'results':{}}
barrier=pathlib.Path('build/owned-process-cleanup.json')
if barrier.exists():
 assert not barrier.is_symlink() and barrier.stat().st_size<=2048
 (out/barrier.name).write_bytes(barrier.read_bytes())
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
for name in ['release-watch.log','release-tv.log','release-vision.log','watch-test-build.log','watch-unit.log','watch-ui.log','tv-test-build.log','tv-test.log','tv-authorized-test.log','tv-revoked-test.log','vision-test-build.log','vision-test.log','vision-ui-test.log','ios-test-build.log','ios-unit.log','PhoneUIResults.log','CompactPhoneUIResults.log','PadUIResults.log','MiniUIResults.log','PadUIResults-layout.log','MiniUIResults-layout.log','PhoneUIResults-imports.log','CompactPhoneUIResults-imports.log']:
 path=pathlib.Path(name)
 if path.is_file():(out/name).write_bytes(path.read_bytes()[-64*1024:])
names=('image-import-files-decoded','image-import-photos-decoded','image-import-real-photos','image-import-real-files','image-import-failure','tv-history-after-removal','tv-history-focused-record','tv-history-focused-delete','tv-history-list','tv-offline-policy','tv-chinese-result','watch-recovered-journal','watch-saved-preview','phone-failure','tv-revoked-photos','watch-empty','watch-offline-policy','watch-fixture-offline-result','watch-system-picker-unavailable','watch-reopened-qr','watch-failure','tv-real-photo-result','tv-verified-photos-output','tv-reopened-history','tv-failure','vision-imported-qr','vision-reopened-history','vision-failure','synthetic-scan-result','synthetic-history','privacy-open-diagnostic','privacy-return-diagnostic','ipad-anchored-share','ipad-split-portrait','ipad-large-text','ipad-imported-photo','ipad-failure','view-layout-320x568-largest-text','view-layout-568x320-largest-text')
def records(value):
 if isinstance(value,dict):
  if 'exportedFileName' in value:yield value
  for child in value.values():yield from records(child)
 elif isinstance(value,list):
  for child in value:yield from records(child)
for result,label in [('WatchUnitResults.xcresult','watch-unit'),('WatchUIResults.xcresult','watch-ui'),('WatchLargestUIResults.xcresult','watch-largest'),('TVTestResults.xcresult','apple-tv'),('TVAuthorizedUIResults.xcresult','apple-tv-pregranted'),('TVRevokedUIResults.xcresult','apple-tv-revoked'),('TVLargestUIResults.xcresult','apple-tv-largest'),('VisionTestResults.xcresult','vision-pro-unit'),('VisionUIResults.xcresult','vision-pro-ui'),('VisionPhotosUIResults.xcresult','vision-photos-ui'),('VisionFilesUIResults.xcresult','vision-files-ui'),('VisionChineseUIResults.xcresult','vision-chinese-ui'),('VisionLargestUIResults.xcresult','vision-largest'),('iOSUnitResults.xcresult','view-layout-host'),('PhoneUIResults.xcresult','pro-max'),('CompactPhoneUIResults.xcresult','SE3'),('PhoneUIResults-imports.xcresult','pro-max-imports'),('CompactPhoneUIResults-imports.xcresult','SE3-imports'),('PadUIResults-layout.xcresult','ipad-pro-13-layout'),('MiniUIResults-layout.xcresult','ipad-mini-layout'),('PadUIResults.xcresult','ipad-pro-13'),('MiniUIResults.xcresult','ipad-mini')]:
 if not pathlib.Path(result,'Info.plist').is_file():
  summary['results'][label]={'not_produced':True};continue
 report=subprocess.run(['xcrun','xcresulttool','get','test-results','summary','--path',result],capture_output=True,text=True)
 summary['results'][label]=json.loads(report.stdout) if report.returncode==0 else {'summary_error':report.stderr}
 folder=pathlib.Path('build/ios-platform-attachments')/label;folder.mkdir(parents=True,exist_ok=True)
 subprocess.run(['xcrun','xcresulttool','export','attachments','--path',result,'--output-path',str(folder)],check=True)
 for entry in records(json.loads((folder/'manifest.json').read_text())):
  text=' '.join(v for v in entry.values() if isinstance(v,str));name=next((n for n in names if n in text),None)
  if not name or 'accessibility' in text:continue
  # Keep the complete largest-size case result, with representative actual
  # result/focus/Chinese pixels inside the unchanged TV evidence allocation.
  if label=='apple-tv-largest' and name not in ['tv-chinese-result','tv-history-focused-delete','tv-real-photo-result','tv-failure']:continue
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
  item={'name':filename,'bytes':len(data),'source_attachment_bytes':source_bytes,'sha256':hashlib.sha256(data).hexdigest()}
  if native_dimensions:item.update(native_pixel_dimensions=native_dimensions,source_bytes_preserved=True)
  summary['screenshots'].append(item);print(json.dumps(item),flush=True)
encoded=json.dumps(summary,indent=2)+'\n'
assert len(encoded.encode())<=(128*1024 if scope.startswith('watchos_') else 512*1024)
(out/'manifest.json').write_text(encoded)
size=sum(p.stat().st_size for p in out.iterdir())
mac=sum(p.stat().st_size for p in pathlib.Path('build/mac-evidence').glob('*') if p.is_file())
print(json.dumps({'ios_evidence_bytes':size,'mac_evidence_bytes':mac,'combined_bytes':size+mac}),flush=True)
assert size<=limit and size+mac<=20_000_000
if summary['omitted']:raise SystemExit('Required named screenshots exceeded the cap; review omitted entries instead of claiming complete visual evidence')
