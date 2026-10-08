#!/usr/bin/env python3
"""Inspect the real iOS product's nested Watch app, not a standalone substitute."""
import hashlib,json,plistlib,re,subprocess,sys,tempfile
from pathlib import Path
kind=sys.argv[1];assert kind in ['device','simulator']
configuration='Release' if kind=='device' else 'Debug'
phone_sdk='iphoneos' if kind=='device' else 'iphonesimulator'
watch_sdk='watchos' if kind=='device' else 'watchsimulator'
products=Path('build/iOS/Build/Products')
parent=products/(configuration+'-'+phone_sdk)/'QRCatcher.app'
watch=parent/'Watch/QRCatcherWatch.app'
producer=products/(configuration+'-'+watch_sdk)/'QRCatcherWatch.app'
parent_info=plistlib.loads((parent/'Info.plist').read_bytes());info=plistlib.loads((watch/'Info.plist').read_bytes())
assert parent_info['CFBundleIdentifier']=='100mango.QRCatcher'
assert info['CFBundleIdentifier']=='100mango.QRCatcher.watchkitapp'
assert info['WKCompanionAppBundleIdentifier']==parent_info['CFBundleIdentifier']
assert info['WKApplication'] is True and info['WKRunsIndependentlyOfCompanionApp'] is True
for key in ['CFBundleShortVersionString','CFBundleVersion']:assert str(info[key])==str(parent_info[key]),key
assert info['MinimumOSVersion']=='9.0' and info['UIDeviceFamily']==[4]
assert info['CFBundleSupportedPlatforms']==(['WatchOS'] if kind=='device' else ['WatchSimulator'])
assert plistlib.loads((producer/'Info.plist').read_bytes())==info
privacy=plistlib.loads((watch/'PrivacyInfo.xcprivacy').read_bytes())
assert privacy['NSPrivacyAccessedAPITypes']==[] and privacy['NSPrivacyCollectedDataTypes']==[] and privacy['NSPrivacyTracking'] is False
assert (watch/'ThirdPartyNotices.txt').read_bytes()==Path('ThirdParty/ZXingCpp/ThirdPartyNotices.txt').read_bytes()
assert (watch/'Assets.car').is_file()
icons={key:info[key] for key in ['CFBundleIcons','CFBundleIconName','CFBundleIconFiles'] if key in info}
assert 'AppIcon' in json.dumps(icons),icons
def inventory(root):
    result={}
    for file in sorted(root.rglob('*')):
        assert not file.is_symlink()
        if file.is_file():
            assert file.stat().st_size<=20*1024*1024
            result[str(file.relative_to(root))]=hashlib.sha256(file.read_bytes()).hexdigest()
            assert len(result)<=256
    return result
nested_files=inventory(watch);producer_files=inventory(producer)
assert set(nested_files)==set(producer_files),'Embedded bundle file set changed'
assert info['CFBundleExecutable']=='QRCatcherWatch'
changed=[p for p in sorted(nested_files) if nested_files[p]!=producer_files[p]]
copy_transform='exact'
if changed:
    # Xcode 27's actual Release copy in run 37176649273 invokes this precise
    # deterministic strip command. Compare its output bytes, never accept an
    # arbitrary executable mismatch or exclude the executable from provenance.
    assert kind=='device' and changed==['QRCatcherWatch'],{'changed':changed}
    with tempfile.TemporaryDirectory(prefix='QRCatcherEmbeddedWatch-') as folder:
        normalized=Path(folder)/'QRCatcherWatch'
        subprocess.check_output(['xcrun','strip','-D','-S','-no_atom_info',str(producer/'QRCatcherWatch'),'-o',str(normalized)],text=True,timeout=30)
        assert normalized.is_file() and not normalized.is_symlink() and normalized.stat().st_size<=20*1024*1024
        expected_hash=hashlib.sha256(normalized.read_bytes()).hexdigest()
        assert nested_files['QRCatcherWatch']==expected_hash,'Embedded executable differs from the observed deterministic copy transform'
    copy_transform='strip -D -S -no_atom_info'
executable=watch/info['CFBundleExecutable']
architectures=subprocess.check_output(['xcrun','lipo','-archs',str(executable)],text=True,timeout=30).split()
assert set(architectures)==({'arm64','arm64_32'} if kind=='device' else {'arm64'}),architectures
minimums={};platforms={}
for arch in architectures:
    load=subprocess.check_output(['xcrun','otool','-arch',arch,'-l',str(executable)],text=True,timeout=30)
    match=re.search(r'cmd LC_BUILD_VERSION\b(?:(?!Load command).)*?\bplatform (\S+)(?:(?!Load command).)*?\bminos ([0-9.]+)',load,re.S)
    assert match,(arch,'missing load command')
    platforms[arch]=match.group(1);minimums[arch]=match.group(2)
    assert match.group(1).lower() in (['4','watchos'] if kind=='device' else ['9','watchossimulator']),platforms
if kind=='device':
    assert minimums=={'arm64':'26.0','arm64_32':'9.0'},minimums
    strings=subprocess.check_output(['strings',str(executable)],text=True,timeout=30)
    for marker in ['QRCATCHER_WATCH_STORE','fixture-payload','reset-history']:assert marker not in strings
    linked=subprocess.check_output(['xcrun','otool','-L',str(executable)],text=True,timeout=30)
    assert '/Vision.framework/' not in linked and '/CoreML.framework/' not in linked
report={'parent':str(parent),'nested':str(watch),'producer':str(producer),'kind':kind,
        'producer_bundle_bytes_match':not changed,'producer_bundle_matches_observed_copy':True,
        'producer_executable_transform':copy_transform,'producer_executable_sha256':producer_files['QRCatcherWatch'],
        'bundle_id':info['CFBundleIdentifier'],'companion':info['WKCompanionAppBundleIdentifier'],
        'version':info['CFBundleShortVersionString'],'build':str(info['CFBundleVersion']),
        'architectures':architectures,'architecture_minimum_os':minimums,'mach_o_platforms':platforms,
        'executable_bytes':executable.stat().st_size,'executable_sha256':nested_files[info['CFBundleExecutable']],
        'privacy':privacy,'icons':icons,'third_party_notices_sha256':nested_files['ThirdPartyNotices.txt']}
out=Path('build/native-release-evidence');out.mkdir(exist_ok=True,parents=True)
encoded=json.dumps(report,indent=2)+'\n';assert len(encoded.encode())<16*1024
(out/('ios-embedded-watch-'+kind+'.json')).write_text(encoded);print(encoded,flush=True)
