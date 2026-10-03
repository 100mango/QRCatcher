#!/usr/bin/env python3
"""Read-only SDK typecheck experiment. Success is not app or runtime validation."""
import hashlib, json, pathlib, platform, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parent
arch=platform.machine()
if arch not in ('arm64','x86_64'): raise SystemExit('Unexpected runner architecture: '+arch)
probes=[
 ('watch-new-vision-floor9','watchsimulator',f'{arch}-apple-watchos9.0-simulator','watch-vision.swift'),
 ('watch-new-vision27','watchsimulator',f'{arch}-apple-watchos27.0-simulator','watch-vision.swift'),
 ('watch-photo-and-sampling','watchsimulator',f'{arch}-apple-watchos9.0-simulator','watch-local.swift'),
 ('watch-legacy-vision','watchsimulator',f'{arch}-apple-watchos27.0-simulator','watch-old-vision.swift'),
 ('watch-coreimage','watchsimulator',f'{arch}-apple-watchos27.0-simulator','watch-coreimage.swift'),
 ('tvos-photokit-write-symbols','appletvsimulator',f'{arch}-apple-tvos17.0-simulator','tv-photos.swift'),
 ('tvos-continuity-camera','appletvsimulator',f'{arch}-apple-tvos17.0-simulator','tv-camera.swift'),
 ('tvos-metadata-output','appletvsimulator',f'{arch}-apple-tvos17.0-simulator','tv-metadata.swift'),
 ('native-vision-image','xrsimulator',f'{arch}-apple-xros1.0-simulator','native-vision.swift'),
 ('native-vision-consumer-capture','xrsimulator',f'{arch}-apple-xros27.0-simulator','vision-capture.swift'),
 ('native-vision-continuity-type','xrsimulator',f'{arch}-apple-xros27.0-simulator','vision-continuity.swift'),
 ('native-mac-desktop-photos','macosx',f'{arch}-apple-macosx13.0','native-mac.swift'),
]
results=[]
for name,sdk,target,source in probes:
    sdkpath=subprocess.check_output(['xcrun','--sdk',sdk,'--show-sdk-path'],text=True).strip()
    cmd=['xcrun','--sdk',sdk,'swiftc','-typecheck','-swift-version','5','-sdk',sdkpath,'-target',target,str(ROOT/source)]
    print('\n=== PROBE '+name+' ===\n'+json.dumps({'command':cmd,'source_sha256':hashlib.sha256((ROOT/source).read_bytes()).hexdigest()}),flush=True)
    try:
        r=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
        print(r.stdout,flush=True); status='accepted' if r.returncode==0 else 'rejected'
        record={'name':name,'sdk':sdk,'target':target,'status':status,'exit_code':r.returncode}
    except subprocess.TimeoutExpired as e:
        output=e.stdout or b''; print(output.decode(errors='replace') if isinstance(output,bytes) else output,flush=True)
        record={'name':name,'sdk':sdk,'target':target,'status':'typecheck_timeout'}
    results.append(record); print('PROBE_RESULT '+json.dumps(record),flush=True)
print('\nTYPECHECK_SUMMARY '+json.dumps(results),flush=True)
print('SCOPE: symbol/typecheck evidence only; no app build, linking, simulator UI, actual image decode, PhotoKit write, camera, transfer, signing or Store claim.')
