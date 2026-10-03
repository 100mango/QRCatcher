#!/bin/bash
set -euo pipefail
# Ephemeral ad-hoc signing only. No identity lookup, provisioning update, team,
# profile, certificate, keychain or system-security setting is created/changed.
xcodebuild build-for-testing -project QRCatcher.xcodeproj -scheme QRCatcherMacSandbox -configuration Debug -derivedDataPath build/MacSandbox -destination 'platform=macOS,arch=arm64' ARCHS=arm64 CODE_SIGNING_ALLOWED=YES CODE_SIGNING_REQUIRED=YES CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM= PROVISIONING_PROFILE_SPECIFIER= | tee mac-sandbox-build.log
APP=build/MacSandbox/Build/Products/Debug/QRCatcherMac.app
codesign --verify --deep --strict "$APP"
codesign -d --entitlements - --xml "$APP" > build/mac-sandbox-entitlements.plist
codesign -dv "$APP" 2> build/mac-sandbox-signature.txt
grep 'Signature=adhoc' build/mac-sandbox-signature.txt
python3 - <<'PY'
import plistlib
from pathlib import Path
values=plistlib.loads(Path('build/mac-sandbox-entitlements.plist').read_bytes())
required={'com.apple.security.app-sandbox','com.apple.security.files.user-selected.read-write','com.apple.security.device.camera'}
assert all(values.get(k) is True for k in required)
# Xcode may inject get-task-allow in this Debug-only XCTest product. There are
# no network, general Documents/Pictures, App Group or Photos-library grants.
assert set(values) <= required | {'com.apple.security.get-task-allow'}, values
print('VERIFIED_EPHEMERAL_SANDBOX_ENTITLEMENTS',values,flush=True)
PY
xcodebuild test-without-building -project QRCatcher.xcodeproj -scheme QRCatcherMacSandbox -configuration Debug -derivedDataPath build/MacSandbox -destination 'platform=macOS,arch=arm64' ARCHS=arm64 -parallel-testing-enabled NO -collect-test-diagnostics never -test-timeouts-enabled YES -default-test-execution-time-allowance 90 -maximum-test-execution-time-allowance 150 -resultBundlePath MacSandboxResults.xcresult CODE_SIGNING_ALLOWED=NO | tee mac-sandbox-test.log
