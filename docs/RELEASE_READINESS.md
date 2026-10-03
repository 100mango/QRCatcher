# QRCatcher modernization and release gates

## Identity and retained functionality

- Original App Store ID: **993170818** (historical README evidence and App Store Connect account check on 2026-10-03)
- Bundle identifier: **100mango.QRCatcher**, unchanged
- Native Objective-C app: QR camera scanning/decoding, text results, web links, persistent scan history, history selection and swipe deletion
- Original scanning artwork, tab icons and ripple animation retained; native safe-area layout, Dynamic Type, Reduce Motion and labelled controls replace device-size assumptions
- Chinese interface retained through Simplified Chinese localization, with English fallback
- Localized, VoiceOver-labelled Privacy Policy entry is available from both tabs and opens https://100mango.github.io/app-privacy/ in an in-app Safari view with an explicit Done dismissal
- Text results can now be copied and stored as well as web links. A scanned URL requires an explicit tap; QR content cannot launch arbitrary URL schemes automatically

## Storage compatibility

The original `QR.xcdatamodeld/QR.xcdatamodel/contents` is unchanged. Entity `URLEntity` and its optional `url` (String), `createDate` (Date) attributes retain their model identity. The SQLite location remains **Documents/coredata.sqlite**. Existing dates, URLs and ordering information are retained. New writes and deletions are saved immediately, and scene backgrounding saves pending work.

Both automatic store migration and inferred mapping remain enabled. No schema change is necessary in this update. Initialization failures leave the existing SQLite file intact and show an error instead of aborting or deleting the user's history. UI tests use `ui-testing.sqlite` only in Debug and cannot reset production history. Release builds contain no UI-test launch seams.

The automated legacy test writes a store with the unchanged original schema using SQLite, detaches it, opens it through the updated store, verifies exact URL/date values, adds a record and reopens it. This establishes schema/reopening compatibility, not provenance from a 2015 device. Before release, test upgrading an archived production build with populated history and a backed-up representative old store, including an interrupted save and low-storage failure.

## Build and automated verification

No CocoaPods install is required. Masonry 0.6.1 was an unused import; the app used no Masonry APIs. The Pod integration was removed, and no third-party implementation was copied. Open `QRCatcher.xcworkspace` or `QRCatcher.xcodeproj` and use the shared **QRCatcher** scheme. Minimum deployment target is iOS 15.0. Project structure is reproducibly generated with `python3 scripts/generate_project.py`.

`.github/workflows/ios.yml` uses one standard `xcode-27` runner, pins `/Applications/Xcode_27.app/Contents/Developer`, and fails unless it reports stable Xcode 27.0 build 27A266a and an installed iOS 27.0 iPhone simulator. It logs OS, SDK and runtime versions first. It runs the entire unit/UI suite serially on an iPhone 18 Pro Max, then repeats UI coverage on the smaller iPhone 17e. It reports both xcresult summaries in logs, builds an unsigned device Release, verifies bundle ID/minimum OS/absence of Debug test seams, and runs Clang static analysis. Test targets require iOS 17+ because the current XCTest library requires that version; the shipping application keeps its iOS 15 deployment target. It disables automatic verbose failure sysdiagnoses to avoid long post-suite collection stalls, while retaining test failures, test results, bounded process/simulator diagnostics and synthetic screenshot evidence in logs. It never uploads artifacts, accesses signing secrets, archives for distribution or submits to App Store Connect. New commits cancel superseded app runs.

### Unit regression cases

- Core Image QR generation and decoding of URL and Unicode text fixtures
- Empty QR/image handling and HTTP/HTTPS URL classification; reject script/file/telephone schemes and credential-containing URLs
- History uniqueness, timestamps, empty payload rejection and persistent deletion
- Original-schema SQLite reopening with exact data preservation
- Corrupt SQLite failure without deleting or replacing the source file

### Simulator UI cases

- Production UIScene launch/background/foreground navigation without any UI-test camera stub; simulator may present its real permission prompt, but has no camera hardware

- Denied camera explanation/Settings affordance and empty history, including Privacy Policy entry visibility, open/dismiss and return to the denied state
- Production QR decode/result/save path via Debug-only generated QR fixture
- Plain text cannot offer website opening; website scan remains in-app until explicit action
- Relaunch/background/foreground history persistence and deletion persistence
- Cancel/reopen navigation and repeated scan flow
- Accessibility XXXL result wrapping with reachable tab navigation and Scan Again

