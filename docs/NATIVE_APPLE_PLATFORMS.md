# Native Apple-platform expansion

## Baseline and current milestone

The frozen iOS base is `9abdd5e8150b47fc176d203db23db10854c81188`. Work is isolated on `codex/apple-platforms`; the iOS modernization branch is unchanged. This milestone implements a separate native macOS executable, `QRCatcherMac`, with the original `100mango.QRCatcher` identity. It is not a Catalyst or iPhone compatibility build. At exact checkpoint `0eebd8f` / run `37124136942`, iOS units12, Pro Max UI8 and native iPad Pro UI3 passed. Vision compiled and passed4 hosted tests; real Photos/decode/copy/reopen assertions ran but its UI test exceeded the initial time allowance. TV compiled and passed4 hosted tests; the UI stopped at the actual system Photos permission dialog. The following changes add a substantive Watch source slice awaiting its first compiler/runtime pass. The combined workflow is not yet green.

Mac deployment floor is 13.0. Build verification covers both arm64 and x86_64; runtime XCTest proof must be reported separately for each executed architecture. A compile is not runtime proof. Release verification remains unsigned. A separate local ad-hoc Debug sandbox test is described below; no Store records, Apple-account signing resources or registered persistent capabilities are created.

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

The `Native Apple platforms` workflow has eight fresh public `xcode-27` VM rows, serialized with `max-parallel: 1`, bounded execution, and exact-head evidence. It checks exact source/tree/toolchain, unsigned universal Mac Release, DEBUG hook exclusion, Mac unit/UI XCTest, unsigned iOS Release, original model/store preservation and iOS unit/codec-equivalence regression. It exports bounded synthetic screenshots after Mac XCTest and logs each screenshot's SHA-256 before transfer. The Mac artifact is allocated 3,000,000 bytes; each other platform/device row is allocated 2,000,000 bytes, all with one-day retention. The 17,000,000-byte sum is below the strict 20,000,000-byte whole-run cap. No full xcresult archive is uploaded.

Native UI test import and export use actual NSOpenPanel/NSSavePanel; decoding, storage and exports are production code. The only DEBUG test hook chooses an isolated store path. No real user store is deleted, TCC database is altered or OS security prompt bypassed.

Physical camera capture/denial/disconnect, Photos-account integration, oldest supported OS launch, x86_64 runtime, signed sandbox and distribution remain separately recorded gates unless concrete evidence is later supplied. No App Store accessibility/privacy compatibility claims follow merely from these tests.

Native UI tests pin the actual app URL to the adjacent Debug product and assert the running process bundle URL, executable URL, PID and executable SHA-256. Tests also cover Simplified Chinese import/copy/export/reopen, real window-edge resizing, button-title containment and bounded cancellation of repeatedly superseded image imports. Runtime warnings from re-entrant SwiftUI publication block the evidence gate.

## Native iPad validation slice

The original iOS target now includes device family 2 and all iPad orientations, retaining the iPhone portrait contract and iOS 15 floor. iPad uses a native split history/scanner interface, explicit saved-record selection without a new history write, window-orientation camera transforms, Files/Photos image import, keyboard actions and anchored QR-image sharing. Imported image operations run serially with cancellation/generation checks. Action buttons calculate their full multiline title height; the compact view-host tests inspect 320×568 and 568×320 at the largest Dynamic Type size, with title containment and actual rendered attachments. These are view-layout tests, not a claim of an iOS 15.5 device/runtime launch.

Fresh standard VMs run the existing phone UI class on Pro Max and SE3, plus the separate iPad UI class on 13-inch Pro and mini, one row at a time. Its real photo-import test consumes an independent QR PNG added to the simulator Photos library with the supported simctl addmedia command. It does not replace the production PHPicker or decoder. Each device row has a 2,000,000-byte evidence allocation for one day, enforced before upload within the whole-run allocation, with actual sizes and omissions recorded. No full result archive, signed app, credential or personal library asset is uploaded.

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


## App Sandbox and import hardening gates

The native Mac target now includes minimal source entitlements for App Sandbox,
user-selected file read/write, and its existing camera feature. The independent
`QRCatcherMacSandbox` scheme uses an ephemeral ad-hoc Debug signature on the same
standard cloud runner. It does not create certificates, profiles, App IDs, teams,
keychain items, accounts, App Groups or system security exceptions. The pipeline
verifies the actual signature and entitlements before an external XCUI suite exercises real Open/Save/paste, container persistence,
legacy selection, and unselected read/write denial. The app is re-signed with
only the minimal source entitlements plus Debug attach support after building;
Xcode-injected broad hosted-test exceptions are not accepted. Synthetic legacy
input and own-container diagnostic export fields are DEBUG-only and excluded
from Release. Any normal Xcode-injected `get-task-allow` is Debug-only test support; this
is not a distribution signature or evidence of prior App Store container handover.
No network, general Documents/Pictures or Photos-library entitlement is granted.
A genuine Photos-picker import from a disposable Mac Photos library is a separate
remaining gate; cancellation or a file-panel import does not substitute for it.

