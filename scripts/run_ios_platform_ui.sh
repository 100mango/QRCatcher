#!/bin/bash
set -euo pipefail
DEVICE=$1
RESULT=$2
CLASS=$3
shift 3
for PREVIOUS in "$@"; do
  if [ -n "$PREVIOUS" ]; then xcrun simctl shutdown "$PREVIOUS" || true; fi
done
xcrun simctl boot "$DEVICE" || true
xcrun simctl bootstatus "$DEVICE" -b
if [ "$CLASS" = QRCatcherPadUITests ]; then
  # This is a genuine simulator Photos asset consumed by the production PHPicker.
  xcrun simctl addmedia "$DEVICE" Tests/Fixtures/unicode.png
fi
xcodebuild test-without-building -project QRCatcher.xcodeproj -scheme QRCatcher -configuration Debug -derivedDataPath build/iOS -destination "platform=iOS Simulator,id=$DEVICE" -only-testing:"QRCatcherUITests/$CLASS" -parallel-testing-enabled NO -collect-test-diagnostics never -test-timeouts-enabled YES -default-test-execution-time-allowance 120 -maximum-test-execution-time-allowance 180 -resultBundlePath "$RESULT" CODE_SIGNING_ALLOWED=NO | tee "${RESULT%.xcresult}.log"