Permission states are injected for determinism because simulator camera hardware is unavailable. These tests do **not** establish physical camera performance, actual OS permission dialogue behavior or interruption recovery. A passing newest-iOS run does not prove runtime support on iOS 15; older OS/device coverage is a separate gate.

## Required release gates

1. Observe passing CI for the exact final commit; inspect warnings and actual runtime/version evidence
2. Real iPhone: clean-install permission prompt, deny, Settings re-enable, camera foreground/background, tab switching, interruption, repeated scan, Unicode and malformed QR, close/far/low-light focus; verify no automatic external launch
3. Upgrade archived published build; validate old history, delete/add/relaunch and failure recovery; retain a backup before migration checks
4. Test supported oldest iOS on physical hardware or available compatible simulator; VoiceOver, Reduce Motion, large text, small and large phone layouts
5. Confirm the recovered **1024×1024 marketing icon** visually against the approved store identity. The asset now included is Apple-served artwork for this published app, recovered on 2026-10-03 without local resizing or redesign. It is an Apple CDN derivative, not a proven designer-original source. Existing device icons remain unchanged; the older store artwork has a slightly different glow
6. Verify App Store Connect ownership, current released version/build, signing team, current privacy declarations, support/privacy-policy URLs, screenshots, export-compliance answers and review notes. The App Store Connect account check on 2026-10-03 confirmed the existing release is version 1.0/build 1; candidate version 1.1/build 2 is higher, and must be rechecked immediately before upload
7. Review the privacy manifest against the final binary. Current app has no tracking, network SDK or collected data, and declares no directly used required-reason APIs; all scan history remains local. Opening a chosen website exposes that request to the destination/browser
8. Sign/archive/upload only through explicitly authorized Apple account access. Resolve agreements/credentials through the account owner. Keep this PR in draft and do not merge/publish without release approval

## Toolchain references

- https://github.com/actions/runner-images/blob/main/images/macos/xcode-27-arm64-Readme.md
- https://developer.apple.com/documentation/uikit/transitioning-to-the-uikit-scene-based-life-cycle
- https://developer.apple.com/documentation/technotes/tn3208-preparing-your-apps-launch-screen-to-meet-app-store-requirements
- https://developer.apple.com/documentation/avfoundation/avcam-building-a-camera-app


## Recovered marketing icon provenance

- Resource: `QRCatcher/Images.xcassets/AppIcon.appiconset/marketing1024.png`
- Source: https://is1-ssl.mzstatic.com/image/thumb/Purple2/v4/79/4a/49/794a49fc-e040-14bf-0cf9-baa32b28c58e/pr_source.png/1024x1024bb.png
- Retrieved via the existing App Store Connect record's artwork on 2026-10-03, then visually verified against the QRCatcher store identity
- Dimensions/format: 1024 × 1024, opaque RGB PNG
- SHA-256: `dc2c12171d08a7d5cc51a66dc212601deccca7ab0d8d6d3c315d0da2ffa403d4`
- Provenance limit: Apple-served 1024px derivative; original designer master has not been recovered


The approved bilingual privacy policy is published at https://100mango.github.io/app-privacy/ and linked from both app tabs. Publication and HTTP/body verification were completed on 2026-10-03. Its implementation does not change QR storage, add tracking, or introduce login. The policy-inclusive commit requires a fresh full CI result; earlier green results alone do not validate this later change.


## Exact-source release provenance

The workflow pins official `actions/checkout` v7.0.1 at commit `3d3c42e5aac5ba805825da76410c181273ba90b1`, disables persisted credentials, and explicitly checks out `github.sha`. On manual `workflow_dispatch` runs only, the named `Verify exact tested commit` and `Verify tested source stayed unchanged` steps assert the checked-out commit and unchanged tracked source and log the tree plus workflow SHA-256. Ordinary PR runs may test a synthetic merge commit; they remain useful regression evidence but do not satisfy the exact frozen-candidate signing gate. No workflow input can override the revision.

The unsigned device build also records every embedded `.framework` bundle and executable hash, or an explicit empty inventory. A final manual run must match the frozen candidate, reviewed workflow digest, run/attempt/repository, both successful provenance steps and every real build/test/analyzer step before signing can be considered. This workflow itself contains no signing or credential access.
