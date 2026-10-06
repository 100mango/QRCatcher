# Local bounded startup observation v1

This candidate is a local implementation of the admitted startup diagnostic.
It does not authorize publication or a native run. The fc10a71 launch/outer
timeout remains unexplained; no completed native case or summary was produced.
The earlier c15b951 actual 2/2 layout result remains separate evidence.

## Scope and transport

The app records only a finite startup slice in DEBUG when the arguments contain
exactly one `-ui-testing`, exactly one `-mini-startup-observation-v1`, one
`-mini-startup-launch-id` followed by a canonical NSUUID string, and one
`-mini-startup-slot` followed by `largest-initial`, `split-initial`, or
`split-reopen`. It generates a separate fresh NSUUID inside the current app
process and records that process's PID. A missing, duplicate, malformed, or
wrong-slot admission does not enable observation.

There are 13 closed phase names, each retained at most once, with a hard limit
of 16 events and 4096 UTF-8 bytes for the combined accessibility value:

1. main_entry
2. store_enter / store_return
3. watch_enter / watch_return
4. delegate_return
5. fixture_encode_enter / fixture_encode_return
6. fixture_decode_enter / fixture_decode_return
7. fixture_handle_save_enter / fixture_handle_save_return
8. main_queue_turn

The recorder brackets the existing synchronous calls. It neither replaces nor
changes Core Data opening/fetching, Watch activation, QR generation/decoding,
payload handling/history save, accessibility announcement, or camera behavior.
The fixture path still uses the real existing CIContext/CIDetector pipeline.
No decoder coverage is inferred from this diagnostic. One dispatched main-queue
block records one turn after the existing appearance path; that single event
does not establish continuous responsiveness or automation quiescence.

The only app transport is the existing owned DEBUG `scan.status`
accessibilityValue. The existing camera diagnostic text is preserved as its
prefix and merged with ` mini_startup_v1=` plus bounded JSON. No app console
channel, file, pasteboard, simulator command, extra control, collector, or
general observer framework is introduced. When the token is absent, the camera
value remains exactly its prior string. All new app and helper diagnostic
symbols, strings, and calls disappear under Release preprocessing.

## Returned-launch and failure observation

QRCatcherPadUITests adds only the token, fresh request UUID, and closed slot for
the two layout cases and the split persistence relaunch. The persistence launch
keeps its original `-ui-testing -AppleLanguages (en)` arguments and continues to
omit reset-history and fixture-payload. Missing fixture phases on that launch
are expected and remain UNKNOWN. Photos and Files retain their original launch
behavior and receive no diagnostic enablement.

The helper emits launch-enter/return and value-read-enter/return records to the
existing retained native layout log, capped at 4096 JSON payload bytes per
observed launch. Nonfinal records can use at most 3712 bytes, reserving 384 bytes
for the decisive value-read-return. If its full record cannot fit, the final
record explicitly reports UNKNOWN_log_cap and startup_record_omitted=true with
a null wall timestamp. The closed fallback is 289 compact JSON bytes, including
the longest slot and the canonical UUID; it therefore fits the reserved space.
An absent app-side merged value remains UNKNOWN_missing_invalid_or_wrong_launch
at the helper.

The portable saturation fixture uses all 13 producer phases, a maximal positive
PID, both UUIDs, the longest slot, and wide negative finite double values. Its
compact JSON sizes are: producer 1105 bytes, combined camera value 1208 bytes,
three prior markers 228/229/232 bytes, final wrapper 1414 bytes, and total helper
payload 2103 bytes. These are portable serialization calculations, not native
execution measurements. Independently, a producer at its full allowed 4096-byte
transport cap plus that wrapper overhead and those markers would need 5094
bytes. The explicit final fallback and actual byte-length checks cover that
saturation regardless of native numeric formatting.

It attempts at most one public scan.status.value getter after
a returned launch, or in the existing failure capture path if no attempt was
made. The attempt is claimed before invoking the getter, including on exception;
failure capture cannot retry it. Retrieval checks the request UUID, closed slot,
an app-generated UUID, positive app PID and finite event count before retaining
the app record. Missing, malformed, oversized or mismatched values remain UNKNOWN.

