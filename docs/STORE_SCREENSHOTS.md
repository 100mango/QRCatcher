# QRCatcher native Store PNG capture candidate

This is a separate, local-only successor for three missing genuine app screenshots:
iPhone history plus iPad result and history. Publication, a Mac run, and Store
delivery remain separate approvals. No new native screenshot has been produced
by this successor.

## Product and scope

- Base: `991af41dfdc01bc1332218cb8969f4ca40198304`, tree
  `d5357beefe435c278f7bfc793eae5059df5b0cfb`, QRCatcher 1.1 (2), families 1 and 2.
- Exact sole publication parent: `57fd7e32a499cc5237a091e30f04d99edf9e7705`,
  tree `001e0aa8b33ea53039d6c47a59a84465aef9f139`. The successor changes only
  the capture UI block, runner, focused tests, and this explanation.
- All 455 other base files remain byte-for-byte unchanged. One contiguous,
  precisely hashed UI-test block is appended to the existing QRCatcherUITests file.
  It declares a separate `QRCatcherStoreCaptureUITests` class, so the original
  `QRCatcherUITests/QRCatcherUITests` all-class selection and its method count
  do not include these display cases. The project file needs no change.
  Removing that block restores its original bytes and all original test bodies.
- No app implementation, project, resource, localization, original workflow, or
  release qualification route changes. The five new files contain the capture
  workflow, runner, protected-source manifest, focused tests, and this document.
- The runtime requires the candidate's actual source/workflow SHA, sole parent,
  parent tree, exact changed-path set, run/attempt, and a fresh clock to agree.
  This capture commit is distinct from the qualified product-source commit.
- The candidate must stay on its separate `codex/store-screenshots` route. It is
  not a replacement release branch and does not rerun or expand release qualification.

## Three new captures and one retained original

The existing zh-Hans translation is selected with normal Apple language/locale
launch arguments. Light appearance and portrait orientation are selected using
normal simulator/XCTest APIs. There is no new localization or app display mode.

1. On iPad, `testStoreNormalResultScreenshot` shows the ordinary saved URL result for
   `https://example.com`, including the existing result actions. The link is never
   opened and no external service is contacted.
2. `testStoreNormalHistoryScreenshot` shows two saved demonstration records:
   that reserved example URL and `周末计划：上午逛市集，下午喝咖啡`. On iPhone the
   normal History tab is shown; on iPad the native history/detail split is shown
   after choosing the note. Both test methods reset their isolated demo history,
   so the second case does not depend on the first case's state.

The iPhone result is reused, without alteration or re-running, from public source
`57fd7e32a499cc5237a091e30f04d99edf9e7705`, run `37529167019`, job
`112493798461`, artifact `11444116266`. Its native case passed 1/1 and its Chinese
UI received visual approval. The exact original is 1206 × 2622 RGB PNG, 214424
bytes, SHA256 `831edae1c448f02ff15f5056f570c037f2482a97d19b5bb3522f5bc2d121717b`.
That run later failed in the history demo; it remains a failed run and is not
relabeled successful. The prior result keeps its own source/run/device receipt
and is not copied into, or attributed to, the new run's packet. The final four-image
set therefore uses two separately identified native captures.

The previous multi-line history demo observed only `周末计划` as the result AX
label and failed the complete-payload assertion. Its cause is not established.
The single-line demonstration avoids that input for screenshot preparation;
its full equality assertion is unchanged. This does not claim a product bug fix
or qualify multi-line input, camera scanning, or persistence independently.

These are synthetic demonstrations. The pre-existing DEBUG `-ui-testing` /
`-fixture-payload` entrance creates a real QR image, decodes that image through the
real codec, passes the decoded text to the normal result handler, and saves it to
the separate `ui-testing.sqlite` store. This demonstrates result/history UI and
that DEBUG encode/decode/save path. It does not prove that a physical camera
scanned a code, that a real photo was imported, or that the Release app exposes
the demonstration entrance. No user photographs, private payloads, or third-party
creative assets are used.

## Original pixels and device ownership

- iPhone 17 Pro: exactly 1206 × 2622 pixels.
- iPad Pro 13-inch (M5): exactly 2064 × 2752 pixels.
- One observed available iOS 27.0 / 24A434 runtime, Xcode 27.0 / 27A266a.
- No model substitution, pre-existing simulator use, large-phone fallback,
  image generation, cropping, resizing, recompression, alpha removal, or compositing.
- Each test attaches `XCUIScreen.mainScreen.screenshot.PNGRepresentation` directly
  with `public.png` and KeepAlways. Existing JPEG diagnostic helpers are unchanged.
- Raw PNG CRC/chunks/raster, dimensions, alpha, byte count, and SHA256 are inspected.
  The PNG validator and observed Xcode 27 flat attachment traversal reuse the
  existing Celluloid Store-capture implementation. There is no second generalized
  screenshot/export framework.
