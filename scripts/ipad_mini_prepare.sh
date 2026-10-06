#!/bin/bash
set -euo pipefail
set -euo pipefail
test "$GITHUB_REPOSITORY" = 100mango/QRCatcher
python3 scripts/ipad_mini_setup.py source-identity
test "$GITHUB_WORKFLOW_SHA" = "$GITHUB_SHA"
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git diff --exit-code HEAD --
SOURCE_HEAD=$(git rev-parse HEAD)
echo "Tested commit: $SOURCE_HEAD"
SOURCE_TREE=$(git rev-parse 'HEAD^{tree}')
echo "Tested tree: $SOURCE_TREE"
if [ "$GITHUB_REF" = refs/heads/codex/mini-managed-full-row ]; then
  python3 scripts/diagnostic_mini_managed_route.py prepared "$SOURCE_HEAD" "$SOURCE_TREE"
fi
if [ "$GITHUB_REF" = refs/heads/codex/ios-original-release ]; then
  python3 scripts/ios_original_release_route.py prepared "$SOURCE_HEAD" "$SOURCE_TREE"
fi
shasum -a 256 .github/workflows/apple-platforms.yml
sw_vers
xcodebuild -version
xcodebuild -version | grep '27A266a'
test "$(uname -m)" = arm64
python3 scripts/verify_portable_source.py
python3 scripts/materialize_qr_fixtures.py
python3 scripts/materialize_mac_icons.py
python3 scripts/materialize_ipad_icons.py
xcrun swift scripts/materialize_native_icons.swift
if [ "$GITHUB_REF" = refs/heads/codex/ios-original-release ]; then
  python3 scripts/generate_project.py --profile ios-only
  git diff --exit-code -- QRCatcher.xcodeproj QRCatcher-iOS-Only.xcodeproj
else
  python3 scripts/generate_project.py
  git diff --exit-code -- QRCatcher.xcodeproj
fi
plutil -lint QRCatcherMac/Info.plist QRCatcherVision/Info.plist QRCatcher/Info.plist QRCatcher/PrivacyInfo.xcprivacy
if [ "$GITHUB_REF" = refs/heads/codex/ios-original-release ]; then
  xcodebuild -list -project QRCatcher-iOS-Only.xcodeproj
else
  xcodebuild -list -project QRCatcher.xcodeproj
fi

python3 scripts/validate_evidence_budget.py --validate-allocation
git diff --exit-code 9abdd5e8150b47fc176d203db23db10854c81188 -- QRCatcher/QR.xcdatamodeld QRCatcher/QRHistoryStore.m QRCatcher/URLEntity.h QRCatcher/URLEntity.m
