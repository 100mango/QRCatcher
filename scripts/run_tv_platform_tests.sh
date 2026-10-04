#!/bin/bash
set -euo pipefail
python3 scripts/owned_process_barrier.py --check
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
if [ "$ORIGINAL_EXIT" -eq 126 ]; then exit 126; fi
python3 scripts/owned_process_barrier.py --check
GRANTED_EXIT=1
# Preserve the original red result. Only an observed exact QRCatcher Photos
# dialog/focus failure authorizes this separate synthetic per-app setup lane.
if [ "$ORIGINAL_EXIT" -ne 0 ] && grep -q QRCATCHER_TV_EXACT_PERMISSION_FOCUS_BLOCKED tv-test.log; then
  echo 'Separate lane: explicit synthetic simulator Photos grant; original prompt automation remains failed.'
  python3 -u scripts/run_bounded.py 30 xcrun simctl terminate "$DEVICE" 100mango.QRCatcher || true
  python3 scripts/owned_process_barrier.py --check
  python3 -u scripts/run_bounded.py 30 xcrun simctl privacy "$DEVICE" grant photos 100mango.QRCatcher
  set +e
  "${BASE[@]}" -only-testing:QRCatcherTVUITests/QRCatcherTVUITests/testExplicitlyPreconditionedPhotosDecodeExportAndReopen -resultBundlePath TVAuthorizedUIResults.xcresult | tee tv-authorized-test.log
  GRANTED_EXIT=${PIPESTATUS[0]}
  set -e
  if [ "$GRANTED_EXIT" -eq 126 ]; then exit 126; fi
  python3 scripts/owned_process_barrier.py --check
  echo "Preconditioned Photos workflow exit: $GRANTED_EXIT (original permission result retained)"
fi
SIZE_PROBE_EXIT=2
if [ "$ORIGINAL_EXIT" -eq 0 ] || [ "$GRANTED_EXIT" -eq 0 ]; then
  echo 'TV_SIZE_CLEANUP_UNCONFIRMED=true' >> "$GITHUB_ENV"
  set +e
  python3 -u scripts/run_bounded.py 600 python3 -u scripts/run_native_size_case.py tv "$DEVICE" | tee tv-largest-test.log
  SIZE_PROBE_EXIT=${PIPESTATUS[0]}
  set -e
  if [ "$SIZE_PROBE_EXIT" -ne 0 ] && [ "$SIZE_PROBE_EXIT" -ne 2 ]; then exit "$SIZE_PROBE_EXIT"; fi
  echo 'TV_SIZE_CLEANUP_UNCONFIRMED=false' >> "$GITHUB_ENV"
fi
python3 scripts/owned_process_barrier.py --check
# Revocation is a distinct supported disposable test precondition, not an
# assertion that the real Don't Allow remote-focus interaction succeeded.
python3 -u scripts/run_bounded.py 30 xcrun simctl terminate "$DEVICE" 100mango.QRCatcher || true
python3 scripts/owned_process_barrier.py --check
python3 -u scripts/run_bounded.py 30 xcrun simctl privacy "$DEVICE" revoke photos 100mango.QRCatcher
set +e
"${BASE[@]}" -only-testing:QRCatcherTVUITests/QRCatcherTVUITests/testExplicitlyRevokedPhotosRecovery -resultBundlePath TVRevokedUIResults.xcresult | tee tv-revoked-test.log
REVOKED_EXIT=${PIPESTATUS[0]}
set -e
if [ "$ORIGINAL_EXIT" -ne 0 ]; then exit "$ORIGINAL_EXIT"; fi
if [ "$REVOKED_EXIT" -ne 0 ]; then exit "$REVOKED_EXIT"; fi
exit "$SIZE_PROBE_EXIT"
