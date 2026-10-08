#!/usr/bin/env python3
"""Bounded actual Watch app launch, portable QR/unit and native UI execution.
WCSession background transfer is intentionally a paired-physical-device gate.
"""
import json,os,time,uuid,subprocess
from watch_process import execute
from owned_process_barrier import mark_unconfirmed,blocked
from run_native_size_case import run_case
from settings_build_provenance import observed_unsupported
from pathlib import Path
out=Path('build/watch-runtime');out.mkdir(parents=True,exist_ok=True)
report={'commit':os.environ['GITHUB_SHA'],'background_file_transport':'requires_paired_physical_devices','operations':[]}
def cleanup_guard(unconfirmed):
 report['cleanup_unconfirmed']=unconfirmed
 with open(os.environ['GITHUB_ENV'],'a') as f:f.write('WATCH_SIZE_CLEANUP_UNCONFIRMED='+str(unconfirmed).lower()+'\n')
def record():
 encoded=json.dumps(report,indent=2)+'\n';assert len(encoded.encode())<64*1024
 (out/'runtime.json').write_text(encoded)
def run(args,seconds=120,check=True,log=None):
 operation={'command':args,'timeout_seconds':seconds,'state':'starting'}
 report['operations'].append(operation);record();print('WATCH_COMMAND_START '+json.dumps(operation),flush=True)
 code,data,details=execute(args,seconds)
 operation.update(details);record()
 if code==126 or details.get('cleanup_confirmed') is not True:
  mark_unconfirmed(details);cleanup_guard(True);record();raise RuntimeError('Owned command group exit is unconfirmed; stop until disposable VM teardown')
 if log:Path(log).write_text(data)
 print('WATCH_COMMAND_END '+json.dumps(operation),flush=True)
 if check and code:raise RuntimeError('Command failed: '+str(code)+' '+args[0])
 return code,data