- A candidate with alpha is retained unchanged and fails direct Store admission;
  it is never silently transformed.

The runner builds the existing iOS-only Debug project once, then creates a fresh
owned 17 Pro using the exact observed runtime/type IDs. The returned UUID must be
canonical, absent from the initial device list, and read back once with its exact
owned name/type/runtime, availability, and Shutdown state. Only that successful
readback permits operations on the device. Build and installed app inventories
are compared before and after its selected cases. The phone runs only history;
the iPad runs result then history. Each of the three new screens is exported
separately. Phone history resets its own demo store and launches both fixed demo
payloads, so it does not depend on re-running the already-approved phone result.
The first owned device must be shut down, read back Shutdown, deleted, and read
back absent before the M5 is created. Existing devices are never booted, shut down,
or deleted. No failed or ambiguous create/install/test is retried.

Each individual test invocation ends before its original PNG is exported. That
PNG is immediately written and fsynced to the final retained packet, followed by
its source/run/device/product/attachment receipt. Only then does summary validation
or the next case occur. Already retained screenshots survive later summary,
postflight, cleanup, second-case, or second-device failures. A case is only marked
passed after its native invocation and one-case, exact-device/time-window summary
agree. A PNG alone is not a successful capture or release-qualification claim.

## Bounded single-Mac execution

The proposed push workflow has one `xcode-27` job, no matrix, contents-read-only
permissions, no signing, no upload to App Store Connect, and no release archive.
Root must check global capacity and authorize the public branch write separately;
this code cannot assert that the overall five-standard-Mac cap is available.
It needs no extra paid service. Expected elapsed capture time is roughly 15–30
minutes, subject to actual simulator/build performance; no native time is proven yet.

A single source/run-bound clock starts before checkout. Ordinary native commands
must finish within its 2700-second work window; exporters, summaries, source
readbacks and owned cleanup use the fixed 2940-second tail endpoint. Every command
reserves its full allowance plus 20 seconds before dispatch. There are no shortened
command allowances or refreshed device clocks. The enclosing capture step is at
most 52 minutes and the job at most 60 minutes. Existing process-group supervision
and its durable uncertainty barrier are reused without modification. Any failed,
late, unknown, or unclean native operation stops the route. Failure handling is
file-only, with no native cleanup retry; disposable-host teardown remains the
owner's responsibility after a failed route.

Fixed maximum command allowances (seconds):

- Source reads: 15; Xcode and inventory reads: 30
- Create/readback: 60/30; boot/bootstatus: 60/240
- Fixture materialization: 30; existing iPad icon materialization: 60
- One Debug build-for-testing: 600; per-device install: 600
- Installed-product lookup and appearance: 60 each
- First UI command per fresh device: 600 (phone history, iPad result)
- Subsequent iPad history command: 420; per-test body maximum: 240
- Each attachment export: 45; each finalized summary: 30
- Owned shutdown/delete: 45 each; their readbacks: 30 each

The first UI command on each fresh device retains the 600-second cold-start
allowance: phone history is now first, while iPad result remains first. Result
method bodies remain 180 seconds, history bodies and the maximum per-test body
remain 240, and the subsequent iPad history command remains 420. The shared
work/tail deadlines, full admission, and one-hour job ceiling are unchanged.

The worst-case sum does not fit the work window; later stages are conditional on
full remaining-time admission. This is intentional and does not authorize a rerun.
The full packet is at most 40 MB, each of three newly captured fixed PNG names at most 8 MB, and
other individual files at most 1 MB. Command log tails are at most 64 KB. No
xcresult, DerivedData, app bundle, or unselected image is uploaded. File-only
upload admission also works after native uncertainty and never deletes successes.
A successful command may retain an empty `.log`; upload admission accepts only
that regular, non-symlink zero-byte log exception. JSON, manifests, and PNGs
remain subject to the unchanged nonempty read rule.

## Remaining review and local validation

The three new images must still pass actual native capture and human visual
review; the prior approved phone result retains its original provenance. Final App Store screenshot slot requirements must be read back for the
actual 1.1 version after that version/build exists; a current 1.0 slot does not
prove a future iPad exemption. The candidate does not create that version.

Local checks, with no Xcode/simulator/network:

```
python3 scripts/store_capture.py verify-source
python3 -m unittest discover -s Tests/Harness -p test_store_capture.py -v
python3 -O -m unittest discover -s Tests/Harness -p test_store_capture.py -v
```

These 15 focused checks cover reversible source preservation, exact device/runtime
selection, original PNG/alpha and attachment binding, bounded/uncertain dispatch,
one-case summary identity, single-job workflow scope, and prior-image retention
on subsequent failure. They are not a native build or a full application regression run.
