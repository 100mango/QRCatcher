#!/bin/bash
set -euo pipefail
SUPPLEMENT_ONLY=false
SUPPLEMENT_PROJECT=
if [ "${GITHUB_REF:-}" = refs/heads/codex/ios-original-supplement ] || [ "${QRCATCHER_IOS_SUPPLEMENT_ONLY:-}" = true ]; then
  SUPPLEMENT_PROJECT=$(python3 - "$@" <<'PY'
from pathlib import Path
import os,sys,uuid
sys.path.insert(0,'scripts')
from ios_original_supplement_route import current_identity,PROJECT
identity=current_identity()
profiles={'iphone_pro':('SIMULATOR_ID','PhoneUIResults.xcresult','QRCatcherUITests'),
 'iphone_se3':('COMPACT_SIMULATOR_ID','CompactPhoneUIResults.xcresult','QRCatcherUITests'),
 'ipad_pro':('IPAD_SIMULATOR_ID','PadUIResults.xcresult','QRCatcherPadUITests'),
 'ipad_mini':('MINI_SIMULATOR_ID','MiniUIResults.xcresult','QRCatcherPadUITests')}
scope=os.environ.get('EVIDENCE_SCOPE');profile=profiles.get(scope)
if identity.get('diagnostic_only') is not True or profile is None or len(sys.argv)!=4:
 raise ValueError('Closed supplemental platform arguments required')
device,result,kind=sys.argv[1:]
if str(uuid.UUID(device)).upper()!=device or (result,kind)!=profile[1:] or os.environ.get(profile[0])!=device:
 raise ValueError('Exact selected supplemental result and destination required')
root=Path(os.environ.get('GITHUB_WORKSPACE',''))
if not root.is_absolute() or root.resolve(strict=True)!=root or Path.cwd()!=root:
 raise ValueError('Canonical supplemental checkout required')
build=root/'build'
if build.exists() or build.is_symlink():
 if build.resolve(strict=True)!=build or not build.is_dir() or build.stat().st_uid!=os.getuid():
  raise ValueError('Original owned supplemental build directory required')
if scope!='ipad_mini':
 base=result.removesuffix('.xcresult')
 stems=[base+('-layout' if scope=='ipad_pro' else ''),base+'-files',base+('' if scope=='ipad_pro' else '-imports')]
 for stem in stems:
  for path in (root/(stem+'.xcresult'),root/(stem+'.log'),build/(stem+'-command.json'),
   build/(stem+'-summary.json'),build/(stem+'-summary-command.json')):
   if path.exists() or path.is_symlink():raise ValueError('Supplemental result cannot retry or reuse stale evidence')
print(PROJECT)
PY
)
  SUPPLEMENT_ONLY=true
fi
if [ "${EVIDENCE_SCOPE:-}" = ipad_mini ] || [ "${2:-}" = MiniUIResults.xcresult ]; then
  python3 -u scripts/ipad_mini_setup.py row "$@"
  exit $?
fi
STEP_STARTED=$(python3 -c 'import time;print(time.monotonic())')
if [ "$SUPPLEMENT_ONLY" = true ] && [ "${PHONE_COMPLETION_ONLY:-}" = true ]; then
  python3 - "$1" "$STEP_STARTED" <<'PY_STEP'
import os,sys
from pathlib import Path
sys.path.insert(0,'scripts')
from atomic_json import write_json
from ios_original_supplement_route import current_identity
identity=current_identity();path=Path('build/ios-platform-step.json')
if identity['scope'] not in ('iphone_pro','iphone_se3') or path.exists() or path.is_symlink() or Path('build/ios-platform-closed-phase').exists() or Path('build/ios-platform-closed-phase').is_symlink():raise ValueError('Fresh selected original phone step required')
write_json(path,{'identity':identity,'device':sys.argv[1],'owner_pid':os.getppid(),'step_started_monotonic':float(sys.argv[2])},limit=16384)
PY_STEP
fi
python3 scripts/owned_process_barrier.py --check
DEVICE=$1
RESULT=$2
CLASS=$3
shift 3
for PREVIOUS in "$@"; do
  if [ -n "$PREVIOUS" ]; then
    python3 -u scripts/run_bounded.py 45 xcrun simctl shutdown "$PREVIOUS" || true
    python3 scripts/owned_process_barrier.py --check
  fi
