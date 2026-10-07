# One QRCatcher Mac unsigned universal archive observation

This branch-only preparation adds one archive job and proof helpers to exact parent d2d63d5c6cfe50139f623d81e1848e67b26bf5a3, tree 1808d1e0753b4bebe042b5fd9d9448d5e80f63a5. It does not change application, project, entitlements, resources, UI tests, existing audits or existing workflows. Publication and native execution require a separate explicit GO.

## Fixed scope

- Push only to `codex/mac-unsigned-archive`; attempt 1, sole parent d2d63d5, one standard xcode-27 job, 20 minutes. No dispatch, retry, device boot, application launch, hosted/UI test matrix, screenshot, signing, export or Apple account operation.
- Archive QRCatcher.xcodeproj / QRCatcherMac / Release / generic macOS / macosx / arm64+x86_64 / CODE_SIGNING_ALLOWED=NO.
- Expected product Products/Applications/QRCatcherMac.app; executable Contents/MacOS/QRCatcherMac; CFBundleName QRCatcher; bundle 100mango.QRCatcher; version 1.1(2); minimum macOS 13.0; SDK 27.0. Match both architecture UUIDs against dSYMs/QRCatcherMac.app.dSYM.
- Pin all 38 product inputs, plus eight existing source/build support files. The full project and scheme are pinned; the Mac app has no external target, Swift Package or script build-phase dependencies. Existing generated-project inputs are observed, not regenerated.
- Use the original `materialize_mac_icons.py` and retained 1024 PNG before archive. Its ten generated icon sizes remain ignored build inputs. This mechanically derives existing artwork; there is no new art/detail or retained source-asset change.

## Product-specific proof

Complete bounded catalogue and all three actual archive/app/dSYM plists are retained before semantic checks. Standard Assets/ProductIcon or app icon PNGs are accepted and inventoried; there is no resource filename whitelist.

The app must contain its actual AppIcon.icns, Assets.car, Shared/FileImportResources privacy manifest, both zh-Hans localization tables and QR.momd/QR.mom. English is source-key fallback; en.lproj is not required. Compare compiled localization dictionaries and privacy with frozen source. QR.omo and VersionInfo.plist are inventory observations rather than assumed archive gates.

Reuse the original QR symbol parser with bounded `nm -u` to observe the FileTimestamp reader import, and the original compiled-icon Swift verifier to decode the actual ICNS. Its PNG remains local; only its JSON observation enters proof. The fixed privacy reasons remain C617.1 and 3B52.1, with no collected data or tracking.

Inspect every actual Mach-O: one universal app executable only, both slices macOS/min13/SDK27, system runtime dependencies, no debug test/public-metadata observer seams. dSYM file headers must actually contain both DWARF architectures. dSYM version fields are observations and may differ from app metadata; identity plus real architecture UUID matching provides the symbol binding.

This follows the successful TouchColor archive driver (7d279381e6564bc375be1bf1c84ec4612180ab53/run37561813814), adapting QR's actual layout. The capture implementation is reused from qualified QR TV source 547dce, only as a process collector. No TV app/source/asset qualification is imported into the Mac product.

## Bounds and diagnostics

- Same phase ceilings as the mature driver, measured from its original monotonic start: preparation 180s; archive 800s; proof 950s; final source/report 980s; evidence 1040s; finalization 1060s. Checkout allows 60s, leaving 80s job headroom.
- Archive receives at most 600s with a separate 20s owned-group cleanup reserve; combined stdout+stderr cap 512 KiB. Non-quiet output retains the normal build conclusion. The old QR universal Release log was about 285 KiB including runner prefixes; no cap/time increase is proposed.
- Preparation includes only this archive helper's portable normal/optimized tests and original icon materialization, within the existing preparation clock. Proof's bounded commands observe symbols, icon and UUID; none launches the app.
- Zero exit with an `error:` line stays failed. Once timely host completion is known, that case retains bounded pure-file catalogue and three plist observations; no further native proof command is allowed. A timeout/uncertain process cleanup starts no follow-up. No automatic second archive.
- Catalogue: at most 2048 entries/1 GiB contents/1 MiB metadata/30s per scan; actual Mach-O at most 64 MiB; plist at most 64 KiB; proof JSON at most 2 MiB. Escaping links/special files and changes during the observation interval fail with the affected path retained.
- Host-client/process-group completion does not prove the lifetime of Xcode's independent system daemons.

## Retention and limits

Upload only build/archive-proof/report.json for one day, using the existing admission and post-upload check against the original clock. No .app, .xcarchive, dSYM binary, IPA, profile or generated icon PNG is public evidence. `qualified` means unsigned archive observation within this interval; signing_qualified, store_qualified, older_os_qualified and binary_handoff remain false. Retention is separately confirmed by the final workflow log receipt.

Historical d2d evidence remains: 26 hosted tests and arm64/x86_64 Release builds passed; two UI rows failed with 17 audit callbacks. A separate bounded visual review accepted the observed foreground audit differences without changing those results. This archive job does not rerun or clear audits, qualify Intel/older-OS runtime, or create compliant Store screenshots. Screenshot work waits for the separately validated temporary-display route.
