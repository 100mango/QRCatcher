#!/bin/bash
set -euo pipefail
python3 scripts/diagnostic_mac_public_metadata_route.py validate-target
# Ephemeral ad-hoc signing only. No identity lookup, provisioning update, team,
# profile, certificate, keychain or system-security setting is created/changed.
python3 -u scripts/run_bounded.py 240 xcodebuild build-for-testing -project QRCatcher.xcodeproj -scheme QRCatcherMacSandbox -configuration Debug -derivedDataPath build/MacSandbox -destination 'platform=macOS,arch=arm64' ARCHS=arm64 CODE_SIGNING_ALLOWED=YES CODE_SIGNING_REQUIRED=YES CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM= PROVISIONING_PROFILE_SPECIFIER= | tee mac-sandbox-build.log
APP=build/MacSandbox/Build/Products/Debug/QRCatcherMac.app
# XCTest's hosted unit instrumentation injects broad read/Mach exceptions. The
# sandbox gate uses external XCUI only, and re-signs this app with exactly the
# source entitlements plus Debug attach support. This removes those exceptions.
python3 - <<'PYCODE'
import plistlib
from pathlib import Path
values=plistlib.loads(Path('QRCatcherMac/QRCatcherMac.entitlements').read_bytes())
values['com.apple.security.get-task-allow']=True
Path('build/mac-sandbox-runtime.entitlements').write_bytes(plistlib.dumps(values))
PYCODE
xcrun swift scripts/prepare_sandbox_boundary.swift build/MacSandbox/Build/Products/Debug/qrcatcher-boundary-control.json
trap 'python3 - <<"CLEANUP"
import json,uuid
from pathlib import Path
import sys
sys.path.insert(0,"scripts")
from owned_process_barrier import blocked
if blocked():raise SystemExit(126)
value=json.loads(Path("build/MacSandbox/Build/Products/Debug/qrcatcher-boundary-control.json").read_text())
folder=Path(value["folder"])
assert folder.parent==Path.home() and folder.name.startswith("QRCatcherBoundaryProbe-")
uuid.UUID(folder.name.removeprefix("QRCatcherBoundaryProbe-"))
(folder/"synthetic-read.txt").unlink()
folder.rmdir()
CLEANUP
' EXIT
codesign --force --sign - --timestamp=none --entitlements build/mac-sandbox-runtime.entitlements "$APP"
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
python3 -u scripts/run_bounded.py 600 env TEST_RUNNER_QRCATCHER_MAC_PUBLIC_METADATA_DIAGNOSTIC=1 xcodebuild test-without-building -project QRCatcher.xcodeproj -scheme QRCatcherMacSandbox -configuration Debug -derivedDataPath build/MacSandbox -destination 'platform=macOS,arch=arm64' ARCHS=arm64 -parallel-testing-enabled NO -collect-test-diagnostics never -test-timeouts-enabled YES -default-test-execution-time-allowance 90 -maximum-test-execution-time-allowance 150 -only-testing:QRCatcherMacUITests/QRCatcherMacUITests/testNativeWindowResizeKeepsFullActionTitles -only-testing:QRCatcherMacUITests/QRCatcherMacUITests/testChineseCriticalFlow -resultBundlePath MacSandboxResults.xcresult CODE_SIGNING_ALLOWED=NO | tee mac-sandbox-test.log
