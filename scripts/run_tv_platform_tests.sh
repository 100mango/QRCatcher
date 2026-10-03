#!/bin/bash
set -euo pipefail
DEVICE=$(python3 - <<'PY'
import json,subprocess
raw=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','-j']))
rows=[d for runtime,devices in raw['devices'].items() if runtime.endswith('tvOS-27-0') for d in devices]
assert rows,'No installed available tvOS 27 simulator was discovered'
print(next((d for d in rows if '4K' in d['name']),rows[0])['udid'])
PY
)
echo "TV_SIMULATOR_ID=$DEVICE" >> "$GITHUB_ENV"
python3 -u scripts/run_bounded.py 180 xcrun simctl boot "$DEVICE"
python3 -u scripts/run_bounded.py 300 xcrun simctl bootstatus "$DEVICE" -b
# Only this independent synthetic QR photo is imported; no account or cloud setup.
python3 -u scripts/run_bounded.py 150 xcrun simctl addmedia "$DEVICE" Tests/Fixtures/unicode.png
BASE=(python3 -u scripts/run_bounded.py 420 xcodebuild test-without-building -project QRCatcher.xcodeproj -scheme QRCatcherTV -configuration Debug -derivedDataPath build/TVTests -destination "platform=tvOS Simulator,id=$DEVICE" -parallel-testing-enabled NO -collect-test-diagnostics never -test-timeouts-enabled YES -default-test-execution-time-allowance 180 -maximum-test-execution-time-allowance 240 CODE_SIGNING_ALLOWED=NO)
set +e
"${BASE[@]}" -only-testing:QRCatcherTVTests -only-testing:QRCatcherTVUITests/QRCatcherTVUITests/testActualPhotosDecodeExportVerificationAndOfflineReopen -resultBundlePath TVTestResults.xcresult | tee tv-test.log
ORIGINAL_EXIT=${PIPESTATUS[0]}
set -e
# Preserve the original red result. Only an observed exact QRCatcher Photos
# dialog/focus failure authorizes this separate synthetic per-app setup lane.
if [ "$ORIGINAL_EXIT" -ne 0 ] && grep -q QRCATCHER_TV_EXACT_PERMISSION_FOCUS_BLOCKED tv-test.log; then
  echo 'Separate lane: explicit synthetic simulator Photos grant; original prompt automation remains failed.'
  xcrun simctl terminate "$DEVICE" 100mango.QRCatcher || true
  xcrun simctl privacy "$DEVICE" grant photos 100mango.QRCatcher
  set +e
  "${BASE[@]}" -only-testing:QRCatcherTVUITests/QRCatcherTVUITests/testExplicitlyPreconditionedPhotosDecodeExportAndReopen -resultBundlePath TVAuthorizedUIResults.xcresult | tee tv-authorized-test.log
  GRANTED_EXIT=${PIPESTATUS[0]}
  set -e
  echo "Preconditioned Photos workflow exit: $GRANTED_EXIT (original permission result retained)"
fi
# Revocation is a distinct supported disposable test precondition, not an
# assertion that the real Don't Allow remote-focus interaction succeeded.
xcrun simctl terminate "$DEVICE" 100mango.QRCatcher || true
xcrun simctl privacy "$DEVICE" revoke photos 100mango.QRCatcher
set +e
"${BASE[@]}" -only-testing:QRCatcherTVUITests/QRCatcherTVUITests/testExplicitlyRevokedPhotosRecovery -resultBundlePath TVRevokedUIResults.xcresult | tee tv-revoked-test.log
REVOKED_EXIT=${PIPESTATUS[0]}
set -e
if [ "$ORIGINAL_EXIT" -ne 0 ]; then exit "$ORIGINAL_EXIT"; fi
exit "$REVOKED_EXIT"
