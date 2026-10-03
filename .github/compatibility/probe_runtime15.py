#!/usr/bin/env python3
"""Bounded iOS 15.5 feasibility probe on an eligible, disposable cloud host."""
import hashlib, json, os, pathlib, plistlib, signal, subprocess, sys, urllib.parse, urllib.request

def run(args, timeout=60, required=True):
    print('COMMAND', args, flush=True)
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try: output, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL); output, _ = process.communicate()
        print('BOUNDED_TIMEOUT', timeout, 'seconds; availability remains inconclusive')
        print(output[-10000:]); return None
    print('EXIT', process.returncode, flush=True)
    print(output[-16000:], flush=True)
    if process.returncode and required: raise SystemExit(process.returncode)
    return output if process.returncode == 0 else None

def version(s): return tuple(int(n) for n in s.split('.'))
host = subprocess.check_output(['sw_vers','-productVersion'],text=True).strip()
xcode = subprocess.check_output(['xcodebuild','-version'],text=True).strip()
assert version(host)[0] == 26, 'This probe is exclusively for the supported macOS 26 host'
assert xcode.splitlines() == ['Xcode 26.6','Build version 17F113'], xcode
print('EXACT_HOST',host,xcode)
url='https://devimages-cdn.apple.com/downloads/xcode/simulators/index2.dvtdownloadableindex'
with urllib.request.urlopen(url,timeout=30) as response: data=response.read(5_000_000)
catalog=plistlib.loads(data)
runtime=next(r for r in catalog['downloadables'] if r['name']=='iOS 15.5 Simulator')
assert runtime['simulatorVersion']['version']=='15.5'
assert runtime['contentType']=='package'
assert urllib.parse.urlparse(runtime['source']).hostname=='devimages-cdn.apple.com'
requirements=runtime.get('hostRequirements',{})
for key,value in [('maxHostVersion',host),('maxXcodeVersion','26.6')]:
    if key in requirements: assert version(value)<=version(requirements[key]), (key,value,requirements)
for key,value in [('minHostVersion',host),('minXcodeVersion','26.6')]:
    if key in requirements: assert version(value)>=version(requirements[key]), (key,value,requirements)
assert 'arm64' not in requirements.get('excludedHostArchitectures',[])
print('OFFICIAL_CATALOG',json.dumps({'url':url,'sha256':hashlib.sha256(data).hexdigest(),'runtime':runtime},sort_keys=True))
# Apple explicitly excludes iOS15 from Sonoma14, which is not this host.
# Apple lists iOS15+ simulators for Xcode26.6; use the preinstalled reputable helper
# solely for this Apple package, with stdin closed and no account credentials.
run(['xcodes','version'],required=False)
run(['xcodes','runtimes','install','--help'])
result=run(['xcodes','runtimes','install','iOS 15.5','--no-aria2'],timeout=720,required=False)
all_runtimes=json.loads(subprocess.check_output(['xcrun','simctl','list','runtimes','-j']))['runtimes']
matching=[r for r in all_runtimes if r.get('platform')=='iOS' and r.get('version')=='15.5']
print('ACTUAL_15_5_RUNTIME',json.dumps(matching,sort_keys=True))
if not matching or not matching[0].get('isAvailable'):
    print('FEASIBILITY_NOT_ESTABLISHED; app and XCTest execution not attempted')
    raise SystemExit(0)
runtime=matching[0]
supported=runtime.get('supportedDeviceTypes',[])
target=next((d for d in supported if d['name']=='iPhone SE (3rd generation)'),None)
if target is None:
    print('NO_SUPPORTED_SE3_DEVICE_TYPE; app and XCTest execution not attempted');raise SystemExit(0)
id=subprocess.check_output(['xcrun','simctl','create','Compatibility iOS15.5 SE3',target['identifier'],runtime['identifier']],text=True).strip()
print('PROBE_SIMULATOR',id, target['name'],runtime['version'],runtime['buildversion'])
run(['xcrun','simctl','boot',id])
ready=run(['xcrun','simctl','bootstatus',id,'-b'],timeout=480,required=False)
if ready is not None:
    observed=subprocess.run(['xcrun','simctl','spawn',id,'launchctl','print','system'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    print('BOOTED_LAUNCHCTL_EXIT',observed.returncode)
    print('BOOTABLE_RUNTIME_ESTABLISHED; no app or XCTest pass is claimed')
run(['xcrun','simctl','shutdown',id],required=False)
