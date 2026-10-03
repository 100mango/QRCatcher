#!/usr/bin/env python3
"""One bounded old-runtime runner feasibility probe. No product app is built."""
import json
import os
from pathlib import Path
import re
import sys
from build_release import bounded_build, output
from run_consumer import checked_host
from runtime_gate import select_runtime
from runner_binary_gate import verify_runner_products

root=Path(__file__).resolve().parent
out=Path(os.environ['RUNNER_TEMP'])/'oldest-harness-probe'
checked_host(); out.mkdir(exist_ok=False)
bounded_build([sys.executable,str(root/'install_official_runtime.py'),'--output',str(out/'runtime-install')],root,out/'official-install.log',1350)
derived=out/'runner-build'
bounded_build(['xcodebuild','build-for-testing','-project','LegacyRuntime.xcodeproj','-scheme','LegacyRuntime','-configuration','Debug','-sdk','iphonesimulator','-destination','generic/platform=iOS Simulator','-derivedDataPath',str(derived),'CODE_SIGNING_ALLOWED=NO','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','-jobs','2'],root,out/'build.log',480)
floors=verify_runner_products(derived/'Build/Products/Debug-iphonesimulator')
print('ACTUAL_OLDER_XCTEST_BINARY_FLOORS',json.dumps(floors,sort_keys=True),flush=True)
inventory=json.loads(output(['xcrun','simctl','list','runtimes','-j']))
results=[]
for number,name in enumerate(['iPhone SE (1st generation)','iPad mini 4']):
    runtime,device=select_runtime(inventory,name)
    sid=output(['xcrun','simctl','create','Oldest XCTest harness '+str(number),device,runtime])
    if not re.fullmatch(r'[0-9a-fA-F-]{36}',sid):raise ValueError('Invalid owned simulator identifier')
    def run(label,command,seconds): bounded_build(command,root,out/(str(number)+'-'+label+'.log'),seconds)
    try:
        run('boot',['xcrun','simctl','boot',sid],60)
        run('bootstatus',['xcrun','simctl','bootstatus',sid,'-b'],300)
        bundle=out/('Smoke-'+str(number)+'.xcresult')
        run('test',['xcodebuild','test-without-building','-project','LegacyRuntime.xcodeproj','-scheme','LegacyRuntime','-configuration','Debug','-derivedDataPath',str(derived),'-destination','platform=iOS Simulator,id='+sid,'-only-testing:LegacyRuntimeTests/OldRuntimeAppTests/testHarnessWindow','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','180','-maximum-test-execution-time-allowance','240','-resultBundlePath',str(bundle),'CODE_SIGNING_ALLOWED=NO'],360)
        summary=json.loads(output(['xcrun','xcresulttool','get','test-results','summary','--path',str(bundle)]))
        if summary.get('totalTestCount')!=1 or summary.get('passedTests')!=1 or summary.get('failedTests')!=0:raise ValueError('Harness smoke was not one actual passing test')
        result={'device':name,'runtime':runtime,'build':'19F70','harness_tests_passed':1,'product_app_tests':0}
        results.append(result); print('OLDEST_HARNESS_RESULT',json.dumps(result),flush=True)
    finally:
        try:run('shutdown',['xcrun','simctl','shutdown',sid],60)
        except Exception as error:print('OWNED_SHUTDOWN_DIAGNOSTIC',type(error).__name__,flush=True)
print('OLDEST_HARNESS_ALL_RESULTS',json.dumps(results),flush=True)