done
python3 -u scripts/run_bounded.py 180 xcrun simctl boot "$DEVICE" || true
python3 scripts/owned_process_barrier.py --check
python3 -u scripts/run_bounded.py 300 xcrun simctl bootstatus "$DEVICE" -b
# Every Bash 3.2 array is populated, including phone/no-seed branches under -u.
PROJECT=QRCatcher.xcodeproj
if [ "${GITHUB_REF:-}" = refs/heads/codex/ios-original-release ]; then
  PROJECT=$(python3 scripts/ios_original_release_route.py project)
fi
if [ "$SUPPLEMENT_ONLY" = true ]; then PROJECT=$SUPPLEMENT_PROJECT; fi
COMMON=(xcodebuild test-without-building -project "$PROJECT" -scheme QRCatcher -configuration Debug -derivedDataPath build/iOS -destination "platform=iOS Simulator,id=$DEVICE" -parallel-testing-enabled NO -collect-test-diagnostics never -test-timeouts-enabled YES -default-test-execution-time-allowance 180 -maximum-test-execution-time-allowance 240 CODE_SIGNING_ALLOWED=NO)
qualify_supplement_result() {
  python3 - "$DEVICE" "$1" "$2" "$3" "$STEP_STARTED" <<'PY'
from pathlib import Path
import json,math,os,sys,time
sys.path.insert(0,'scripts')
from atomic_json import write_json
from ios_import_continuation import read_regular
from ios_original_supplement_route import current_identity,PROJECT,summary_admission,SUMMARY_POST_RETURN_SECONDS,SUMMARY_CLEANUP_SECONDS
from owned_process_barrier import blocked,mark_unconfirmed
from watch_process import execute
def strict(raw):
 def pairs(rows):
  result={}
  for key,value in rows:
   if key in result:raise ValueError('Duplicate receipt or summary key')
   result[key]=value
  return result
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
device,result,raw_cap,raw_exit,raw_start=sys.argv[1:];cap=int(raw_cap);exit_code=int(raw_exit);started=float(raw_start)
identity=current_identity()
scope=os.environ['EVIDENCE_SCOPE']
base={'iphone_pro':'PhoneUIResults','iphone_se3':'CompactPhoneUIResults','ipad_pro':'PadUIResults'}[scope]
ordinary=(['-only-testing:QRCatcherUITests/QRCatcherPadUITests',
 '-skip-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords']
 if scope=='ipad_pro' else ['-only-testing:QRCatcherUITests/QRCatcherUITests/testDeniedCameraAndEmptyHistory',
 '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPickerWarmupAndCancelPreservesPreviousSelection'])
photo='QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords' if scope=='ipad_pro' else 'QRCatcherImageImportUITests/testRealPhotosImportAndReopen'
allowed={(base+('-layout' if scope=='ipad_pro' else '')+'.xcresult'):(480 if scope=='ipad_pro' else 570,2,ordinary),
 base+'-files.xcresult':(360 if scope=='iphone_pro' else 240,1,['-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealFilesImportAndReopen']),
 base+('' if scope=='ipad_pro' else '-imports')+'.xcresult':(360,1,['-only-testing:QRCatcherUITests/'+photo])}
try:
 expected_cap,expected,selectors=allowed[result]
 if cap!=expected_cap or identity.get('diagnostic_only') is not True:raise ValueError('Wrong selected result cap/profile')
 stem=result.removesuffix('.xcresult')
 text=read_regular(Path(stem+'.log'),17*1024*1024).decode()
 starts=[strict(line.split(' ',1)[1]) for line in text.splitlines() if line.startswith('BOUNDED_COMMAND_START ')]
 ends=[strict(line.split(' ',1)[1]) for line in text.splitlines() if line.startswith('BOUNDED_COMMAND_END ')]
 if len(starts)!=1 or len(ends)!=1 or text.strip().splitlines()[-1]!='BOUNDED_COMMAND_END '+json.dumps(ends[0]):
  raise ValueError('One finalized bounded command receipt required')
 operation=ends[0]
 write_json(Path('build')/(stem+'-command.json'),operation,limit=16384)
 command=['xcodebuild','test-without-building','-project',PROJECT,'-scheme','QRCatcher','-configuration','Debug',
 '-derivedDataPath','build/iOS','-destination','platform=iOS Simulator,id='+device,'-parallel-testing-enabled','NO',
 '-collect-test-diagnostics','never','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','180',
 '-maximum-test-execution-time-allowance','240','CODE_SIGNING_ALLOWED=NO',*selectors,'-resultBundlePath',result]
 elapsed=operation.get('elapsed_seconds')
 if starts[0]!={'seconds':cap,'command':command} or operation.get('command')!=command or operation.get('timeout_seconds')!=cap or operation.get('exit')!=exit_code or exit_code not in (0,65) or operation.get('state')!='completed' or operation.get('cleanup_confirmed') is not True or type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0<=elapsed<cap+2 or blocked():
  raise ValueError('Selected command is unknown, late or unclean; no summary query allowed')
 summary_command=['xcrun','xcresulttool','get','test-results','summary','--path',result]
 admission=summary_admission(scope,result,started)
 summary_cap=admission['summary_seconds']
 print('IOS_SUPPLEMENT_SUMMARY_ADMISSION '+json.dumps(admission),flush=True)
 print('BOUNDED_COMMAND_START '+json.dumps({'seconds':summary_cap,'command':summary_command}),flush=True)
 summary_admission(scope,result,started)
 began=time.monotonic()
 code,raw,summary_operation=execute(summary_command,summary_cap,output_limit=65536,tail_limit=65536,echo=False)
 print('BOUNDED_COMMAND_END '+json.dumps(summary_operation),flush=True)
 write_json(Path('build')/(stem+'-summary-command.json'),summary_operation,limit=16384)
 if raw:Path('build',stem+'-summary.json').write_text(raw)
 duration=summary_operation.get('elapsed_seconds')
 if code!=0 or summary_operation.get('command')!=summary_command or summary_operation.get('timeout_seconds')!=summary_cap or summary_operation.get('exit')!=0 or summary_operation.get('state')!='completed' or summary_operation.get('cleanup_confirmed') is not True or summary_operation.get('output_bytes')!=len(raw.encode()) or type(duration) not in (int,float) or not math.isfinite(duration) or not 0<=duration<summary_cap+SUMMARY_POST_RETURN_SECONDS or time.monotonic()>=began+summary_cap+SUMMARY_POST_RETURN_SECONDS or time.monotonic()+SUMMARY_CLEANUP_SECONDS>admission['phase_deadline_monotonic']:
  raise ValueError('Summary is incomplete, late or unclean')
 value=strict(raw);keys=['totalTestCount','passedTests','failedTests','skippedTests','expectedFailures']
 counts={key:value.get(key) for key in keys};rows=value.get('devicesAndConfigurations')
 if any(type(v) is not int or v<0 for v in counts.values()) or counts['totalTestCount']!=expected or counts['skippedTests']!=0 or counts['expectedFailures']!=0 or counts['passedTests']+counts['failedTests']!=expected or not isinstance(rows,list) or len(rows)!=1 or rows[0].get('device',{}).get('deviceId')!=device or value.get('runtimeWarnings')!=[]:
  raise ValueError('Selected counts or destination did not qualify')
 if exit_code==0 and (value.get('result')!='Passed' or counts['passedTests']!=expected or value.get('testFailures')!=[]):raise ValueError('Successful exit conflicts with selected results')
 if exit_code==65 and (value.get('result')!='Failed' or counts['failedTests']==0 or not isinstance(value.get('testFailures'),list) or not value['testFailures']):raise ValueError('Failure is not finalized selected case evidence')
 print('IOS_SUPPLEMENT_RESULT '+json.dumps({'result':result,'device':device,'counts':counts,'diagnostic_only':True}),flush=True)
except BaseException as error:
 mark_unconfirmed({'state':'supplement_result_unresolved','exit':126,'cleanup_confirmed':False})
 print('IOS_SUPPLEMENT_REFUSED '+str(error),file=sys.stderr,flush=True)
 raise SystemExit(126)
PY
}
run_suite() {
  local OUTPUT=$1
  local CAP=$2
  shift 2
  set +e
  python3 -u scripts/run_bounded.py "$CAP" "${COMMON[@]}" "$@" -resultBundlePath "$OUTPUT" | tee "${OUTPUT%.xcresult}.log"
  TEST_EXIT=${PIPESTATUS[0]}
  set -e
  SUPPLEMENT_GATE_EXIT=0
  if [ "$SUPPLEMENT_ONLY" = true ]; then
    if qualify_supplement_result "$OUTPUT" "$CAP" "$TEST_EXIT"; then
      if [ "${PHONE_COMPLETION_ONLY:-}" = true ] && { [ "$OUTPUT" = "$RESULT" ] || [ "$OUTPUT" = "${RESULT%.xcresult}-files.xcresult" ]; }; then
        if python3 -u scripts/export_ios_platform_screenshots.py --retain-closed-phone-phase "${OUTPUT%.xcresult}" "$STEP_STARTED"; then :; else SUPPLEMENT_GATE_EXIT=126; fi
      fi
    else SUPPLEMENT_GATE_EXIT=$?; fi
  fi
}
LAYOUT_EXIT=-1
SEED_EXIT=-1
FILE_EXIT=-1
PHOTO_EXIT=-1
SUPPLEMENT_SEED_GATE_EXIT=-1
CONTINUE_AFTER_ORDINARY_FAILURE=false
# Pro 7239 spent 140 seconds launching XCTest before the Files case began.
# Keep its existing 180-second test allowance intact, plus bounded startup and
# cleanup reserve. Only the observed Pro profile changes; SE3/iPad stay at 240 seconds.
FILE_CAP=240
if [ "$CLASS" = QRCatcherUITests ] && [ "$RESULT" = PhoneUIResults.xcresult ]; then FILE_CAP=360; fi
record_setup() {
  python3 - "$DEVICE" "$CLASS" "$LAYOUT_EXIT" "$SEED_EXIT" "$PHOTO_EXIT" "$FILE_EXIT" "$FILE_CAP" <<'PY'
from pathlib import Path
import json,sys
sys.path.insert(0,'scripts')
from ios_import_continuation import read_regular
continuation=Path('build/ios-import-continuation.json')
continuation_record=json.loads(read_regular(continuation,16*1024)) if continuation.exists() or continuation.is_symlink() else None
Path('build').mkdir(exist_ok=True)
Path('build/ios-platform-setup.json').write_text(json.dumps({'device':sys.argv[1],'test_class':sys.argv[2],
 'layout_and_real_picker_cancel_exit':int(sys.argv[3]),'photo_seed_exit':int(sys.argv[4]),'real_photo_case_exit':int(sys.argv[5]),'real_files_case_exit':int(sys.argv[6]),'real_files_timeout_seconds':int(sys.argv[7]),
 'photo_import_gate':'ready' if int(sys.argv[4])==0 else 'blocked_or_not_requested',
 'seed_attempts':int(int(sys.argv[4])>=0),'timeout_does_not_prove_asset_absence':True,
 'independent_import_continuation':continuation_record},indent=2)+'\n')
PY
  if [ "$SUPPLEMENT_ONLY" = true ]; then
    python3 - "$SUPPLEMENT_SEED_GATE_EXIT" <<'PY'
from pathlib import Path
import json,sys
sys.path.insert(0,'scripts')
from ios_import_continuation import read_regular
from ios_original_supplement_route import current_identity
path=Path('build/ios-platform-setup.json');value=json.loads(read_regular(path,16384))
value.update(diagnostic_only=True,selected_cases=current_identity()['selected_cases'],full_original_row_accepted=False)
if int(sys.argv[1])!=0:value['photo_import_gate']='blocked_or_not_requested'
path.write_text(json.dumps(value,indent=2)+'\n')
PY
  fi
}
retain_supplement_seed() {
  python3 - "$DEVICE" "${RESULT%.xcresult}-seed.log" "$SEED_EXIT" <<'PY'
from pathlib import Path
import json,math,sys
sys.path.insert(0,'scripts')
from atomic_json import write_json
from ios_import_continuation import read_regular
from ios_original_supplement_route import current_identity
from owned_process_barrier import blocked,mark_unconfirmed
identity=current_identity()
device,name,raw_exit=sys.argv[1:];exit_code=int(raw_exit)
try:
 expected={'iphone_pro':'PhoneUIResults-seed.log','iphone_se3':'CompactPhoneUIResults-seed.log','ipad_pro':'PadUIResults-seed.log'}
 if identity.get('diagnostic_only') is not True or name!=expected[identity['scope']]:raise ValueError('Closed supplemental seed log required')
 text=read_regular(Path(name),17*1024*1024).decode()
 starts=[json.loads(line.split(' ',1)[1]) for line in text.splitlines() if line.startswith('BOUNDED_COMMAND_START ')]
 rows=[json.loads(line.split(' ',1)[1]) for line in text.splitlines() if line.startswith('BOUNDED_COMMAND_END ')]
 command=['xcrun','simctl','addmedia',device,'Tests/Fixtures/unicode.png']
 if starts!=[{'seconds':210,'command':command}] or len(rows)!=1 or text.strip().splitlines()[-1]!='BOUNDED_COMMAND_END '+json.dumps(rows[0]):raise ValueError('One finalized seed receipt required')
 operation=rows[0];write_json(Path('build')/(name.removesuffix('.log')+'-command.json'),operation,limit=16384)
 elapsed=operation.get('elapsed_seconds')
 if operation.get('command')!=command or operation.get('timeout_seconds')!=210 or operation.get('state')!='completed' or type(operation.get('exit')) is not int or operation['exit']!=exit_code or operation.get('cleanup_confirmed') is not True or type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0<=elapsed<212 or blocked():
  raise ValueError('Seed result is unknown, late or unclean')
except Exception as error:
 mark_unconfirmed({'state':'supplement_seed_unresolved','exit':126,'cleanup_confirmed':False})
 print('IOS_SUPPLEMENT_SEED_REFUSED '+str(error),file=sys.stderr,flush=True);raise SystemExit(126)
PY
}
record_setup
if [ "$CLASS" = QRCatcherPadUITests ]; then
  run_suite "${RESULT%.xcresult}-layout.xcresult" 480 "-only-testing:QRCatcherUITests/$CLASS" '-skip-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords'
  PHOTO_RESULT=$RESULT
  PHOTO_TEST='-only-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords'
