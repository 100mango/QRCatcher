# Original iPhone/iPad profile

This profile isolates the original iPhone/iPad product for its own qualification.
It does not qualify a native build, physical-camera behavior, signing, distribution,
or the deferred Watch/Mac/TV/Vision products.

## Deterministic generation and identity

Run from the repository root:

```sh
python3 scripts/generate_project.py --profile ios-only
```

The output is `QRCatcher-iOS-Only.xcodeproj` with the shared `QRCatcher` scheme and
exactly three targets: `QRCatcher`, `QRCatcherTests`, and `QRCatcherUITests`. Use
`-project QRCatcher-iOS-Only.xcodeproj -scheme QRCatcher` for the closed route.
Do not use `QRCatcher.xcworkspace`, which selects the all-platform project.

The shipping product remains `QRCatcher.app`, executable `QRCatcher`, bundle ID
`100mango.QRCatcher`, version `1.1`, build `2`, device families `1,2`, and iOS
deployment floor `15.0`. Hosted test runners still require iOS `17.0`. The
scheme's test action still names both original hosted unit and UI test bundles;
its archive action remains Release. Build outputs and archives must use the
separate paths selected by the closed route, not an all-platform product cache.

Default `python3 scripts/generate_project.py`, or explicit `--profile all-platforms`,
replays the original `QRCatcher.xcodeproj` and all six schemes byte for byte. The
two invocations never overwrite each other's generated project. Later-platform
source, standalone targets, and default Watch embedding remain available in the
all-platform profile.

## Implementation ownership

In the iOS profile, the app has no Watch dependency and no Embed Watch Content
phase. `QRWatchPhoneService.m` and `QRWatchSessionGate.m` compile only into the
hosted `QRCatcherTests.xctest` bundle. In the default profile they compile only
into the app, as before. Header/navigator references are not shipping build
membership: the source phase and target edges determine the implementation owner.

Both iOS app build configurations define `QRCATCHER_IOS_ONLY_RELEASE=1`. The
source defaults that macro to `0` when it is undefined. Only the Watch service
import, its launch activation, and its two Debug observation calls are gated.
The store/decoder/history/camera/picker/privacy/controller/resource paths remain
unchanged. The iOS profile deliberately emits no `watch_enter` or `watch_return`
events for an activation it skips. Existing finite phase names remain available
for compatibility, and observed timing remains diagnostic only.

The original hosted unit inventory remains 30 cases: 12 core, 7 bounded image
import, 7 phone result, and 4 Watch phone processor. Those four cases keep their
actual helper implementations and may link WatchConnectivity in the test bundle.
That is distinct from the shipping app, which must contain neither helper nor
WatchConnectivity. No existing native test or strict app accessibility assertion
is removed or relaxed.

## Package evidence

The route must inspect its actual Debug simulator app and unsigned Release
archive using the bounded `scripts/verify_ios_only_release.py` validator. A
source graph alone cannot establish what a native linker emitted. A Debug
build-for-testing host can contain its unit bundle inside `PlugIns`, as
documented in Apple's [TN2339](https://developer.apple.com/library/archive/technotes/tn2339/_index.html).
The Debug validator therefore needs the actual newly produced `.xctestrun` file
to bind exactly one `QRCatcherTests.xctest` bundle to the inspected app. Only
that identified test bundle is inspected and reported separately as test-only.
All other app code, shipping frameworks, and package entries remain subject to
the strict Watch absence checks. Release archives admit no `.xctest` bundle.
Unrelated test products elsewhere in DerivedData remain outside the selected
app scope.

```sh
python3 scripts/verify_ios_only_release.py path/to/QRCatcher.app \
  --platform simulator --configuration Debug --xctestrun path/to/actual.xctestrun \
  --output path/to/debug-package.json
python3 scripts/verify_ios_only_release.py path/to/QRCatcher.xcarchive \
  --platform device --configuration Release --output path/to/release-package.json
```

Create the output parent directory before these calls. Package rejection is a
nonzero exit; a success report is package evidence, never native-runtime or
release approval. Release diagnostic markers must be absent. Debug fixture and
startup diagnostics are expected, while Watch/helper/companion presence fails in
both configurations. Every app Mach-O image, including any Debug dylib, must be
inspected; the bound hosted bundle's Mach-O evidence is labeled separately.
Stripped `nm` symbols are not used as an absence proof.

## Portable validation

```sh
python3 -m unittest Tests.Harness.test_ios_only_project \
  Tests.Harness.test_ios_only_release_package \
  Tests.Harness.test_mini_startup_observation
python3 -O -m unittest Tests.Harness.test_ios_only_project \
  Tests.Harness.test_ios_only_release_package \
  Tests.Harness.test_mini_startup_observation
```

These tests parse the emitted project graph, resolve implementation consumers
and local header import closure, compare all default output bytes, preserve the
30-case source inventory, and exercise a real portable preprocessor on the
actual conditional source. They do not fabricate Apple SDK declarations and do
not claim Objective-C compilation, framework autolinking, hosted-test linkage,
archive validity, or runtime coverage. Those remain native qualification gates.

The compiler macro representation is documented in Apple's
[Build Setting Reference](https://developer.apple.com/library/archive/documentation/DeveloperTools/Reference/XcodeBuildSettingRef/1-Build_Setting_Reference/build_setting_ref.html).
The finite profile choices and disabled option abbreviation use documented
[Python argparse](https://docs.python.org/3/library/argparse.html) behavior.
