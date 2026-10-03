#!/usr/bin/env python3
"""Bounded actual Watch app launch, local Vision/unit and native UI execution.
WCSession background transfer is intentionally a paired-physical-device gate.
"""
import json,os,signal,subprocess,time
from pathlib import Path
out=Path('build/watch-runtime');out.mkdir(parents=True,exist_ok=True)
report={'commit':os.environ['GITHUB_SHA'],'background_file_transport':'requires_paired_physical_devices'}
def run(args,seconds=120,check=True,log=None):
 print('+ '+' '.join(args),flush=True)
 process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
 try: data=process.communicate(timeout=seconds)[0]
 except subprocess.TimeoutExpired:
  os.killpg(process.pid,signal.SIGTERM)
  try:data=process.communicate(timeout=10)[0]
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);data=process.communicate()[0]
  if log:Path(log).write_text(data)
  print(data,flush=True);raise TimeoutError('Bounded operation timed out: '+args[0])
 if log:Path(log).write_text(data)
 print(data,flush=True)
 if check and process.returncode:raise RuntimeError('Command failed: '+str(process.returncode)+' '+args[0])
 return process.returncode,data
raw=json.loads(run(['xcrun','simctl','list','devices','available','-j'])[1])
rows=[d for runtime,devices in raw['devices'].items() if runtime.endswith('watchOS-27-0') for d in devices]
assert rows,'No installed Watch 27 simulator; SDK build is not runtime proof'
device=next((d for d in rows if '46mm' in d['name']),rows[0]);udid=device['udid'];report['device']=device
with open(os.environ['GITHUB_ENV'],'a') as f:f.write('WATCH_SIMULATOR_ID='+udid+'\n')
failed=False
try:
 if device['state']!='Booted':run(['xcrun','simctl','boot',udid],180)
 run(['xcrun','simctl','bootstatus',udid,'-b'],300)
 app='build/WatchTests/Build/Products/Debug-watchsimulator/QRCatcherWatch.app'
 run(['xcrun','simctl','install',udid,app],90)
 code,text=run(['xcrun','simctl','launch',udid,'100mango.QRCatcher.watchkitapp'],60);report['launch']=text
 time.sleep(3)
 pid=text.strip().rsplit(':',1)[-1].strip();assert pid.isdigit();report['process']=run(['ps','-p',pid,'-o','pid=,comm='],20)[1]
 assert 'QRCatcherWatch' in report['process']
 media,output=run(['xcrun','simctl','addmedia',udid,'Tests/Fixtures/unicode.png'],60,check=False)
 report['photo_seeding']={'exit':media,'output':output[-4000:]}
 common=['xcodebuild','test-without-building','-project','QRCatcher.xcodeproj','-scheme','QRCatcherWatch','-configuration','Debug','-derivedDataPath','build/WatchTests','-destination','platform=watchOS Simulator,id='+udid,'-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','90','-maximum-test-execution-time-allowance','150','CODE_SIGNING_ALLOWED=NO']
 code,_=run(common+['-only-testing:QRCatcherWatchTests','-resultBundlePath','WatchUnitResults.xcresult'],360,False,'watch-unit.log');report['hosted_tests_exit']=code;failed|=code!=0
 options=['-only-testing:QRCatcherWatchUITests']
 code,_=run(common+options+['-resultBundlePath','WatchUIResults.xcresult'],360,False,'watch-ui.log');report['ui_tests_exit']=code;failed|=code!=0
 report['photos_import_gate']='physical_device_required_system_picker_explicitly_unavailable_in_simulator'
 report['ui_fixture_scope']='offline_collection_only_prepared_by_actual_hosted_decoder_not_system_Photos_import'
finally:
 (out/'runtime.json').write_text(json.dumps(report,indent=2)+'\n')
 run(['xcrun','simctl','shutdown',udid],45,False)
if failed:raise SystemExit('One or more native Watch gates are not satisfied; see actual runtime evidence')
