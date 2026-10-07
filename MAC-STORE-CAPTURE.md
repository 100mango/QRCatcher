# Two real QRCatcher Mac Store window captures

Local preparation only. Exact parent bf726e9637fcdd469048ed157b8ea73953ccb4fb/tree37d33f2f3b5b1d9bde222f9481c49e9997ca49fc has the qualified unsigned universal Mac archive. Its shipping input matches the previously tested d2d Mac source. No new native or remote execution is authorized by this document.

## Fixed user-visible flow

One new case, testStoreNormalResultAndHistoryScreenshots, in the existing QRCatcherMacUITests runner:

1. Paste the existing ASCII QR image through the real app's Paste action, observe the complete URL, verify Copy and the one-record history, and capture the normal result window.
2. Paste the existing Unicode QR image to save a second record; choose the original URL row, then the Unicode row through real history UI; verify the selected row, restored full text, Copy and two-record count; capture the history result window.

Sample QR payloads are the existing benign fixture content, not user data. No history database is injected, no app feature is mocked, and there is no separate app launch between frames. Both images bind exact source, built executable/debug payload hashes, app PID, app/window identity, real display geometry, case timing, literal payload/hash, history count and selection. English control labels are observed, in addition to the existing explicit English launch arguments.

## Mature capture/display reuse

Reuse the actually successful TouchColor source 272ab606188772236e9a9d9e23eae7c0b93e1c66/run 37571336030. The original UITestRunner owns at most one advertised temporary display-mode change via forAppOnly. It prefers true 1× and accepts true 2×; no virtual display, persistent setting, independent keeper, elevation or utility is introduced. Setup precedes the original app launch. Teardown terminates the app before attempting to restore the original mode. Incomplete restoration remains a separate cleanup observation and does not erase already source-bound images.

The sole product change is an explicitly gated DEBUG helper, invoked only with a valid new capture token, the test's new temporary store and exact capture launch argument. It resizes and centers the existing window once at 1280×800 points. No-token execution and the Release projection preserve the parent behavior. Existing UI cases and strict audit code remain unchanged; this single screenshot case does not call an accessibility audit.

Capture uses the actual window.screenshot PNG, excluding other windows, screen chrome and desktop. Preserve that original native PNG. Reuse the successful PNG codec unchanged: if alpha is entirely opaque, remove that channel while proving every RGB sample equal; preserve color profiles. No crop, resize, upscale, recoloring, background fill or compositing is admitted. Unsupported dimensions/transparent pixels remain format failures with qualified native originals retained for diagnosis. Expected Store pixels are 1280×800 at 1× or 2560×1600 at 2×.

## Source and process scope

Freeze all 38 shipping inputs, recording the single DEBUG-only source difference and proving Release projection equivalence. Lock existing collector/owned-process helper and all original QR fixture materializer inputs. The project, scheme, entitlements, payload/history logic, artwork, privacy and localization sources are unchanged. Product identity is QRCatcherMac.app / QRCatcherMac / QRCatcherMac.debug.dylib, bundle 100mango.QRCatcher; same-bundle iOS/TV products are not admitted.

The controller derives the proven fixed Mac capture path. It reuses bounded process capture, pure file/JSON/summary primitives, display receipt validation and pixel codec; no unrelated launch diagnostic framework is imported. Original materialize_mac_icons.py and materialize_qr_fixtures.py run during preparation. Building test products does not run hosted suites or other UI cases.

## Proposed single cohort and bounds

One push to codex/mac-store-display would run one xcode-27 job, attempt 1, with the same 25-minute outer budget as the successful Touch capture route. It builds Debug once, runs only this one capture case once, reads its summary and exports only its attachments. No dispatch, automatic retry, alternate mode attempt, audit matrix, signing/export or Apple account action.

All phases share the original monotonic clock: prepare 180s, build ceiling 640s, test 960s, proof 1140s, final source/report 1170s, evidence 1230s, finalization 1250s. Checkout adds 60s, leaving 190s outer headroom. Build command≤420s, UI command≤300s with XCTest allowance 120s; each reserves 20s owned-group cleanup. Existing log caps remain 512KiB; PNG≤3MiB, report≤2MiB, full packet≤14MiB. Two bounded original QR materialization commands fit within the same preparation budget. Known zero-exit build error text stops before product/test work; uncertain cleanup starts no further command. No clock restarts at export or upload.

Only report.json, native-result.png, native-history.png and their RGB Store copies may be publicly retained for one day. No app/archive/test-result bundle or unrelated XCTest attachment is published. Capture/pixel qualification and runner restoration are recorded separately; Store acceptance remains pending actual image review. The prior UI Failed/audit disposition, archive proof and signing authorization retain their separate scopes.