else
  if [ "$SUPPLEMENT_ONLY" = true ]; then
    run_suite "$RESULT" 570 '-only-testing:QRCatcherUITests/QRCatcherUITests/testDeniedCameraAndEmptyHistory' '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPickerWarmupAndCancelPreservesPreviousSelection'
  else
    run_suite "$RESULT" 570 "-only-testing:QRCatcherUITests/$CLASS" '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPickerWarmupAndCancelPreservesPreviousSelection'
  fi
  PHOTO_RESULT="${RESULT%.xcresult}-imports.xcresult"
  PHOTO_TEST='-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPhotosImportAndReopen'
fi
LAYOUT_EXIT=$TEST_EXIT; record_setup
if [ "$SUPPLEMENT_ONLY" = true ] && [ "$SUPPLEMENT_GATE_EXIT" -ne 0 ]; then exit "$SUPPLEMENT_GATE_EXIT"; fi
if [ "$LAYOUT_EXIT" -ne 0 ]; then
  if [ "$SUPPLEMENT_ONLY" = true ]; then exit "$LAYOUT_EXIT"; fi
  if [ "$LAYOUT_EXIT" -ne 65 ] || [ "$CLASS" != QRCatcherUITests ] || [ "$RESULT" != PhoneUIResults.xcresult ]; then exit "$LAYOUT_EXIT"; fi
  # A finalized completed65 can preserve independent coverage. Outer timeouts,
  # missing summaries and unknown cleanup never enter this continuation.
  if python3 scripts/ios_import_continuation.py admit "$DEVICE" "$RESULT" "$STEP_STARTED"; then
    CONTINUE_AFTER_ORDINARY_FAILURE=true
  else
    GATE_EXIT=$?; record_setup; exit "$GATE_EXIT"
  fi
  record_setup
  python3 -u scripts/run_bounded.py 75 python3 scripts/stage_owned_import_fixture.py "$DEVICE"
