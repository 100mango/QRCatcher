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
SEED_EXIT=0
EXTRA=()
if [ "$CLASS" = QRCatcherPadUITests ]; then
  # Normal Photos launch can initialize its disposable local library. No account,
  # database edit or permission grant is used, and launch failure is not masked as
  # an app failure. The actual addmedia command remains an independent strict gate.
  python3 -u scripts/run_bounded.py 30 xcrun simctl launch "$DEVICE" com.apple.mobileslideshow || echo 'Optional Photos launch unavailable'
  if python3 -u scripts/run_bounded.py 150 xcrun simctl addmedia "$DEVICE" Tests/Fixtures/unicode.png; then
    echo 'Independent synthetic Photos QR seeded'
  else
    SEED_EXIT=$?
    echo "PHOTO_IMPORT_PRECONDITION_FAILED=$SEED_EXIT; real import remains blocked, unaffected split/layout tests continue"
    EXTRA+=('-skip-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords')
  fi
fi
python3 - "$DEVICE" "$CLASS" "$SEED_EXIT" <<'PY'
from pathlib import Path
import json,sys
Path('build').mkdir(exist_ok=True)
Path('build/ios-platform-setup.json').write_text(json.dumps({'device':sys.argv[1],'test_class':sys.argv[2],'photo_seed_exit':int(sys.argv[3]),'photo_import_gate':'blocked' if int(sys.argv[3]) else 'ready'},indent=2)+'\n')
PY
set +e
python3 -u scripts/run_bounded.py 570 xcodebuild test-without-building -project QRCatcher.xcodeproj -scheme QRCatcher -configuration Debug -derivedDataPath build/iOS -destination "platform=iOS Simulator,id=$DEVICE" -only-testing:"QRCatcherUITests/$CLASS" "${EXTRA[@]}" -parallel-testing-enabled NO -collect-test-diagnostics never -test-timeouts-enabled YES -default-test-execution-time-allowance 180 -maximum-test-execution-time-allowance 240 -resultBundlePath "$RESULT" CODE_SIGNING_ALLOWED=NO | tee "${RESULT%.xcresult}.log"
TEST_EXIT=${PIPESTATUS[0]}
set -e
if [ "$SEED_EXIT" -ne 0 ]; then exit "$SEED_EXIT"; fi
exit "$TEST_EXIT"
