#!/usr/bin/env python3
"""Converge compiler and embedding failures before any long simulator matrix."""
import json,time
from pathlib import Path
from atomic_json import write_json
from watch_process import execute
from owned_process_barrier import mark_unconfirmed

SCHEMES=[
    ('QRCatcher','build/iOS','generic/platform=iOS Simulator'),
    ('QRCatcherMac','build/MacTests','platform=macOS,arch=arm64'),
    ('QRCatcherMacSandbox','build/MacSandbox','platform=macOS,arch=arm64'),
    ('QRCatcherWatch','build/WatchTests','generic/platform=watchOS Simulator'),
    ('QRCatcherVision','build/VisionTests','generic/platform=visionOS Simulator'),
    ('QRCatcherTV','build/TVTests','generic/platform=tvOS Simulator'),
]

def main():
    root=Path('build/preflight');root.mkdir(parents=True,exist_ok=True)
    report={'scope':'unsigned compilation and exact Debug embedding only; zero runtime tests','operations':[]}
    started=time.monotonic();failed=False
    def run(label,args,cap):
        if report.get('cleanup_unconfirmed'):
            report['operations'].append({'label':label,'state':'blocked_owned_process_cleanup_unconfirmed'})
            write_json(root/'summary.json',report);return 126
        remaining=900-(time.monotonic()-started)
        if remaining<=0:
            report['operations'].append({'label':label,'state':'not_run_total_preflight_deadline'})
            write_json(root/'summary.json',report);return 124
        print('PLATFORM_PREFLIGHT_START '+json.dumps({'label':label,'command':args}),flush=True)
        code,tail,operation=execute(args,min(cap,remaining),output_limit=16*1024*1024,tail_limit=16*1024)
        (root/(label+'.log')).write_text(tail)
        report['operations'].append({'label':label,**operation});write_json(root/'summary.json',report)
        if code==126 or operation.get('cleanup_confirmed') is not True:
            report['cleanup_unconfirmed']=True;mark_unconfirmed(operation);write_json(root/'summary.json',report);return 126
        print('PLATFORM_PREFLIGHT_END '+json.dumps(report['operations'][-1]),flush=True)
        return code
    for scheme,derived,destination in SCHEMES:
        command=['xcodebuild','build-for-testing','-project','QRCatcher.xcodeproj','-scheme',scheme,
                 '-configuration','Debug','-derivedDataPath',derived,'-destination',destination,
                 '-jobs','2','ARCHS=arm64','CODE_SIGNING_ALLOWED=NO']
        code=run(scheme,command,180);failed|=code!=0
        if scheme=='QRCatcher' and code==0:
            failed|=run('ios-embedded-watch',['python3','scripts/verify_embedded_watch.py','simulator'],45)!=0
    report['passed']=not failed;write_json(root/'summary.json',report)
    print(json.dumps(report),flush=True)
    if failed:raise SystemExit('Compiler/setup preflight failed; dependent runtime matrix must not start')
if __name__=='__main__':main()