else
  python3 scripts/stage_owned_import_fixture.py "$DEVICE"
fi
python3 scripts/owned_process_barrier.py --check
if [ "$CONTINUE_AFTER_ORDINARY_FAILURE" = true ]; then
  if python3 scripts/ios_import_continuation.py files "$DEVICE" "$RESULT" "$STEP_STARTED"; then :; else
    GATE_EXIT=$?; record_setup; exit "$GATE_EXIT"
  fi
  record_setup
fi
# Files uses only the owned Documents fixture and must not depend on Photos
# seeding. In c1552a7 a single addmedia timeout hid this independent real flow.
run_suite "${RESULT%.xcresult}-files.xcresult" "$FILE_CAP" '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealFilesImportAndReopen'
FILE_EXIT=$TEST_EXIT; record_setup
if [ "$SUPPLEMENT_ONLY" = true ] && [ "$SUPPLEMENT_GATE_EXIT" -ne 0 ]; then exit "$SUPPLEMENT_GATE_EXIT"; fi
if [ "$FILE_EXIT" -eq 126 ]; then exit "$FILE_EXIT"; fi
python3 scripts/owned_process_barrier.py --check
if [ "$CONTINUE_AFTER_ORDINARY_FAILURE" = true ]; then
  if python3 scripts/ios_import_continuation.py seed-and-photos "$DEVICE" "$RESULT" "$STEP_STARTED"; then :; else
    GATE_EXIT=$?; record_setup; exit "$GATE_EXIT"
  fi
  record_setup