Paste reads encoded PNG/TIFF bytes only after the person's explicit action.
Source metadata is checked without caching before ImageIO expands raster data:
50 MiB encoded input, 32,768 pixels per edge, 100 million source pixels, and a
4,096-pixel normalized decode thumbnail. Tiny valid 1-bit PNG fixtures exercise
both the edge and total-pixel limits through the actual clipboard path, preserving
the prior result/history on failure. Existing normal golden QR fixtures continue
to test UIKit/shared-codec equivalence.

Final combined validation must pass the same head on Pro Max, SE3, iPad Pro
13-inch and iPad mini. All four rows are now enabled on fresh VMs; focused repair
runs do not fulfill those final gates. The genuine iOS 15.5 launch and physical capture,
Watch pairing, TV library availability and Vision interaction gates remain distinct.


## First native TV slice

`QRCatcherTV` has native PhotoKit browsing, explicitly requested Photos access,
40-asset pagination, cancellable streamed resource loading (50 MiB / 45-second
bounds), shared QR decoding, a focus-based result/history UI, and real PNG save
through PhotoKit. Save is reported as verified only after fetching the created
asset, reading its image resource, checking dimensions, and decoding its payload.
A QR can be displayed for an explicit phone scan; no TV clipboard or unrestricted
browser is assumed. Its own versioned history metadata is limited to a conservative
256 KiB total encoded defaults-domain budget. A failed batch leaves all earlier
records intact; no quota-driven eviction, phone-store rewrite or silent truncation
occurs. The unit suite includes duplicate/date/order/reopen, corrupt-value retention,
and a quota case accounting for other preferences. Native unit/UI execution, Photos
permission/focus behavior, export/refetch and relaunch are required CI gates, not
inferred from the SDK. TV artwork packaging, Chinese critical-flow review, optional
physical Continuity Camera and further accessibility audits remain separate gates.

## Native Watch implementation and remaining physical gates

The new Watch source (first QRCatcher compiler/runtime pass still pending) uses watchOS 27's Swift `DetectBarcodesRequest` behind an
availability check, not unavailable legacy VN/Core Image APIs. It imports a
bounded selected Photos file, normalizes a real source image with ImageIO,
retains that normalized preview (up to1536pixels, not original bytes) and all decoded payloads in a quota-bounded atomic archive,
and provides offline viewing, zoom, confirmed removal and the approved policy.
Unreadable archives are never overwritten. Older watchOS versions retain the
selected photo and offer explicit paired-iPhone processing.

The paired phone processor consumes only explicit request files. It verifies
version, UUIDs, image fingerprint, bounded regular non-symlink file contents and
same-ID conflicts, then runs the actual shared QR decoder without writing to the
phone's original history. Session epochs suppress stale results after counterpart
changes. Activation never automatically replays retained jobs; retry is explicit.
Pending originals are retained on errors and cancelled delivery. A completed file
transfer is not treated as an acknowledgement of a decoded result.

Cloud test scopes are deliberately distinct:
- Hosted Watch tests exercise actual local QR decoding, source-image readback,
  duplicate/date retention, archive reopen, quotas, corruption and reply state
- Native Watch UI tests exercise empty/policy screens and a clearly labeled
  fixture-fed offline collection prepared by the real hosted decoder
- The actual Watch Photos picker reports that Photos cannot load in Simulator;
  the QRCatcher test targets its unavailable/Close path; selection requires a physical Watch
- Apple excludes background WCSession file/user-info delivery from Simulator
  support; cross-device transport requires a paired physical iPhone and Watch
- An older-watchOS launch and weak-link/device Release packaging remain separate
  gates, as do physical scannability of the displayed saved preview and camera
  capture where a platform has a camera workflow

No App IDs, certificates, provisioning profiles or Store records were registered
for these source targets. All native platform builds/tests use the one bounded
standard cloud runner lane.

## Isolated qualification candidate after 84accd6

The same-head qualification workflow uses eight fresh standard `xcode-27` VMs,
serialized with `max-parallel: 1` and `fail-fast: false`: Mac, Vision, TV, Watch,
large phone, SE3, 13-inch iPad, and iPad mini. No successful result is inferred
from this isolation. Per-command timeouts retain their actual operation names.
The artifact allocation is 3,000,000 bytes for Mac and 2,000,000 for each other
row, totaling 17,000,000 bytes under the 20,000,000-byte whole-run cap. Each
upload has its own strict successful budget gate and one-day retention.

Mac hosted regressions execute once; real external UI executes in the minimally
entitled ephemeral sandbox. Its private 0600 unselected boundary fixture is now
created and read by an explicitly unsandboxed same-user Swift helper. Photos.app
Get Started and File menu inventory were observed; actual synthetic import and
populated app picker selection still require successful runtime evidence.

