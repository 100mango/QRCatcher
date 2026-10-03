#!/bin/bash
set -euo pipefail
DEVICE=$1
RESULT=$2
CLASS=$3
shift 3
for PREVIOUS in "$@"; do
  if [ -n "$PREVIOUS" ]; then xcrun simctl shutdown "$PREVIOUS" || true; fi
done
python3 -u scripts/run_bounded.py 180 xcrun simctl boot "$DEVICE" || true
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
PHOTO_EXIT=-1
record_setup() {
  python3 - "$DEVICE" "$CLASS" "$LAYOUT_EXIT" "$SEED_EXIT" "$PHOTO_EXIT" <<'PY'
from pathlib import Path
import json,sys
Path('build').mkdir(exist_ok=True)
Path('build/ios-platform-setup.json').write_text(json.dumps({'device':sys.argv[1],'test_class':sys.argv[2],
 'layout_and_real_picker_cancel_exit':int(sys.argv[3]),'photo_seed_exit':int(sys.argv[4]),'real_photo_case_exit':int(sys.argv[5]),
 'photo_import_gate':'ready' if int(sys.argv[4])==0 else 'blocked_or_not_requested',
 'seed_attempts':int(int(sys.argv[4])>=0),'timeout_does_not_prove_asset_absence':True},indent=2)+'\n')
PY
}
record_setup
if [ "$CLASS" = QRCatcherPadUITests ]; then
  # The existing actual picker/cancel/privacy and split/share/relaunch cases run
  # first. This installs the built app and exercises its normal system picker;
  # it grants no production PhotoKit access and is not a claimed root-cause fix.
  run_suite "${RESULT%.xcresult}-layout.xcresult" 480 "-only-testing:QRCatcherUITests/$CLASS" '-skip-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords'
  LAYOUT_EXIT=$TEST_EXIT
  record_setup
  if [ "$LAYOUT_EXIT" -ne 0 ]; then exit "$LAYOUT_EXIT"; fi
  python3 scripts/stage_owned_import_fixture.py "$DEVICE"
  # Exactly one seed attempt. Related controlled runs needed166.7s on a cold
  # library; retain the real outcome and never equate a timeout with no asset.
  if python3 -u scripts/run_bounded.py 210 xcrun simctl addmedia "$DEVICE" Tests/Fixtures/unicode.png; then
    SEED_EXIT=0
    echo 'Independent synthetic Photos QR seeded after actual picker warm-up'
  else
    SEED_EXIT=$?
    echo "PHOTO_IMPORT_PRECONDITION_FAILED=$SEED_EXIT; no retry and no asset-absence claim; layout passes remain separate"
  fi
  record_setup
  if [ "$SEED_EXIT" -ne 0 ]; then exit "$SEED_EXIT"; fi
  run_suite "$RESULT" 360 '-only-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords' '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealFilesImportAndReopen'
  PHOTO_EXIT=$TEST_EXIT
  record_setup
  exit "$PHOTO_EXIT"
fi
run_suite "$RESULT" 570 "-only-testing:QRCatcherUITests/$CLASS" '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPickerWarmupAndCancelPreservesPreviousSelection'
LAYOUT_EXIT=$TEST_EXIT; record_setup
if [ "$LAYOUT_EXIT" -ne 0 ]; then exit "$LAYOUT_EXIT"; fi
python3 scripts/stage_owned_import_fixture.py "$DEVICE"
if python3 -u scripts/run_bounded.py 210 xcrun simctl addmedia "$DEVICE" Tests/Fixtures/unicode.png; then SEED_EXIT=0; else SEED_EXIT=$?; fi
record_setup
if [ "$SEED_EXIT" -ne 0 ]; then echo "PHOTO_IMPORT_PRECONDITION_FAILED=$SEED_EXIT; no retry or asset-absence claim"; exit "$SEED_EXIT"; fi
run_suite "${RESULT%.xcresult}-imports.xcresult" 360 '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealFilesImportAndReopen' '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPhotosImportAndReopen'
PHOTO_EXIT=$TEST_EXIT; record_setup
exit "$PHOTO_EXIT"
