#!/bin/bash
set -euo pipefail
if [ "${EVIDENCE_SCOPE:-}" = ipad_mini ] || [ "${2:-}" = MiniUIResults.xcresult ]; then
  python3 -u scripts/ipad_mini_setup.py row "$@"
  exit $?
fi
STEP_STARTED=$(python3 -c 'import time;print(time.monotonic())')
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
COMMON=(xcodebuild test-without-building -project QRCatcher.xcodeproj -scheme QRCatcher -configuration Debug -derivedDataPath build/iOS -destination "platform=iOS Simulator,id=$DEVICE" -parallel-testing-enabled NO -collect-test-diagnostics never -test-timeouts-enabled YES -default-test-execution-time-allowance 180 -maximum-test-execution-time-allowance 240 CODE_SIGNING_ALLOWED=NO)
run_suite() {
  local OUTPUT=$1
  local CAP=$2
  shift 2
  set +e
  python3 -u scripts/run_bounded.py "$CAP" "${COMMON[@]}" "$@" -resultBundlePath "$OUTPUT" | tee "${OUTPUT%.xcresult}.log"
  TEST_EXIT=${PIPESTATUS[0]}
  set -e
}
LAYOUT_EXIT=-1
SEED_EXIT=-1
FILE_EXIT=-1
PHOTO_EXIT=-1
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
}
record_setup
if [ "$CLASS" = QRCatcherPadUITests ]; then
  run_suite "${RESULT%.xcresult}-layout.xcresult" 480 "-only-testing:QRCatcherUITests/$CLASS" '-skip-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords'
  PHOTO_RESULT=$RESULT
  PHOTO_TEST='-only-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords'
else
  run_suite "$RESULT" 570 "-only-testing:QRCatcherUITests/$CLASS" '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPickerWarmupAndCancelPreservesPreviousSelection'
  PHOTO_RESULT="${RESULT%.xcresult}-imports.xcresult"
  PHOTO_TEST='-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPhotosImportAndReopen'
fi
LAYOUT_EXIT=$TEST_EXIT; record_setup
if [ "$LAYOUT_EXIT" -ne 0 ]; then
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
if python3 -u scripts/run_bounded.py 210 xcrun simctl addmedia "$DEVICE" Tests/Fixtures/unicode.png; then SEED_EXIT=0; else SEED_EXIT=$?; fi
record_setup
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
if [ "$PHOTO_EXIT" -eq 126 ]; then exit "$PHOTO_EXIT"; fi
if [ "$LAYOUT_EXIT" -ne 0 ]; then exit "$LAYOUT_EXIT"; fi
if [ "$FILE_EXIT" -ne 0 ]; then exit "$FILE_EXIT"; fi
exit "$PHOTO_EXIT"
