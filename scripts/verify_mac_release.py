#!/usr/bin/env python3
"""Inspect the actual unsigned universal Mac product; do not infer its floor."""
import hashlib,json,plistlib,re,subprocess
from pathlib import Path
from required_reason_symbols import inspect_file_reader_imports
app=Path('build/MacRelease/Build/Products/Release/QRCatcherMac.app')
info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
assert info['CFBundleIdentifier']=='100mango.QRCatcher'
assert info['CFBundleShortVersionString']=='1.1' and str(info['CFBundleVersion'])=='2'
assert info['LSMinimumSystemVersion']=='13.0'
executable=app/'Contents/MacOS'/info['CFBundleExecutable']
archs=subprocess.check_output(['xcrun','lipo','-archs',str(executable)],text=True,timeout=30).split()
assert set(archs)=={'arm64','x86_64'}
reader_symbols=inspect_file_reader_imports(executable,True)
strings=subprocess.check_output(['strings',str(executable)],text=True,timeout=30)
for marker in ['QRCATCHER_MAC_PUBLIC_METADATA_', 'QRCatcher.MacPublicMetadata.', 'org.qrcatcher.mac-public-metadata.', 'MacAuditPublicMetadataObserver', 'MAC_PUBLIC_METADATA_']:
    if marker in strings:raise ValueError('Debug public-metadata observer leaked into Mac Release: '+marker)
minima={}
for arch in archs:
    load=subprocess.check_output(['xcrun','otool','-arch',arch,'-l',str(executable)],text=True,timeout=30)
    match=re.search(r'cmd LC_BUILD_VERSION\b(?:(?!Load command).)*?\bminos ([0-9.]+)',load,re.S)
    assert match and match.group(1)=='13.0',(arch,match.group(1) if match else None)
    minima[arch]=match.group(1)
report={'platform':'Mac','bundle_id':info['CFBundleIdentifier'],'version':info['CFBundleShortVersionString'],'build':str(info['CFBundleVersion']),
        'actual_file_metadata_imports':reader_symbols,'minimum_os':info['LSMinimumSystemVersion'],'architecture_minimum_os':minima,
        'executable_bytes':executable.stat().st_size,'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
        'runtime_scope':'Current arm64 macOS27 only; minimum-floor and x86_64 runtime remain separate gates'}
encoded=json.dumps(report,indent=2)+'\n';assert len(encoded.encode())<8192
out=Path('build/native-release-evidence');out.mkdir(parents=True,exist_ok=True)
(out/'mac-release.json').write_text(encoded);print(encoded,flush=True)