raw=json.loads(run(['xcrun','simctl','list','devices','available','-j'])[1])
rows=[d for runtime,devices in raw['devices'].items() if runtime.endswith('watchOS-27-0') for d in devices]
assert rows,'No installed Watch 27 simulator; SDK build is not runtime proof'
scope=os.environ.get('EVIDENCE_SCOPE','watchos');assert scope in ['watchos','watchos_40','watchos_49']
requested={'watchos':'Apple Watch Series 12 (46mm)','watchos_40':'Apple Watch SE 3 (40mm)','watchos_49':'Apple Watch Ultra 4 (49mm)'}[scope]
matches=[d for d in rows if d['name']==requested];assert matches,'Requested endpoint is not present in this VM inventory: '+requested
device=matches[0];report.update(scope=scope,requested_model=requested)
runtime=next(runtime for runtime,devices in raw['devices'].items() if device in devices)
_,created=run(['xcrun','simctl','create','QRCatcher Native Watch Validation',device['deviceTypeIdentifier'],runtime],60)
udid=str(uuid.UUID(created.strip())).upper();os.environ['WATCH_SIMULATOR_ID']=udid;report.update(device_type=device['deviceTypeIdentifier'],runtime=runtime,device_udid=udid,device_ownership='created solely for this disposable validation')
with open(os.environ['GITHUB_ENV'],'a') as f:f.write('WATCH_SIMULATOR_ID='+udid+'\n')
failed=False
try:
 pair_code,pairs=run(['xcrun','simctl','list','pairs','-j'],30,False)
 report['pairing_query_exit']=pair_code
 if pair_code==0:
  values=json.loads(pairs).get('pairs',{})
  report['matching_pairings']=[{'id':key,'watch':value.get('watch'),'phone':value.get('phone'),'state':value.get('state')} for key,value in values.items() if value.get('watch',{}).get('udid')==udid]
 record()
 run(['xcrun','simctl','boot',udid],180)
 run(['xcrun','simctl','bootstatus',udid,'-b'],300)
 app='build/WatchTests/Build/Products/Debug-watchsimulator/QRCatcherWatch.app'
 run(['xcrun','simctl','install',udid,app],90)
 code,text=run(['xcrun','simctl','launch',udid,'100mango.QRCatcher.watchkitapp'],60);report['launch']=text
 time.sleep(3)
 pid=text.strip().rsplit(':',1)[-1].strip();assert pid.isdigit();report['process']=run(['ps','-p',pid,'-o','pid=,comm='],20)[1]
 assert 'QRCatcherWatch' in report['process']
 run(['xcrun','simctl','io',udid,'screenshot','--type=jpeg',str(out/'actual-app-launch.jpg')],30,False)
 report['manual_app_terminate_exit']=run(['xcrun','simctl','terminate',udid,'100mango.QRCatcher.watchkitapp'],30,False)[0]
 report['photo_seeding']='Not attempted: actual Watch Photos picker explicitly reports simulator unavailability; hosted fixtures exercise the real decoder separately'
 common=['xcodebuild','test-without-building','-project','QRCatcher.xcodeproj','-scheme','QRCatcherWatch','-configuration','Debug','-derivedDataPath','build/WatchTests','-destination','platform=watchOS Simulator,id='+udid,'-parallel-testing-enabled','NO','-maximum-concurrent-test-simulator-destinations','1','-collect-test-diagnostics','never','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','90','-maximum-test-execution-time-allowance','150','CODE_SIGNING_ALLOWED=NO']
 code,_=run(common+['-only-testing:QRCatcherWatchTests','-resultBundlePath','WatchUnitResults.xcresult'],600,False,'watch-unit.log');report['hosted_tests_exit']=code;failed|=code!=0
 hosted_passed=code==0
 options=['-only-testing:QRCatcherWatchUITests','-skip-testing:QRCatcherWatchUITests/QRCatcherWatchSettingsDiscovery','-skip-testing:QRCatcherWatchUITests/QRCatcherWatchUITests/testFixtureResultAndRelaunchAtLargestPublicTrait']
 if code:
  report['dependent_offline_ui']='Not executed: hosted fixture preparation did not pass; independent empty/policy and actual system-picker limitation UI still runs'
  options+=['-skip-testing:QRCatcherWatchUITests/QRCatcherWatchUITests/testFixtureFedOfflineResultSourceImageAndRelaunch','-skip-testing:QRCatcherWatchUITests/QRCatcherWatchUITests/testSyntheticJournalRecoveryAcrossActualAppRelaunch']
  run(['python3','scripts/collect_watch_startup_diagnostics.py',udid],45,False)
 code,_=run(common+options+['-resultBundlePath','WatchUIResults.xcresult'],360,False,'watch-ui.log');report['ui_tests_exit']=code;failed|=code!=0
 if code:run(['python3','scripts/collect_watch_startup_diagnostics.py',udid,'ui'],45,False)
 cleanup_guard(True);record()
 size_exit,size_report=run_case('watch',udid,precondition=hosted_passed)
 report['system_text_size_ui_exit']=size_exit;report['largest_text_ui']=size_report['status'];failed|=size_exit!=0
 if size_exit==126:raise RuntimeError('System-size UI gate is unresolved; no further simulator action')
 if scope=='watchos' and size_exit==2 and observed_unsupported('watch',udid):
  report['settings_discovery']='starting_read_only_unqualified';record()
  # No new session for the shell/controller: each already-reviewed fenced
  # command owns its group, and the pre-Python latch survives an outer kill.
  discovery=subprocess.run(['bash','scripts/run_settings_discovery_fenced.sh','watch',udid,os.environ['QRCATCHER_RUNTIME_PARENT_START']]).returncode
  report['settings_discovery_exit']=discovery;record()
  if discovery!=2 or blocked():
   mark_unconfirmed({'state':'settings_discovery_parent_unresolved','exit':126,'cleanup_confirmed':False})
   cleanup_guard(True);record();raise RuntimeError('Settings discovery ownership unresolved; no later simulator action')
 cleanup_guard(False)
 report['photos_import_gate']='physical_device_required_system_picker_explicitly_unavailable_in_simulator'
 report['ui_fixture_scope']='offline_collection_only_prepared_by_actual_hosted_decoder_not_system_Photos_import'
finally:
 record()
 if not report.get('cleanup_unconfirmed'):
  run(['xcrun','simctl','shutdown',udid],45,False)
  run(['xcrun','simctl','delete',udid],45,False) # Only the UUID created above, never a pre-existing device.
if failed:raise SystemExit('One or more native Watch gates are not satisfied; see actual runtime evidence')
