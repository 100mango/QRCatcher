# QRCatcher modernization and release gates

## Identity and retained functionality

- Original App Store ID: **993170818** (historical README evidence; current App Store Connect record still requires verification)
- Bundle identifier: **100mango.QRCatcher**, unchanged
- Native Objective-C app: QR camera scanning/decoding, text results, web links, persistent scan history, history selection and swipe deletion
- Original scanning artwork, tab icons and ripple animation retained; native safe-area layout, Dynamic Type, Reduce Motion and labelled controls replace device-size assumptions
- Chinese interface retained through Simplified Chinese localization, with English fallback
- Text results can now be copied and stored as well as web links. A scanned URL requires an explicit tap; QR content cannot launch arbitrary URL schemes automatically

## Storage compatibility

The original `QR.xcdatamodeld/QR.xcdatamodel/contents` is unchanged. Entity `URLEntity` and its optional `url` (String), `createDate` (Date) attributes retain their model identity. The SQLite location remains **Documents/coredata.sqlite**. Existing dates, URLs and ordering information are retained. New writes and deletions are saved immediately, and scene backgrounding saves pending work.

Both automatic store migration and inferred mapping remain enabled. No schema change is necessary in this update. Initialization failures leave the existing SQLite file intact and show an error instead of aborting or deleting the user's history. UI tests use `ui-testing.sqlite` only in Debug and cannot reset production history. Release builds contain no UI-test launch seams.

The automated legacy test writes a store with the unchanged original schema using SQLite, detaches it, opens it through the updated store, verifies exact URL/date values, adds a record and reopens it. This establishes schema/reopening compatibility, not provenance from a 2015 device. Before release, test upgrading an archived production build with populated history and a backed-up representative old store, including an interrupted save and low-storage failure.

## Build and automated verification

No CocoaPods install is required. Masonry 0.6.1 was an unused import; the app used no Masonry APIs. The Pod integration was removed, and no third-party implementation was copied. Open `QRCatcher.xcworkspace` or `QRCatcher.xcodeproj` and use the shared **QRCatcher** scheme. Minimum deployment target is iOS 15.0. Project structure is reproducibly generated with `python3 scripts/generate_project.py`.

`.github/workflows/ios.yml` uses one standard `xcode-27` runner, pins `/Applications/Xcode_27.app/Contents/Developer`, and fails unless it reports stable Xcode 27.0 build 27A266a and an installed iOS 27.0 iPhone simulator. It logs OS, SDK and runtime versions first. It runs the entire unit/UI suite serially, reports the xcresult summary in logs, and then builds an unsigned device Release. It never uploads artifacts, accesses signing secrets, archives for distribution or submits to App Store Connect. New commits cancel superseded app runs.

### Unit regression cases

- Core Image QR generation and decoding of URL and Unicode text fixtures
- Empty QR/image handling and HTTP/HTTPS URL classification; reject script/file/telephone schemes and credential-containing URLs
- History uniqueness, timestamps, empty payload rejection and persistent deletion
- Original-schema SQLite reopening with exact data preservation
- Corrupt SQLite failure without deleting or replacing the source file

### Simulator UI cases

- Production UIScene launch/background/foreground navigation without any UI-test camera stub; simulator may present its real permission prompt, but has no camera hardware

- Denied camera explanation/Settings affordance and empty history
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
5. Obtain an original high-resolution **1024×1024 marketing icon**. The repository's largest existing icon is only 180×180; an upscaled copy is not an original high-resolution source
6. Verify App Store Connect ownership, current released version/build, signing team, current privacy declarations, support/privacy-policy URLs, screenshots, export-compliance answers and review notes. Proposed version 1.1/build 2 are placeholders until checked against the live record
7. Review the privacy manifest against the final binary. Current app has no tracking, network SDK or collected data, and declares no directly used required-reason APIs; all scan history remains local. Opening a chosen website exposes that request to the destination/browser
8. Sign/archive/upload only through explicitly authorized Apple account access. Resolve agreements/credentials through the account owner. Keep this PR in draft and do not merge/publish without release approval

## Toolchain references

- https://github.com/actions/runner-images/blob/main/images/macos/xcode-27-arm64-Readme.md
- https://developer.apple.com/documentation/uikit/transitioning-to-the-uikit-scene-based-life-cycle
- https://developer.apple.com/documentation/technotes/tn3208-preparing-your-apps-launch-screen-to-meet-app-store-requirements
- https://developer.apple.com/documentation/avfoundation/avcam-building-a-camera-app
