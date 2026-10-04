#!/usr/bin/env python3
"""Independent bounded XCTest invocations keep a failed cleanup from hiding cases."""
import json,os,subprocess,sys,uuid
from pathlib import Path
from watch_process import execute
from atomic_json import write_json
from owned_process_barrier import mark_unconfirmed
from run_native_size_case import run_case
from owned_process_group import stop_group
udid=str(uuid.UUID(sys.argv[1])).upper();out=Path('build/vision-runtime');out.mkdir(parents=True,exist_ok=True)
marker=out/'ui-completed.marker';marker.unlink(missing_ok=True)
report={'commit':os.environ['GITHUB_SHA'],'device':udid,'cases':[]}
common=['xcodebuild','test-without-building','-project','QRCatcher.xcodeproj','-scheme','QRCatcherVision','-configuration','Debug','-derivedDataPath','build/VisionTests','-destination','platform=visionOS Simulator,id='+udid,'-parallel-testing-enabled','NO','-collect-test-diagnostics','never','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','420','-maximum-test-execution-time-allowance','480','CODE_SIGNING_ALLOWED=NO']
cases=[('photos-export','testRealPhotosImportCopyAndReopen','VisionPhotosUIResults.xcresult',600),
       ('files','testRealFilesImportAndReopen','VisionFilesUIResults.xcresult',300),
       ('chinese','testChineseEmptyPhotosResultAndOfflinePolicy','VisionChineseUIResults.xcresult',300)]
failed=False
with (out/'checkpoint-capture.log').open('w') as output:
 capture=subprocess.Popen(['python3','-u','scripts/capture_vision_checkpoints.py',udid,'vision-ui-test.log'],stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  for label,name,result,seconds in cases:
   # Exact owned app only; never restart simulator/security services. Preserve
   # the outcome and continue a distinct case rather than retrying the same action.
   cleanup,_,cleanup_info=execute(['xcrun','simctl','terminate',udid,'100mango.QRCatcher'],30)
   row={'case':name,'result':result,'pre_case_app_termination':cleanup_info,'state':'starting'}
   report['cases'].append(row);write_json(out/'ui-cases.json',report)
   if cleanup==126 or cleanup_info.get('cleanup_confirmed') is not True:
    row['state']='blocked_owned_process_cleanup_unconfirmed';report['cleanup_unconfirmed']=True
    mark_unconfirmed(cleanup_info);failed=True;break
   print('VISION_CASE_START '+json.dumps(row),flush=True)
   code,tail,operation=execute(common+['-only-testing:QRCatcherVisionUITests/QRCatcherVisionUITests/'+name,'-resultBundlePath',result],seconds)
   (out/(label+'-ui-tail.log')).write_text(tail[-16*1024:])
   row.update(state='finished',exit=code,operation=operation);failed|=code!=0
   write_json(out/'ui-cases.json',report);print('VISION_CASE_END '+json.dumps(row),flush=True)
   if code==126 or operation.get('cleanup_confirmed') is not True:
    report['cleanup_unconfirmed']=True;mark_unconfirmed(operation);failed=True;break
  if not report.get('cleanup_unconfirmed'):
   size_exit,size_report=run_case('vision',udid)
   report['system_text_size_ui_exit']=size_exit;report['largest_text_ui']=size_report['status'];failed|=size_exit!=0
   if size_exit==126:report['cleanup_unconfirmed']=True
 finally:
  marker.touch()
  try: capture_exit=capture.wait(timeout=30)
  except subprocess.TimeoutExpired:
   capture_exit=124
  capture_clean=stop_group(capture)
  report['capture_cleanup_confirmed']=capture_clean
  if not capture_clean:
   report['cleanup_unconfirmed']=True;mark_unconfirmed({'state':'capture_cleanup_unconfirmed','exit':126,'cleanup_confirmed':False});failed=True
  report['capture_process_exit']=capture_exit;write_json(out/'ui-cases.json',report)
  failed|=capture_exit!=0
if failed:raise SystemExit('One or more independent Vision UI/capture gates failed; retained cases stay distinct')
