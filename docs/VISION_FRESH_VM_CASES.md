# Existing Vision cases on independent fresh VMs

The single combined Vision matrix row is replaced by four rows. Each GitHub
matrix job receives a fresh standard runner VM and locally builds its own test
bundles. No app products, containers, caches, or simulator state cross VMs.
Creating several simulators on one VM would not meet this contract.

| Scope | Existing XCTest method | Exact result | Outer UI cap | XCTest default/max | Evidence bytes |
| --- | --- | --- | ---: | --- | ---: |
| visionos_photos | testRealPhotosImportCopyAndReopen | VisionPhotosUIResults.xcresult | 600 s | 420/480 s | 900,000 |
| visionos_files | testRealFilesImportAndReopen | VisionFilesUIResults.xcresult | 300 s | 420/480 s | 800,000 |
| visionos_chinese | testChineseEmptyPhotosResultAndOfflinePolicy | VisionChineseUIResults.xcresult | 300 s | 420/480 s | 550,000 |
| visionos_largest | testChineseEmptyPhotosResultAndOfflinePolicy at actual read-back largest system category | VisionLargestUIResults.xcresult | 300 s | 180/240 s | 550,000 |

The case selector is a closed enumeration. An omitted, unknown, combined, or
mismatched scope is rejected before any simulator command. Existing result or
case-report files reject a second invocation on the same VM. Each row runs one
existing UI invocation once, with one capture helper and one current runner
lease. A failing row cannot prevent the other independent matrix rows from
running; there is no automatic retry or assertion relaxation.

The locally built Debug app is installed through public simctl with a 90-second
cap before fixture preparation. Photos, Chinese and largest rows seed only the
synthetic Photos image with the existing 150-second cap. Files stages only its
app-owned synthetic document. The 11 hosted tests run once on Photos; unsigned
Vision Release/package verification runs once on Files. The source icon preview
is retained only with Files Release evidence.

The largest row keeps actual system-category set/read/restore, original failure
and restoration status. A trait override does not substitute for Vision system
propagation. Held success checkpoint ACKs retain their existing 100-second
bound; failure-only host screenshots cannot qualify success evidence.

Evidence is bound to source commit, device UUID, selected scope, exact XCTest
method and result bundle, plus the current runner lease/PID and frame hash.
Required success checkpoints and actual export receipts cannot be replaced by a
failure frame, another case's result, or another runner. Missing/oversized
required evidence leaves the job red. Bounded diagnostic artifacts can still be
retained with `qualified: false`, subject to the same per-row upload cap. Raw
xcresult bundles are never uploaded. Log tails are retained once at 8–16 KiB
per selected log, rather than duplicating full logs in each evidence route.

The total reserved artifact allocation is 19,800,000 bytes within the unchanged
20,000,000-byte whole-run cap and one-day retention. Per-row caps are strict;
there is no truncation/substitution of required native frames to force a pass.

Workflow concurrency remains `qrcatcher-apple-platforms`, `max-parallel: 1`,
`fail-fast: false`, with the existing standard runner and unchanged 45-minute
runtime job caps. There are now 13 runtime rows. Including the unchanged
20-minute preflight, the declared worst-case workflow cap rises from 470 to
605 minutes (+135). The healthy-path extra boot/build/setup cost is estimated
at about 10–20 minutes, not a promised completion time; service stalls may use
the existing hard caps. Runner cost constraints remain unchanged.

Portable fixtures exercise routing, exact selection and identity, workflow
isolation, budgets at and one byte above each allocation, and malformed or
substituted evidence under normal and optimized Python. These checks are not
Apple compilation, actual fresh-VM execution, system-size propagation, or
native screenshot proof. Those remain required live CI gates for the exact
reviewed source revision.
