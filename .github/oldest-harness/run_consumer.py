#!/usr/bin/env python3
"""Run one unchanged SDK27-built Release app on an exact older iOS runtime.

Local preparation. Requires an already installed official iOS15.5 runtime and
fresh hosted macOS26 VM. App source is never compiled here. No credentials.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from build_release import ALLOWED, bounded_build, checked_sources, output
from bundle_archive import unpack, verify_directory
from runtime_gate import select_runtime, validate_provenance, verify_installed_app
from runner_binary_gate import verify_runner_products

TESTS = {
    'TouchColor': 'testTouchColorReleasePhotoPersistence',
    'QRCatcher': 'testQRCatcherReleaseDecodePersistence',
    'Celluloid': 'testCelluloidReleaseEditSaveReopen',
}


def checked_host():
    # An accidental-execution guard, not an authentication or isolation boundary.
    if any(os.environ.get(k) != v for k, v in {'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'macOS'}.items()):
        raise ValueError('This runtime gate is only prepared for a disposable hosted macOS VM')
    if output(['xcodebuild','-version']).splitlines() != ['Xcode 26.6','Build version 17F113']:
        raise ValueError('Exact older UI-runner toolchain required')
    if output(['sw_vers','-productVersion']).split('.')[0] != '26' or output(['uname','-m']) != 'arm64':
        raise ValueError('Exact supported host family and arm64 required')
    print('CONSUMER_HOST',output(['sw_vers']),output(['xcodebuild','-version']),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--archive-sha256',required=True)
    parser.add_argument('--app',choices=sorted(ALLOWED),required=True)
    parser.add_argument('--device',choices=['iPhone SE (1st generation)','iPad mini 4'],required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--fixture-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    checked_host()
    rows=checked_sources(args.sources)
    if not re.fullmatch('[0-9a-f]{64}',args.fixture_sha256):
        raise ValueError('Exact fixture digest required')
    import hashlib
    if args.fixture.is_symlink() or not args.fixture.is_file() or args.fixture.stat().st_size > 1_000_000 or hashlib.sha256(args.fixture.read_bytes()).hexdigest()!=args.fixture_sha256:
        raise ValueError('Synthetic fixture differs or exceeds its bound')
    args.output.mkdir(parents=False,exist_ok=False)
    root=args.output/'unchanged-apps'
    manifest=unpack(args.archive,args.archive_sha256,root)
    provenances=validate_provenance(manifest,rows)
    runtime,device=select_runtime(json.loads(output(['xcrun','simctl','list','runtimes','-j'])),args.device)
    runner_source=Path(__file__).resolve().parent
    derived=args.output/'runner-build'
    # This project contains only the dummy test host and black-box UI bundle.
    # None of the three product projects appears in this command or checkout.
    bounded_build(['xcodebuild','build-for-testing','-project','LegacyRuntime.xcodeproj','-scheme','LegacyRuntime','-configuration','Debug','-sdk','iphonesimulator','-destination','generic/platform=iOS Simulator','-derivedDataPath',str(derived),'CODE_SIGNING_ALLOWED=NO','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES'],runner_source,args.output/'runner-build.log',600)
    runner_binaries=verify_runner_products(derived/'Build/Products/Debug-iphonesimulator')
    (args.output/'runner-binary-floors.json').write_text(json.dumps(runner_binaries,indent=2)+'\n')
    print('OLDER_XCTEST_ACTUAL_BINARY_FLOORS',json.dumps(runner_binaries,sort_keys=True),flush=True)
    verify_directory(root,manifest)
    simulator=output(['xcrun','simctl','create','SDK27 binary compatibility '+args.app,device,runtime])
    if not re.fullmatch('[0-9A-Fa-f-]{36}',simulator):
        raise ValueError('Unexpected simulator creation result')
    (args.output/'simulator.json').write_text(json.dumps({'id':simulator,'device':args.device,'runtime':runtime,'app':args.app})+'\n')
    def command(name,argv,seconds):bounded_build(argv,runner_source,args.output/(name+'.log'),seconds)
    installed=None
    try:
        command('boot',['xcrun','simctl','boot',simulator],60)
        command('bootstatus',['xcrun','simctl','bootstatus',simulator,'-b'],480)
        command('install',['xcrun','simctl','install',simulator,str(root/(args.app+'.app'))],120)
        installed=Path(output(['xcrun','simctl','get_app_container',simulator,ALLOWED[args.app][3],'app']))
        print('INSTALLED_BEFORE',json.dumps(verify_installed_app(installed,args.app,manifest,provenances[args.app]),sort_keys=True),flush=True)
        command('fixture',['xcrun','simctl','addmedia',simulator,str(args.fixture)],150)
        # Permission transitions are handled by actual XCTest system-alert taps;
        # a simctl pre-grant must not be described as user-consent coverage.
        command('ui',['xcodebuild','test-without-building','-project','LegacyRuntime.xcodeproj','-scheme','LegacyRuntime','-configuration','Debug','-derivedDataPath',str(derived),'-destination','platform=iOS Simulator,id='+simulator,'-only-testing:LegacyRuntimeTests/OldRuntimeAppTests/'+TESTS[args.app],'-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','240','-maximum-test-execution-time-allowance','300','-resultBundlePath',str(args.output/'UI.xcresult'),'CODE_SIGNING_ALLOWED=NO'],600)
    finally:
        # Always retain app hashes even after a failing UI case. No app data is
        # read or uploaded; only product files produced by the SDK27 job.
        try:
            verify_directory(root,manifest)
            if installed is not None:
                print('INSTALLED_AFTER',json.dumps(verify_installed_app(installed,args.app,manifest,provenances[args.app]),sort_keys=True),flush=True)
        finally:
            # Shut down only this newly created test simulator. No global erase,
            # deletion, daemon reset or other user's machine can be targeted.
            try:command('shutdown',['xcrun','simctl','shutdown',simulator],60)
            except (subprocess.SubprocessError,OSError) as error:print('SHUTDOWN_DIAGNOSTIC',type(error).__name__,flush=True)


if __name__=='__main__':main()
