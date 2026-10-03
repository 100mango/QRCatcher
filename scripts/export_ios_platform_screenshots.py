#!/usr/bin/env python3
"""Bounded synthetic phone/iPad evidence. Never uploads full xcresult archives."""
import hashlib,json,os,pathlib,subprocess
scope=os.environ['EVIDENCE_SCOPE']
limit=json.loads(pathlib.Path('scripts/evidence-allocation.json').read_text())['scope_limits_bytes'][scope]
out=pathlib.Path('build/ios-platform-evidence');out.mkdir(parents=True,exist_ok=True)
summary={'scope':scope,'scope_limit_bytes':limit,'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),'run_id':os.environ.get('GITHUB_RUN_ID'),'screenshots':[],'omitted':[],'results':{}}
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
for name in ['release-watch.log','release-tv.log','release-vision.log','watch-test-build.log','watch-unit.log','watch-ui.log','tv-test-build.log','tv-test.log','tv-authorized-test.log','tv-revoked-test.log','vision-test-build.log','vision-test.log','vision-ui-test.log','ios-test-build.log','ios-unit.log','PhoneUIResults.log','CompactPhoneUIResults.log','PadUIResults.log','MiniUIResults.log']:
 path=pathlib.Path(name)
 if path.is_file():(out/name).write_bytes(path.read_bytes()[-64*1024:])
names=('tv-history-focused-record','tv-history-focused-delete','tv-history-list','tv-offline-policy','tv-chinese-result','watch-recovered-journal','phone-failure','tv-revoked-photos','watch-empty','watch-offline-policy','watch-fixture-offline-result','watch-system-picker-unavailable','watch-reopened-qr','watch-failure','tv-real-photo-result','tv-verified-photos-output','tv-reopened-history','tv-failure','vision-imported-qr','vision-reopened-history','vision-failure','synthetic-scan-result','synthetic-history','privacy-open-diagnostic','privacy-return-diagnostic','ipad-anchored-share','ipad-split-portrait','ipad-large-text','ipad-imported-photo','ipad-failure','view-layout-320x568-largest-text','view-layout-568x320-largest-text')
def records(value):
 if isinstance(value,dict):
  if 'exportedFileName' in value:yield value
  for child in value.values():yield from records(child)
 elif isinstance(value,list):
  for child in value:yield from records(child)
for result,label in [('WatchUnitResults.xcresult','watch-unit'),('WatchUIResults.xcresult','watch-ui'),('TVTestResults.xcresult','apple-tv'),('TVAuthorizedUIResults.xcresult','apple-tv-pregranted'),('TVRevokedUIResults.xcresult','apple-tv-revoked'),('VisionTestResults.xcresult','vision-pro-unit'),('VisionUIResults.xcresult','vision-pro-ui'),('iOSUnitResults.xcresult','view-layout-host'),('PhoneUIResults.xcresult','pro-max'),('CompactPhoneUIResults.xcresult','SE3'),('PadUIResults.xcresult','ipad-pro-13'),('MiniUIResults.xcresult','ipad-mini')]:
 if not pathlib.Path(result,'Info.plist').is_file():
  summary['results'][label]={'not_produced':True};continue
 report=subprocess.run(['xcrun','xcresulttool','get','test-results','summary','--path',result],capture_output=True,text=True)
 summary['results'][label]=json.loads(report.stdout) if report.returncode==0 else {'summary_error':report.stderr}
 folder=pathlib.Path('build/ios-platform-attachments')/label;folder.mkdir(parents=True,exist_ok=True)
 subprocess.run(['xcrun','xcresulttool','export','attachments','--path',result,'--output-path',str(folder)],check=True)
 for entry in records(json.loads((folder/'manifest.json').read_text())):
  text=' '.join(v for v in entry.values() if isinstance(v,str));name=next((n for n in names if n in text),None)
  if not name or 'accessibility' in text:continue
  path=(folder/entry['exportedFileName']).resolve();assert path.is_relative_to(folder.resolve())
  data=path.read_bytes()
  source_bytes=len(data)
  if data.startswith(b'\x89PNG'):
   converted=path.with_suffix('.bounded.jpg')
   subprocess.run(['sips','-s','format','jpeg','-s','formatOptions','55','-Z','1440',str(path),'--out',str(converted)],check=True,capture_output=True)
   data=converted.read_bytes()
  elif label.startswith('apple-tv') and data.startswith(b'\xff\xd8'):
   # Preserve the whole actual TV frame, but bound its long edge so the enlarged
   # focus/localization/policy set fits this platform's fixed artifact allocation.
   converted=path.with_suffix('.bounded.jpg')
   subprocess.run(['sips','-s','format','jpeg','-s','formatOptions','50','-Z','1920',str(path),'--out',str(converted)],check=True,capture_output=True,timeout=30)
   data=converted.read_bytes()
  assert data.startswith(b'\xff\xd8') and len(data)<=800*1024,'Invalid or oversized synthetic screenshot'
  filename=f'{label}-{name}-{len(summary["screenshots"])+1}.jpg'
  # Reserve 512 KiB for structured summaries, keeping the entire artifact <=6 MiB.
  used=sum(p.stat().st_size for p in out.iterdir())
  if used+len(data)>limit-512*1024 or len(summary['screenshots'])>=28:
   summary['omitted'].append({'name':filename,'reason':'bounded evidence cap'});print('OMITTED_AT_CAP',filename,flush=True);continue
  (out/filename).write_bytes(data)
  item={'name':filename,'bytes':len(data),'source_attachment_bytes':source_bytes,'sha256':hashlib.sha256(data).hexdigest()};summary['screenshots'].append(item);print(json.dumps(item),flush=True)
(out/'manifest.json').write_text(json.dumps(summary,indent=2)+'\n')
size=sum(p.stat().st_size for p in out.iterdir())
mac=sum(p.stat().st_size for p in pathlib.Path('build/mac-evidence').glob('*') if p.is_file())
print(json.dumps({'ios_evidence_bytes':size,'mac_evidence_bytes':mac,'combined_bytes':size+mac}),flush=True)
assert size<=limit and size+mac<=20_000_000
if summary['omitted']:raise SystemExit('Required named screenshots exceeded the cap; review omitted entries instead of claiming complete visual evidence')
