#!/usr/bin/env python3
"""Read-only unsigned device bundle/weak-link proof; no Store or signing work."""
import argparse,hashlib,json,plistlib,re,subprocess
from pathlib import Path
from required_reason_symbols import inspect_file_reader_imports
parser=argparse.ArgumentParser();parser.add_argument('platform',choices=['Watch','TV','Vision']);args=parser.parse_args()
platform=args.platform;name='QRCatcher'+platform
sdk={'Watch':'watchos','TV':'appletvos','Vision':'xros'}[platform]
app=Path('build')/('Release'+platform)/'Build/Products'/('Release-'+sdk)/(name+'.app')
info=plistlib.loads((app/'Info.plist').read_bytes());expected='100mango.QRCatcher.watchkitapp' if platform=='Watch' else '100mango.QRCatcher'
assert info['CFBundleIdentifier']==expected
if platform!='Vision':assert 'UIFileSharingEnabled' not in info and 'LSSupportsOpeningDocumentsInPlace' not in info
assert info['CFBundleShortVersionString']=='1.1' and str(info['CFBundleVersion'])=='2'
minimum={'Watch':'9.0','TV':'17.0','Vision':'1.0'}[platform]
assert info['MinimumOSVersion']==minimum,(info['MinimumOSVersion'],minimum)
assert info['UIDeviceFamily']==[{'Watch':4,'TV':3,'Vision':7}[platform]]
privacy=plistlib.loads((app/'PrivacyInfo.xcprivacy').read_bytes())
assert privacy.get('NSPrivacyTracking') is False and privacy.get('NSPrivacyCollectedDataTypes')==[]
required=[{'NSPrivacyAccessedAPIType':'NSPrivacyAccessedAPICategoryUserDefaults','NSPrivacyAccessedAPITypeReasons':['CA92.1']}] if platform=='TV' else ([{'NSPrivacyAccessedAPIType':'NSPrivacyAccessedAPICategoryFileTimestamp','NSPrivacyAccessedAPITypeReasons':['C617.1','3B52.1']}] if platform=='Vision' else [])
assert privacy['NSPrivacyAccessedAPITypes']==required
icons={k:info[k] for k in ['CFBundleIcons','CFBundleIconName','CFBundleIconFiles'] if k in info}
expected_icon='Small' if platform=='TV' else 'AppIcon'
assert expected_icon in json.dumps(icons),icons
assert (app/'Assets.car').stat().st_size>0
executable=app/info['CFBundleExecutable'];data=executable.read_bytes()
strings=subprocess.check_output(['strings',str(executable)],text=True)
for marker in ['QRCATCHER_TEST_STORE','QRCATCHER_SANDBOX_','QRCATCHER_TV_TEST_STORE','QRCATCHER_WATCH_STORE','QRCATCHER_WATCH_LAYOUT_STRESS','QRCATCHER_WATCH_LAYOUT_PROBE','QRCATCHER_TV_LAYOUT_STRESS','QRCATCHER_TV_LAYOUT_PROBE','fixture-payload','reset-history','QRCatcherExportTestReceipts','Export readback verification failed']:
 assert marker not in strings,(platform,marker)
assert not list(app.rglob('*.xctest'))
archs=subprocess.check_output(['xcrun','lipo','-archs',str(executable)],text=True).strip().split()
load=subprocess.check_output(['xcrun','otool','-l',str(executable)],text=True)
reader_symbols=inspect_file_reader_imports(executable,platform=='Vision')
report={'platform':platform,'actual_file_metadata_imports':reader_symbols,'bundle':str(app),'bundle_id':expected,'minimum_os':minimum,'version':'1.1','build':'2','architectures':archs,'executable_bytes':len(data),'executable_sha256':hashlib.sha256(data).hexdigest(),'icons':icons,'privacy':privacy,'assets_car_sha256':hashlib.sha256((app/'Assets.car').read_bytes()).hexdigest()}
report['architecture_minimum_os']={}
for arch in archs:
 slice_load=subprocess.check_output(['xcrun','otool','-arch',arch,'-l',str(executable)],text=True)
 match=re.search(r'cmd LC_BUILD_VERSION\b(?:(?!Load command).)*?\bminos ([0-9.]+)',slice_load,re.S)
 assert match,arch
 report['architecture_minimum_os'][arch]=match.group(1)
if platform!='Watch':
 assert all(value==minimum for value in report['architecture_minimum_os'].values())
 report['oldest_runtime_launch']='not yet executed; unsigned bundle/load-command checks are not runtime proof'
if platform=='Watch':
 assert set(archs)>={'arm64_32','arm64'},archs
 # Native arm64 Watch executables were introduced with watchOS 26. The older
 # arm64_32 slice must preserve the application's declared watchOS 9 floor.
 assert report['architecture_minimum_os']['arm64_32']=='9.0'
 assert report['architecture_minimum_os']['arm64']=='26.0'
 assert '/Vision.framework/Vision' not in load,'Portable Watch Release must not load the failed Vision model path'
 assert '/CoreML.framework/' not in load
 report['decoder']='Pinned QR-only ZXing-C++ CPU path; no Vision/CoreML framework dependency'
 report['older_runtime_launch']='not yet executed; device arm64/arm64_32 packaging is not runtime proof'
 notice=app/'ThirdPartyNotices.txt';assert notice.is_file() and 'Apache License' in notice.read_text()
 report['third_party_notices_sha256']=hashlib.sha256(notice.read_bytes()).hexdigest()
 assert notice.read_bytes()==Path('ThirdParty/ZXingCpp/ThirdPartyNotices.txt').read_bytes()
 report['portable_source_commit']='287c85df6f961c8efbfb5ffd736cd9457b8b890e'
# Record bounded catalog metadata; exact source artwork derivation is separately
# SHA-checked and its rendered pixels inspected in CI evidence.
assets=json.loads(subprocess.check_output(['xcrun','assetutil','--info',str(app/'Assets.car')],text=True))
report['icon_catalog_entries']=[{k:v for k,v in entry.items() if k in ['Name','AssetType','PixelWidth','PixelHeight','Scale','Idiom']} for entry in assets if ('icon' in str(entry.get('Name','')).lower() or (platform=='TV' and str(entry.get('Name','')).split('/')[0] in ['Small','Large']))][:50]
assert report['icon_catalog_entries'],'Compiled catalog lacks identified app-icon entries'
out=Path('build/native-release-evidence');out.mkdir(parents=True,exist_ok=True)
encoded=json.dumps(report,indent=2)+'\n';assert len(encoded.encode())<64*1024
(out/(platform.lower()+'-release.json')).write_text(encoded);print(encoded,flush=True)
