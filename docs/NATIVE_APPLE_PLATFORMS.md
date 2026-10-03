# Native Apple-platform expansion

## Baseline and current milestone

The frozen iOS base is `9abdd5e8150b47fc176d203db23db10854c81188`. Work is isolated on `codex/apple-platforms`; the iOS modernization branch is unchanged. This milestone implements a separate native macOS executable, `QRCatcherMac`, with the original `100mango.QRCatcher` identity. It is not a Catalyst or iPhone compatibility build. The native iPad split workflow is implemented in this branch and is under validation. Vision has an initial import-first executable slice awaiting compiler/runtime proof. Watch and TV remain staged and are not implemented.

Mac deployment floor is 13.0. Build verification covers both arm64 and x86_64; runtime XCTest proof must be reported separately for each executed architecture. A compile is not runtime proof. All builds here are unsigned and no Store records, signing resources or persistent capabilities are created.

## Product workflow

- Open an image with the native file panel, select an image from Photos, drop an image/file, or paste an image from the clipboard
- Decode real pixels locally using the shared Core Image QR decoder, normalize EXIF orientation at the ImageIO boundary, and display a result without opening anything automatically
- Save every decoded result in local history, preserve existing duplicate semantics, search/select history, and copy a result
- Open only explicitly chosen HTTP/HTTPS links without embedded credentials in the system browser
- Export a real rescannable PNG with a four-module quiet zone, or export all history as versioned JSON with original timestamps and order
- Reopen the app and read persisted history; failed store loads retain the original bytes and still allow scan/copy/export of a current result
- Choose an available desktop camera, request camera access, decode bounded real video frames and stop after a result. Absence, denial, interruptions and connection changes are explicit, with import fallback and retry

New Mac history lives in Application Support/100mango.QRCatcher/coredata.sqlite. When the OS provides the native app with a genuinely app-owned container that already holds the prior Documents/coredata.sqlite, the resolver retains that existing location in place; ambiguous dual stores require an explicit choice. Phone history remains at its existing Documents/coredata.sqlite. No automatic transfer, account, backend or sync is introduced. The original QR.xcdatamodeld, URLEntity and storage adapter implementation are unchanged. The shared domain value projection is Foundation-only. The UIKit codec is a thin adapter over the extracted Core Graphics/Core Image implementation.

## Test contract

On macOS, run `python3 scripts/materialize_qr_fixtures.py` and `python3 scripts/materialize_mac_icons.py` before opening/building the project. The icon script derives the standard Mac icon sizes from the retained, SHA-256-checked artwork using Apple’s local sips tool; it does not redesign the artwork. The independent checked-in fixtures use ReportLab QR encoding, include ASCII/Unicode/rotated/multiple/invalid input, and verify their recorded SHA-256. Rebuilding fixtures is an intentional development step; production never uses them.

Run `python3 scripts/generate_project.py` after changing source inventory. The generated Xcode project is deterministic and CI rejects a difference.

The `Native Apple platforms` workflow has one public `xcode-27` job with bounded execution and evidence output. It checks exact source/tree/toolchain, unsigned universal Mac Release, DEBUG hook exclusion, Mac unit/UI XCTest, unsigned iOS Release, original model/store preservation and iOS unit/codec-equivalence regression. It exports bounded synthetic screenshots after Mac XCTest and logs each screenshot's SHA-256 before transfer. The Mac evidence artifact is capped at 6 MB and retained for one day. A second synthetic phone/iPad/Vision artifact is also capped at 6 MB, with a combined hard cap of 20 MB. No full xcresult archive is uploaded.

Native UI test import and export use actual NSOpenPanel/NSSavePanel; decoding, storage and exports are production code. The only DEBUG test hook chooses an isolated store path. No real user store is deleted, TCC database is altered or OS security prompt bypassed.

Physical camera capture/denial/disconnect, Photos-account integration, oldest supported OS launch, x86_64 runtime, signed sandbox and distribution remain separately recorded gates unless concrete evidence is later supplied. No App Store accessibility/privacy compatibility claims follow merely from these tests.

