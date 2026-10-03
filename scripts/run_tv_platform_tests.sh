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
xcrun simctl boot "$DEVICE"
xcrun simctl bootstatus "$DEVICE" -b
# Only this independent synthetic QR photo is imported; no account or cloud setup.
xcrun simctl addmedia "$DEVICE" Tests/Fixtures/unicode.png
xcodebuild test-without-building -project QRCatcher.xcodeproj -scheme QRCatcherTV -configuration Debug -derivedDataPath build/TVTests -destination "platform=tvOS Simulator,id=$DEVICE" -parallel-testing-enabled NO -collect-test-diagnostics never -test-timeouts-enabled YES -default-test-execution-time-allowance 90 -maximum-test-execution-time-allowance 150 -resultBundlePath TVTestResults.xcresult CODE_SIGNING_ALLOWED=NO | tee tv-test.log