fi
# Exactly one seed attempt after the real picker warm-up. A Files assertion
# failure remains recorded, while the distinct Photos case may still execute.
# No further mutation is allowed when owned-process cleanup is unconfirmed.
if [ "$SUPPLEMENT_ONLY" = true ]; then
  set +e
  python3 -u scripts/run_bounded.py 210 xcrun simctl addmedia "$DEVICE" Tests/Fixtures/unicode.png | tee "${RESULT%.xcresult}-seed.log"
  SEED_EXIT=${PIPESTATUS[0]}
  set -e
  if retain_supplement_seed; then SUPPLEMENT_SEED_GATE_EXIT=0; else SUPPLEMENT_SEED_GATE_EXIT=$?; fi
else
  if python3 -u scripts/run_bounded.py 210 xcrun simctl addmedia "$DEVICE" Tests/Fixtures/unicode.png; then SEED_EXIT=0; else SEED_EXIT=$?; fi
fi
record_setup
if [ "$SUPPLEMENT_ONLY" = true ] && [ "$SUPPLEMENT_SEED_GATE_EXIT" -ne 0 ]; then exit "$SUPPLEMENT_SEED_GATE_EXIT"; fi
if [ "$SEED_EXIT" -ne 0 ]; then echo "PHOTO_IMPORT_PRECONDITION_FAILED=$SEED_EXIT; no retry or asset-absence claim; Files outcome retained separately"; exit "$SEED_EXIT"; fi
python3 scripts/owned_process_barrier.py --check
if [ "$CONTINUE_AFTER_ORDINARY_FAILURE" = true ]; then
  if python3 scripts/ios_import_continuation.py photos "$DEVICE" "$RESULT" "$STEP_STARTED"; then :; else
    GATE_EXIT=$?; record_setup; exit "$GATE_EXIT"
  fi
  record_setup
fi
run_suite "$PHOTO_RESULT" 360 "$PHOTO_TEST"
PHOTO_EXIT=$TEST_EXIT; record_setup
if [ "$SUPPLEMENT_ONLY" = true ] && [ "$SUPPLEMENT_GATE_EXIT" -ne 0 ]; then exit "$SUPPLEMENT_GATE_EXIT"; fi
if [ "$PHOTO_EXIT" -eq 126 ]; then exit "$PHOTO_EXIT"; fi
if [ "$LAYOUT_EXIT" -ne 0 ]; then exit "$LAYOUT_EXIT"; fi
if [ "$FILE_EXIT" -ne 0 ]; then exit "$FILE_EXIT"; fi
exit "$PHOTO_EXIT"