The public value getter has no hard per-getter deadline. It may block until the
unchanged XCTest case or outer command bound. A killed relaunch may leave only
launch_enter, and a killed getter may leave value_read_enter. No extra wait,
poll, retry, readiness assertion, post-timeout command, assertion weakening,
quiescence change, audit change, or cap increase is introduced. A diagnostic
getter is an additional public automation request, so its blocking remains a
native execution risk even though it does not qualify a pass.

## Clock meaning and evidence limits

The app and helper use CFAbsoluteTimeGetCurrent, a wall-clock value with the
NSDate reference epoch (2001-01-01 UTC). Finite timestamps are retained solely
for diagnostic correlation. Nonfinite timestamps become null; a nonfinite or
backward observation sets the sticky clock-discontinuity flag. Every interval
is explicitly UNKNOWN. Wall time alone cannot detect every forward clock jump,
and neither apparently ordered timestamps nor a main-queue turn prove a
continuous duration or responsiveness.

Under an explicit assumption of no wall-clock discontinuity, a reviewer may
compare raw main-entry, synchronous call brackets, delegate-return, fixture and
helper launch records to investigate app-authored startup versus Xcode launch
delay. This is conditional correlation, never monotonic timing or native
acceptance evidence. Missing early markers or a failed AX retrieval cannot
isolate a launch stall. In particular, startup blocked before the existing
status label is created cannot export an earlier in-memory marker through this
surface. There is deliberately no second transport to recover it.

## API and source verification

The language-specific public declarations were checked on 2026-10-06:

- [Apple Core Foundation CFDate.h](https://github.com/apple-oss-distributions/CF/blob/main/CFDate.h): C declaration of CFAbsoluteTimeGetCurrent returning CFAbsoluteTime; that type is a double interval from the 2001 reference epoch.
- [NSProcessInfo processIdentifier, Objective-C](https://developer.apple.com/documentation/foundation/processinfo/processidentifier?language=objc): readonly int property.
- [XCUIElementAttributes value, Objective-C](https://developer.apple.com/documentation/xcuiautomation/xcuielementattributes/value?language=objc): readonly nullable id property; its exact type varies with the element.
- [NSUUID UUID, Objective-C](https://developer.apple.com/documentation/foundation/nsuuid/uuid?language=objc): class method returning instancetype.
- [NSUUID initWithUUIDString, Objective-C](https://developer.apple.com/documentation/foundation/nsuuid/init(uuidstring:)-8t9n3?language=objc): instance initializer accepting NSString.
- [NSUUID UUIDString, Objective-C](https://developer.apple.com/documentation/foundation/nsuuid/uuidstring?language=objc): copy, readonly NSString property.
- [NSNumber numberWithBool, Objective-C](https://developer.apple.com/documentation/foundation/nsnumber/numberwithbool:?language=objc): class factory taking BOOL and returning NSNumber, preserving JSON Boolean intent.
- [NSMutableArray arrayWithCapacity, Objective-C](https://developer.apple.com/documentation/foundation/nsmutablearray/arraywithcapacity:?language=objc): class factory taking NSUInteger and returning instancetype.
- [NSString rangeOfString, Objective-C](https://developer.apple.com/documentation/foundation/nsstring/range(of:)?language=objc): instance method taking NSString and returning NSRange.
- [NSMaxRange, Objective-C/C](https://developer.apple.com/documentation/foundation/nsmaxrange(_:)?language=objc): static NSUInteger function taking NSRange.

The primary Apple documentation's Objective-C variant declarations were read
from its public structured documentation responses. This is declaration
verification, not Apple compilation or runtime validation. No Apple SDK was
installed locally. No system-uptime/mach boot-time API or privacy-manifest change
is added.

The actual checked-in PBX file/build/source-phase/target edges were inspected:
AppDelegate.m, main.m and QRCatchViewController.m are compiled only by QRCatcher;
QRCatcherPadUITests.m is compiled only by QRCatcherUITests. The deterministic
generator's app and UI source loops include those existing files. No source
inventory, project, scheme, header search path, SDK, framework, or compile
prerequisite is changed. The six-scheme native compile gate remains unchanged
and must run on any independently admitted later native candidate.

Portable tests exercise the actual C gate/bounds/wall policy, actual DEBUG and
Release preprocessing, source mutations, frozen v5 behavior digests, all four
original case methods, decoder/history/Watch paths, original caps/fences/audits,
and the one-getter/no-new-transport contract. They do not prove native API
availability, Objective-C compilation, launch success, or UI correctness.