Native UI tests pin the actual app URL to the adjacent Debug product and assert the running process bundle URL, executable URL, PID and executable SHA-256. Tests also cover Simplified Chinese import/copy/export/reopen, real window-edge resizing, button-title containment and bounded cancellation of repeatedly superseded image imports. Runtime warnings from re-entrant SwiftUI publication block the evidence gate.

## Native iPad validation slice

The original iOS target now includes device family 2 and all iPad orientations, retaining the iPhone portrait contract and iOS 15 floor. iPad uses a native split history/scanner interface, explicit saved-record selection without a new history write, window-orientation camera transforms, Files/Photos image import, keyboard actions and anchored QR-image sharing. Imported image operations run serially with cancellation/generation checks. Action buttons calculate their full multiline title height; the compact view-host tests inspect 320×568 and 568×320 at the largest Dynamic Type size, with title containment and actual rendered attachments. These are view-layout tests, not a claim of an iOS 15.5 device/runtime launch.

The same standard cloud job runs the existing phone UI class on Pro Max and SE3, plus the separate iPad UI class on 13-inch Pro and mini. Its real photo-import test consumes an independent QR PNG added to the simulator Photos library with the supported simctl addmedia command. It does not replace the production PHPicker or decoder. A second synthetic evidence artifact is capped at 6 MiB for one day; both artifacts together are capped at 20 MiB, with actual sizes and any omissions recorded. No full result archive, signed app, credential or personal library asset is uploaded.

Before building the iPad target, also run `python3 scripts/materialize_ipad_icons.py` on macOS to derive the required iPad icon sizes from the unchanged retained artwork.

## App-owned legacy data locations and a separate Store-upgrade gate

The native history resolver checks the old Documents/coredata.sqlite location only when the operating system supplies an app-owned sandbox home, the standard Documents URL is inside that home, and the main file plus WAL/SHM paths do not escape through links. An unsandboxed developer build does not inspect general Documents or another container. If only the original store exists, the original unchanged adapter opens it in place; no SQLite copying, moving or deletion is performed. If both original and native stores exist, history remains blocked until the person explicitly selects one. That choice is stored separately, and both databases remain present. Unreadable stores or settings do not silently create an empty replacement.

Isolated tests exercise a synthetic same-container original store with actual WAL/SHM files, duplicate values and dates, an ambiguous two-store case, an unreadable original and an escaping-link refusal. These tests do not prove App Store container inheritance. Apple documents that sandbox directory APIs return container-relative locations, and that macOS14+ associates containers with code signatures: [App Sandbox file access](https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox), [standard Documents directory](https://developer.apple.com/documentation/foundation/url/documentsdirectory).

A July2026 Apple DTS response does not guarantee the exact iOS-on-Mac to native-Mac replacement/container behavior: [Apple Developer Forums discussion](https://developer.apple.com/forums/thread/838374). Whether QRCatcher was actually available as an iOS app on Mac, and the signed Store-upgrade data path, remain release gates. No App Group, migration entitlement, container-scanning workaround or signing identity has been introduced by this implementation.

The native Mac target requests `ASSETCATALOG_COMPILER_STANDALONE_ICON_BEHAVIOR=all` so the loose ICNS also contains the complete icon size family. Apple's default is a smaller representative subset, while the complete catalog lives in Assets.car: [Xcode build-settings reference](https://developer.apple.com/documentation/xcode/build-settings-reference). Package validation decodes the actual compiled ICNS through ImageIO and records its sizes and SHA-256; it does not assume an iconutil extraction filename.


## Native visionOS first runtime slice

`QRCatcherVision` is an unsigned native visionOS executable with import-first
SwiftUI Files/Photos/drop input, the shared bounded image decoder, original
Core Data adapter, local history/reopen, copy, explicit safe browser action and
PNG/JSON exports. It does not request passthrough-camera access. The first lane
boots an actually installed visionOS 27 simulator on the standard `xcode-27`
runner with a bounded timeout before attempting hosted unit tests and an actual
Photos import UI flow. SDK acceptance is not runtime proof; a failed boot is
reported separately from compilation or app-test failures. Native Vision pixels,
Chinese localization, icon packaging and export UI verification remain gates
until recorded successful evidence exists. No simulator/runtime downloads or
paid runner fallback are performed.
