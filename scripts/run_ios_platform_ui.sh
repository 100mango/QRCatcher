#!/bin/bash
set -euo pipefail
DEVICE=$1
RESULT=$2
CLASS=$3
PREVIOUS=${4:-}
if [ -n "$PREVIOUS" ]; then xcrun simctl shutdown "$PREVIOUS" || true; fi
xcrun simctl boot "$DEVICE" || true
xcrun simctl bootstatus "$DEVICE" -b
if [ "$CLASS" = QRCatcherPadUITests ]; then
  # This is a genuine simulator Photos asset consumed by the production PHPicker.
  xcrun simctl addmedia "$DEVICE" Tests/Fixtures/unicode.png
fi
xcodebuild test -project QRCatcher.xcodeproj -scheme QRCatcher -configuration Debug -derivedDataPath build/iOS -destination "platform=iOS Simulator,id=$DEVICE" -only-testing:"QRCatcherUITests/$CLASS" -parallel-testing-enabled NO -collect-test-diagnostics never -test-timeouts-enabled YES -default-test-execution-time-allowance 120 -maximum-test-execution-time-allowance 180 -resultBundlePath "$RESULT" CODE_SIGNING_ALLOWED=NO