Watch processing uses an explicit FIFO admission permit across suspended and
synchronous native calls, with a controlled cancellation regression. Native
Watch, TV, and Vision unsigned generic-device Release packaging is separately
checked. The CPU Watch candidate must have both arm64/arm64_32 slices and no
Vision/CoreML framework dependency. These checks do not establish older Watch
launch or physical paired background transport.

TV's exact real Photos dialog remains a strict UI case. Only if its specifically
observed focus marker fails may a separate per-app synthetic simulator-granted
lane execute selection/decode/Photos export/refetch/reopen. That lane never
changes the original red prompt result. Revoked access recovery is separately
labeled as a simulator precondition, not a real Don't Allow interaction pass.

Vision screenshot checkpoints hold the actual UI until a UUID acknowledgement
from public simctl capture succeeds or reports an error. Blank XCTest images and
capture timeouts never count as visual acceptance. Phone camera-state assertions
remain strict; DEBUG-only lifecycle/authorization/epoch diagnostics and failure
pixels explain any failure without changing the production camera behavior.

## Further stabilization after the first isolated run

At `79493b3`, Mac hosted18/18 passed. The sandbox completed the real normal-home
0600 denial controls and container persistence path, but `.all` still found an
unlabeled outer NSWindow content group above the correctly labeled SwiftUI root.
Photos.app successfully selected the synthetic PNG through File → Import; the
remaining test error addressed a Sheet as a Dialog. Those selectors and the
native window accessibility label are being repaired without ignoring audits.

The same head's TV runtime passed the exact real Photos authorization, actual
selection/decode, PhotoKit export/refetch verification and result/output audits.
After relaunch, the saved record existed but the native List grouped Open and
Delete in one focused cell; they are being separated into single-action rows.
Explicit simulator-revoked Photos recovery passed as its own test. The TV device
Release compiled, while its verifier needed the actual `Small` rendition name.
Vision device Release, original identity/minimum1.0/privacy/icon checks passed.
Vision hosted tests were blocked by a short-name Simulator launch helper, now
separated from unit execution. Watch app/hosted/UI compilation passed; runtime
and weak-link qualification remain governed by their actual reports.

Watch incoming replies now have a bounded app-owned journal design: synchronous
atomic staging before the WC delegate returns, local replay through the existing
pending UUID/hash validator, and removal only after durable commit or an obsolete
request. Each history archive has its own inbox so isolated test stores cannot
consume production replies. Conflicting same-ID replies preserve the first file;
unreadable history retains its journal. Tests cover the process-boundary fixture,
relaunch, stale/duplicate replies and bounded orphan recovery. This is not proof
of physical background transport. Failed phone processing preserves prior local
results, and canceled decode waiters release captured images before the currently
running native request finishes.

## Pinned Watch CPU decoder candidate

The 79493b3 Watch simulator actually launched, but Swift Vision returned empty
results for independent ASCII/Unicode/rotated QR fixtures with ANMD model-load
timeouts and MRC network-compilation errors. This is preserved as a failed local
simulator decoder gate; it does not establish physical Watch failure. The real
Photos picker separately displayed Apple's simulator-unavailable message.

The next candidate isolates ZXing-C++ v3.1.1, official commit
287c85df6f961c8efbfb5ffd736cd9457b8b890e, to Watch and Mac-hosted oracle tests.
QR-only readers are enabled, writers and all other symbologies disabled. The
126 upstream files are byte-for-byte hash-pinned; their selected 39 C++ plus one
C translation units total 312,195 bytes. Source and embedded dependency notices
are retained and bundled. quirc was smaller but required separate ECI handling
and had outstanding hardening reports, so it was not selected.

The production C ABI accepts only contiguous grayscale up to 1536×1536, returns
at most 32 QR strings (16 KiB each), rejects a detected 33rd code rather than
truncating, and supports cancellation at delivery. The serial owner keeps its
permit until native processing returns; queued canceled work is released early.
No fixture value is injected into decoding. The iPhone/Mac app codec and original
CoreData store adapter are unchanged. Local GCC ASan/UBSan evaluation passes 44
unique cases, including Latin-1/UTF-8/Shift-JIS/mixed ECI, rotated/mirrored/inverted,
multiple codes, maximum dimensions, malformed and truncated inputs. LeakSanitizer
cannot run under the ptraced host and is explicitly not claimed. An optimized
Linux harness was 318,360 bytes; the Watch binary footprint and actual arm64/
arm64_32 load/runtime still require the exact Apple CI candidate.

The Watch app is not yet embedded in the iOS product; a combined unsigned
companion packaging gate remains after native Watch compilation/runtime stabilizes.
No App Store platform, App ID, or persistent signing resource has been created.
