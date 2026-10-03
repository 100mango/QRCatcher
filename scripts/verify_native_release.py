#!/usr/bin/env python3
"""Read-only unsigned device bundle/weak-link proof; no Store or signing work."""
import argparse,hashlib,json,plistlib,re,subprocess
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('platform',choices=['Watch','TV','Vision']);args=parser.parse_args()
platform=args.platform;name='QRCatcher'+platform
sdk={'Watch':'watchos','TV':'appletvos','Vision':'xros'}[platform]
app=Path('build')/('Release'+platform)/'Build/Products'/('Release-'+sdk)/(name+'.app')
info=plistlib.loads((app/'Info.plist').read_bytes());expected='100mango.QRCatcher.watchkitapp' if platform=='Watch' else '100mango.QRCatcher'
assert info['CFBundleIdentifier']==expected
assert info['CFBundleShortVersionString']=='1.1' and str(info['CFBundleVersion'])=='2'
minimum={'Watch':'9.0','TV':'17.0','Vision':'1.0'}[platform]
assert info['MinimumOSVersion']==minimum,(info['MinimumOSVersion'],minimum)
assert info['UIDeviceFamily']==[{'Watch':4,'TV':3,'Vision':7}[platform]]
privacy=plistlib.loads((app/'PrivacyInfo.xcprivacy').read_bytes())
assert privacy.get('NSPrivacyTracking') is False and privacy.get('NSPrivacyCollectedDataTypes')==[]
required=[{'NSPrivacyAccessedAPIType':'NSPrivacyAccessedAPICategoryUserDefaults','NSPrivacyAccessedAPITypeReasons':['CA92.1']}] if platform=='TV' else []
assert privacy['NSPrivacyAccessedAPITypes']==required
icons={k:info[k] for k in ['CFBundleIcons','CFBundleIconName','CFBundleIconFiles'] if k in info}
assert 'AppIcon' in json.dumps(icons),icons
assert (app/'Assets.car').stat().st_size>0
executable=app/info['CFBundleExecutable'];data=executable.read_bytes()
strings=subprocess.check_output(['strings',str(executable)],text=True)
for marker in ['QRCATCHER_TEST_STORE','QRCATCHER_SANDBOX_','QRCATCHER_TV_TEST_STORE','QRCATCHER_WATCH_STORE','fixture-payload','reset-history']:
 assert marker not in strings,(platform,marker)
assert not list(app.rglob('*.xctest'))
archs=subprocess.check_output(['xcrun','lipo','-archs',str(executable)],text=True).strip().split()
load=subprocess.check_output(['xcrun','otool','-l',str(executable)],text=True)
report={'platform':platform,'bundle':str(app),'bundle_id':expected,'minimum_os':minimum,'version':'1.1','build':'2','architectures':archs,'executable_sha256':hashlib.sha256(data).hexdigest(),'icons':icons,'privacy':privacy,'assets_car_sha256':hashlib.sha256((app/'Assets.car').read_bytes()).hexdigest()}
if platform=='Watch':
 chunks=re.split(r'Load command \d+',load)
 vision=[chunk for chunk in chunks if '/Vision.framework/Vision ' in chunk]
 assert vision,'Expected Watch27 decoder to reference Vision'
 assert all('LC_LOAD_WEAK_DYLIB' in chunk and 'LC_LOAD_DYLIB\n' not in chunk for chunk in vision),vision
 report['vision_load_commands']=[{'weak':True,'details':chunk.strip()} for chunk in vision]
 report['older_runtime_launch']='not yet executed; static weak link is not runtime proof'
# Record bounded catalog metadata; exact source artwork derivation is separately
# SHA-checked and its rendered pixels inspected in CI evidence.
assets=json.loads(subprocess.check_output(['xcrun','assetutil','--info',str(app/'Assets.car')],text=True))
report['icon_catalog_entries']=[{k:v for k,v in entry.items() if k in ['Name','AssetType','PixelWidth','PixelHeight','Scale','Idiom']} for entry in assets if 'icon' in str(entry.get('Name','')).lower()][:50]
assert report['icon_catalog_entries'],'Compiled catalog lacks identified app-icon entries'
out=Path('build/native-release-evidence');out.mkdir(parents=True,exist_ok=True)
encoded=json.dumps(report,indent=2)+'\n';assert len(encoded.encode())<64*1024
(out/(platform.lower()+'-release.json')).write_text(encoded);print(encoded,flush=True)
