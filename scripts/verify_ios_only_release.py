#!/usr/bin/env python3
"""Bounded, read-only QRCatcher iPhone/iPad Release package inspection.

CLI: verify_ios_only_release.py PRODUCT.app|PRODUCT.xcarchive
       [--platform device|simulator] [--configuration Debug|Release]
       [--xctestrun ACTUAL.xctestrun] [--output REPORT.json]

Inspect a quiescent, unpacked build product. JSON on stdout, exit 0 on pass,
1 on validation/IO failure, 2 on invalid CLI. --output's parent must exist;
the report must be outside the input package. No Apple tools, subprocesses,
binary execution, signing, credentials, or distribution are involved.

The parser implements public header layouts, not an nm-output heuristic:
https://github.com/apple-oss-distributions/cctools/blob/main/include/mach-o/loader.h
https://github.com/apple-oss-distributions/cctools/blob/main/include/mach-o/fat.h
https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/mach/machine.h
Verified against Apple's declarations on 2026-10-06: mach_header_64,
load_command, segment_command_64/section_64, dylib_command, build_version_command,
version_min_command, symtab_command, linkedit_data_command, dyld_info_command,
encryption_info_command(_64), fat_header/fat_arch(_64), and CPU_TYPE_*.
Watch keys: https://developer.apple.com/library/archive/documentation/General/Reference/InfoPlistKeyReference/Articles/watchOSKeys.html
Debug layout: https://developer.apple.com/documentation/xcode/understanding-build-product-layout-changes
Hosted binding: https://developer.apple.com/library/archive/technotes/tn2339/_index.html
The version 2 shape follows Apple's xcodebuild.xctestrun(5) public manual:
https://keith.github.io/xcode-man-pages/xcodebuild.xctestrun.5.html
Filesystem API: https://docs.python.org/3/library/os.html (os.scandir fd,
os.open/os.stat dir_fd, os.stat follow_symlinks, O_DIRECTORY/O_NOFOLLOW).
Requires Python 3.9+ on a POSIX host exposing those capabilities; checked
explicitly at admission rather than assuming the Linux or macOS runtime.

Supported shipping code is unencrypted 64-bit arm64 device or arm64/x86_64
simulator Mach-O with LC_BUILD_VERSION, or legacy LC_VERSION_MIN_IPHONEOS.
All fat slices are inspected. Metadata, dylib load commands, and ASCII/UTF-16
helper/class/diagnostic strings are independent evidence; stripping a symbol
table cannot waive the checks. This checks package composition, not runtime,
code-sign validity, an App Store approval, or arbitrarily obfuscated code.
Archives require device/Release scope and inspect their complete bounded outer
inventory for test package/symbol/XCTest names, alongside strict shipping code.
Ordinary app symbol companions and archive metadata outside the shipping app
are inventoried but are not claimed as runtime-code or symbol-binding evidence.
Debug admits existing fixture/startup diagnostics and the exact XCTestCase
dynamic camera-permission detection name in QRCatcher's main/debug images.
That name alone is not observed XCTest runtime code. XCTest load dependencies,
other XCTest names and markers elsewhere retain their independent gates.
Debug preserves every
Watch/helper/companion and shipping-inventory check. The default is Release.
Only --xctestrun in Debug/simulator/.app scope admits one exact, actual-bound
PlugIns/QRCatcherTests.xctest. Its code is bounded and inspected separately;
test-only helper/framework links are reported, never waived in parent code.
Its optional fixed sibling QRCatcherTests.xctest.dSYM is test symbol evidence,
not runtime code: public dSYM metadata, one DWARF/QRCatcherTests MH_DSYM,
and identical architecture/LC_UUID pairs to that same bound test executable.
Optional Relocations/<boundarch>/QRCatcherTests.yml supports only dsymutil's
bounded emitted YAML mapping/flow-record shape, owned by that same binary and
Apple iOS simulator architecture. Unknown fields/formats are unsupported.
RelocationMap's triple can instead be the closed public Mach-O architecture
form arm64-apple-darwin or x86_64-apple-darwin: DebugMap uses header CPU/subtype
only. It is architecture metadata, never simulator proof. The bound executable
still requires Mach-O platform7 and exact CPU/subtype/UUID symbol pairing.
https://github.com/llvm/llvm-project/blob/93b307b610102a62bdd81deb89aaf4b824dc546b/llvm/tools/dsymutil/MachODebugMapParser.cpp
https://github.com/llvm/llvm-project/blob/93b307b610102a62bdd81deb89aaf4b824dc546b/llvm/lib/Object/MachOObjectFile.cpp
Other external resources (Swift interfaces, remarks, CAS, embedded resources)
are unsupported. __DWARF,__swift_ast remains bounded debug section evidence.
Within this exact bound MH_DSYM only, regular __DWARF sections may have zero
flags: dsymutil passes Flags=0 to MachObjectWriter.writeSection, which writes
that field directly. The public debug-attribute form remains supported; stored
instructions, nonregular types, relocations, invalid ranges and UUID mismatches
remain forbidden. Fixed official source declarations:
https://github.com/llvm/llvm-project/blob/93b307b610102a62bdd81deb89aaf4b824dc546b/llvm/tools/dsymutil/MachOUtils.cpp
https://github.com/llvm/llvm-project/blob/93b307b610102a62bdd81deb89aaf4b824dc546b/llvm/lib/MC/MachObjectWriter.cpp
Optional LC_TARGET_TRIPLE follows Apple's public target_triple_command;
symbol companions require one bounded simulator/architecture string matching
the same bound binary slice exactly. Absence on both sides is permitted.
dSYM UUID and public bundle construction sources verified on 2026-10-06:
https://developer.apple.com/documentation/xcode/building-your-app-to-include-debugging-information
https://developer.apple.com/documentation/technotes/tn3178-checking-for-and-resolving-build-uuid-problems
https://github.com/apple-oss-distributions/xnu/blob/main/EXTERNAL_HEADERS/mach-o/loader.h
https://github.com/llvm/llvm-project/blob/main/llvm/tools/dsymutil/dsymutil.cpp
https://github.com/llvm/llvm-project/blob/main/llvm/tools/dsymutil/CFBundle.cpp
https://github.com/llvm/llvm-project/blob/main/llvm/tools/dsymutil/MachOUtils.cpp
https://github.com/llvm/llvm-project/blob/main/llvm/tools/dsymutil/DwarfLinkerForBinary.cpp
https://github.com/llvm/llvm-project/blob/main/llvm/tools/dsymutil/RelocationMap.cpp
https://github.com/llvm/llvm-project/blob/main/llvm/tools/dsymutil/RelocationMap.h
https://github.com/llvm/llvm-project/blob/main/llvm/lib/MC/MCObjectFileInfo.cpp
https://github.com/apple-oss-distributions/cctools/blob/main/include/mach-o/loader.h
These declarations establish the supported format, not observed native bytes.
Validation failures may retain bounded, unqualified observations from the same
owned companion inspection: relative path/types, fixed plist keys and Mach-O
type/architecture/UUID summaries and at most 16 already-read __DWARF section
headers per slice. Omitted header counts remain explicit. No raw DWARF, symbol
names, source paths, private section content or second traversal is retained.
Independent owned-file rule failures accumulate after the same bounded reads.
Malformed file syntax blocks its dependent checks explicitly as UNKNOWN;
filesystem identity/ownership and resource-cap uncertainty stop immediately.
All findings fail the package. At most 64 fixed code/stage/owned-relative-scope
receipts share the existing half-report summary budget with symbol observations;
omission and incomplete qualification remain explicit. safe_inventory_complete
records completion of the owned inventory's stable-read/directory checks only,
and never qualifies failed metadata, code, dependencies or runtime behavior.
"""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import struct
import sys
import tempfile
from xml.parsers.expat import ExpatError


@dataclass(frozen=True)
class Limits:
    entries: int = 4096             # Files AND directories, including empty ones.
    directory_entries: int = 1024
    depth: int = 32
    path_bytes: int = 512
    file_bytes: int = 64 * 1024 * 1024
    total_bytes: int = 256 * 1024 * 1024
    plist_bytes: int = 1024 * 1024
    plist_nodes: int = 8192
    binaries: int = 64
    slices: int = 8
    load_commands: int = 4096
    load_command_bytes: int = 1024 * 1024
    sections: int = 4096
    dependency_bytes: int = 1024
    test_configurations: int = 16
    test_targets: int = 64
    report_bytes: int = 64 * 1024
    findings: int = 64


DEFAULT_LIMITS = Limits()
BUNDLE_ID = '100mango.QRCatcher'
TEST_BUNDLE = 'PlugIns/QRCatcherTests.xctest'
TEST_BUNDLE_ID = '100mango.QRCatcherTests'
TEST_SYMBOLS = TEST_BUNDLE + '.dSYM'
TEST_DWARF = TEST_SYMBOLS + '/Contents/Resources/DWARF/QRCatcherTests'
TEST_SYMBOL_FILES = {TEST_SYMBOLS + '/Contents/Info.plist', TEST_DWARF}
TEST_SYMBOL_DIRECTORIES = {TEST_SYMBOLS, TEST_SYMBOLS + '/Contents',
                           TEST_SYMBOLS + '/Contents/Resources',
                           TEST_SYMBOLS + '/Contents/Resources/DWARF'}
TEST_RELOCATIONS = TEST_SYMBOLS + '/Contents/Resources/Relocations'
RELOCATION_ARCHITECTURES = {'aarch64': 0x0100000C, 'x86_64': 0x01000007}
TEST_RELOCATION_FILES = {TEST_RELOCATIONS + '/' + architecture + '/QRCatcherTests.yml'
                         for architecture in RELOCATION_ARCHITECTURES}
TEST_RELOCATION_DIRECTORIES = {TEST_RELOCATIONS} | {
    TEST_RELOCATIONS + '/' + architecture for architecture in RELOCATION_ARCHITECTURES}
TEST_DARWIN_RELOCATION_TRIPLES = {'arm64-apple-darwin': 'aarch64',
                                'x86_64-apple-darwin': 'x86_64'}
TEST_RELOCATION_REJECTIONS = {
    'test_relocation_bytes_limit', 'test_relocation_runtime_code', 'test_relocation_encoding',
    'test_relocation_node_limit', 'unsupported_test_relocation_format',
    'unsupported_test_relocation_field', 'duplicate_test_relocation_field',
    'test_relocation_binary_path', 'test_relocation_platform', 'test_relocation_architecture',
    'test_relocation_symbol_limit', 'test_relocation_size',
}
MINIMUM_OS = 15 << 16
CAMERA_USAGE = 'QRCatcher uses the camera to scan QR codes. Camera images are not stored or uploaded.'
EXPECTED_PRIVACY = {
    'NSPrivacyAccessedAPITypes': [{'NSPrivacyAccessedAPIType': 'NSPrivacyAccessedAPICategoryFileTimestamp',
                                'NSPrivacyAccessedAPITypeReasons': ['C617.1', '3B52.1']}],
    'NSPrivacyCollectedDataTypes': [], 'NSPrivacyTracking': False, 'NSPrivacyTrackingDomains': [],
}
WATCH_PLIST_KEYS = {
    'WKApplication', 'WKWatchKitApp', 'WKCompanionAppBundleIdentifier', 'WKAppBundleIdentifier',
    'WKRunsIndependentlyOfCompanionApp', 'WKSupportsRunningWithoutiOSAppInstallation',
    'WKBackgroundModes', 'WKExtensionDelegateClassName', 'WKWatchOnly', 'WKRequiresCompanionApp',
    'NSWatchKitUsageDescription', 'CLKComplicationSupportedFamilies', 'CLKComplicationPrincipalClass',
    'CLKComplicationDescriptors', 'PUICAutoLaunchAudioOptOut',
}
PLATFORMS = {'device': ('iPhoneOS', 2), 'simulator': ('iPhoneSimulator', 7)}
THIN_MAGICS = {b'\xcf\xfa\xed\xfe': '<', b'\xfe\xed\xfa\xcf': '>'}
OTHER_THIN_MAGICS = {b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xce'}
FAT_MAGICS = {b'\xca\xfe\xba\xbe': ('>', False), b'\xbe\xba\xfe\xca': ('<', False),
              b'\xca\xfe\xba\xbf': ('>', True), b'\xbf\xba\xfe\xca': ('<', True)}
MACH_MAGICS = set(THIN_MAGICS) | OTHER_THIN_MAGICS | set(FAT_MAGICS)
DYLIB_COMMANDS = {0xC, 0xD, 0x80000018, 0x8000001F, 0x20, 0x80000023}
LINKEDIT_COMMANDS = {0x1D, 0x1E, 0x26, 0x29, 0x2B, 0x2E, 0x80000033, 0x80000034}
WATCH_MARKERS = ('WatchConnectivity', 'WatchKit.framework', 'WCSession',
                 'QRWatchPhoneService', 'QRWatchSessionGate', 'WatchPhoneTransport',
                 'QRCatcherWatch', 'com.apple.watchkit', '.watchkitapp', '.watchkitextension')
DIAGNOSTIC_MARKERS = (
    '-ui-testing', 'ui-testing.sqlite', '-fixture-payload', '-fixture-empty',
    '-reset-history', '-camera-denied', '-mini-startup-', 'mini_startup_v1=',
    'QRStartupObservation', 'QRStartupEncodedValue', 'QRStartupRecord',
    'QRStartupLaunchGate', 'QRStartupCanRecord', 'QRStartupWallComparable',
    'cameraDiagnosticEpoch', 'traceCamera:', 'QRCATCHER_CAMERA_TRACE',
    'QRCATCHER_TEST_STORE', 'QRCATCHER_SANDBOX_', 'QRCATCHER_WATCH_STORE',
    'QRCATCHER_WATCH_LAYOUT_', 'QRCATCHER_TV_TEST_STORE', 'QRCATCHER_TV_LAYOUT_',
    'QRCatcherExportTestReceipts', 'Export readback verification failed',
    'XCTest.framework', 'XCTestCase', 'XCTestObservation',
)
# Search actual bytes, including stripped Objective-C runtime class names,
# selectors and strings, without invoking strings/nm or trusting their output.
BYTE_MARKERS = tuple((label, value.encode(encoding))
                     for label, values in (('watch_presence', WATCH_MARKERS),
                                           ('release_diagnostics', DIAGNOSTIC_MARKERS))
                     for value in values for encoding in ('ascii', 'utf-16-le', 'utf-16-be'))
TEST_BYTE_MARKERS = {value.encode(encoding) for value in ('XCTest.framework', 'XCTestCase', 'XCTestObservation')
                     for encoding in ('ascii', 'utf-16-le', 'utf-16-be')}
DEBUG_DETECTION_IMAGES = {'QRCatcher', 'QRCatcher.debug.dylib', '__preview.dylib'}
DEBUG_DETECTION_BYTES = {value.encode(encoding): encoding for encoding in ('ascii', 'utf-16-le', 'utf-16-be')
                         for value in ('XCTestCase',)}
DEBUG_TEXT_UNITS = {encoding: {chr(value).encode(encoding) for value in range(32, 127)}
                    for encoding in DEBUG_DETECTION_BYTES.values()}


class ValidationError(ValueError):
    def __init__(self, code, detail):
        self.code = code
        self.detail = str(detail)[:400]
        super().__init__(self.detail)


def require(condition, code, detail):
    # Never use assert for admission: python -O must retain every gate.
    if not condition:
        raise ValidationError(code, detail)


class PackageFindings:
    """Finite package-rule receipts; no retry, rescan or parser recovery."""
    def __init__(self, limits):
        self.limits = limits
        self.cap = min(limits.findings, 64) if type(limits.findings) is int and limits.findings > 0 else 64
        self.summary_budget = limits.report_bytes // 2 if type(limits.report_bytes) is int and limits.report_bytes > 0 else DEFAULT_LIMITS.report_bytes // 2
        self.items = []
        self.first = None
        self.omitted = 0
        self.complete = True
        self.safe_inventory_complete = False
        self.identity = {}

    def add(self, error, stage, scope):
        if self.first is None:
            self.first = error
        item = {'code': error.code, 'stage': stage, 'scope': scope}
        if item in self.items:
            return
        if len(self.items) < self.cap:
            self.items.append(item)
        else:
            self.omitted += 1
            self.complete = False

    def check(self, condition, code, detail, stage, scope):
        if not condition:
            self.add(ValidationError(code, detail), stage, scope)
        return bool(condition)

    def unknown(self, scope, checks):
        self.complete = False
        self.add(ValidationError('dependent_checks_unknown', 'UNKNOWN: ' + checks), 'dependent-checks', scope)

    def file_error(self, error, stage, scope):
        # Every resource cap and filesystem/identity uncertainty is still an
        # immediate stop. Syntax failures only block this owned file's checks.
        if error.code.endswith('_limit'):
            raise error
        self.add(error, stage, scope)
        self.unknown(scope, 'invalid file syntax or unsupported format blocks dependent qualification')

    def reject(self):
        if self.first is not None:
            raise self.first


def debug_detection_name(data, marker):
    """Admit only complete encoded name tokens, never a dependency path."""
    offset = data.find(marker)
    original_encoding = DEBUG_DETECTION_BYTES[marker]
    original_unit = 1 if original_encoding == 'ascii' else 2
    while offset >= 0:
        end = offset + len(marker)
        if offset >= original_unit and data[offset - original_unit:offset] in DEBUG_TEXT_UNITS[original_encoding]:
            return False
        complete_token = False
        # UTF-16 endian searches can also match one byte into the other endian
        # spelling, including its terminator. Qualify the complete surrounding
        # token in either encoding instead of rejecting that overlap.
        for candidate, encoding in DEBUG_DETECTION_BYTES.items():
            unit = 1 if encoding == 'ascii' else 2
            text_units = DEBUG_TEXT_UNITS[encoding]
            for start in (offset - 1, offset, offset + 1):
                finish = start + len(candidate)
                if (start < 0 or start > offset or finish + unit < end
                        or data[start:finish] != candidate):
                    continue
                if ((start < unit or data[start - unit:start] not in text_units)
                        and (finish == len(data) or data[finish:finish + unit] == b'\0' * unit)):
                    complete_token = True
                    break
            if complete_token:
                break
        if not complete_token:
            return False
        offset = data.find(marker, end)
    return True


def version(value):
    return '{}.{}.{}'.format(value >> 16, (value >> 8) & 255, value & 255)


def scan_bytes(data, label, release=True, allow_watch=False, findings=None, dynamic_detection=False):
    for code, marker in BYTE_MARKERS:
        if ((code == 'release_diagnostics' and not release and (allow_watch or marker not in TEST_BYTE_MARKERS))
                or (code == 'watch_presence' and allow_watch)):
            continue
        if (not release and dynamic_detection and marker in DEBUG_DETECTION_BYTES
                and debug_detection_name(data, marker)):
            continue
        detail = '{}: forbidden shipping marker {}'.format(label, marker.decode('ascii', errors='replace')[:100])
        if findings is None:
            require(marker not in data, code, detail)
        else:
            findings.check(marker not in data, code, detail, 'markers', label)


def scan_plist(info, label, limits, release=True, allow_watch=False, findings=None):
    stack = [(info, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        require(nodes <= limits.plist_nodes and depth <= limits.depth, 'plist_limit', label)
        if isinstance(value, dict):
            require(len(value) <= limits.plist_nodes, 'plist_limit', label)
            for key, child in value.items():
                require(isinstance(key, str), 'malformed_plist', label)
                condition = key not in WATCH_PLIST_KEYS and not key.startswith(('WKCompanion', 'WKWatchKit', 'CLKComplication'))
                if findings is None:
                    require(condition, 'watch_plist_key', '{}: {}'.format(label, key))
                else:
                    findings.check(condition, 'watch_plist_key', '{}: {}'.format(label, key), 'plist', label)
                stack.append((key, depth + 1))
                stack.append((child, depth + 1))
        elif isinstance(value, list):
            require(len(value) <= limits.plist_nodes, 'plist_limit', label)
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            lowered = value.casefold()
            condition = allow_watch or (not any(marker.casefold() in lowered for marker in WATCH_MARKERS)
                    and lowered not in {'watchos', 'watchsimulator', 'watchossimulator'})
            if findings is None:
                require(condition, 'watch_plist_value', label)
            else:
                findings.check(condition, 'watch_plist_value', label, 'plist', label)
            scan_bytes(value.encode('utf-8'), label, release, allow_watch, findings)


def parse_plist(data, label, limits, release=True, allow_watch=False, findings=None):
    require(len(data) <= limits.plist_bytes, 'plist_bytes_limit', label)
    try:
        info = plistlib.loads(data)
    except (ValueError, TypeError, OverflowError, RecursionError, plistlib.InvalidFileException,
            ExpatError, IndexError, KeyError, struct.error) as exc:
        raise ValidationError('malformed_plist', label) from exc
    require(isinstance(info, dict), 'malformed_plist', label)
    scan_plist(info, label, limits, release, allow_watch, findings)
    return info


def check_range(offset, size, length, label):
    require(0 <= offset <= length and 0 <= size <= length - offset, 'mach_o_range', label)


def stable_stat(item):
    # Reading can update atime. Only content/identity fields belong to the
    # concurrent-change check, including nanoseconds that stat_result equality
    # would otherwise discard on some platforms.
    return (item.st_dev, item.st_ino, item.st_mode, item.st_nlink,
            item.st_size, item.st_mtime_ns, item.st_ctime_ns)


def parse_thin(data, label, limits, release=True, allow_watch=False, symbol_companion=False, slice_observations=None, findings=None, finding_scope=None):
    endian = THIN_MAGICS.get(data[:4])
    require(endian is not None, 'unsupported_mach_o', label)
    require(len(data) >= 32, 'truncated_mach_o', label)
    _, cpu, subtype, filetype, count, command_bytes, _, reserved = struct.unpack_from(endian + '8I', data)
    observed = None
    if slice_observations is not None:
        observed = {'index': len(slice_observations), 'file_type': filetype,
                    'cpu_type': cpu, 'cpu_subtype': subtype,
                    'architecture': {0x0100000C: 'arm64', 0x01000007: 'x86_64'}.get(cpu, 'unsupported'),
                    'uuid': None, 'uuid_commands_observed': 0}
        slice_observations.append(observed)
    require(reserved == 0, 'malformed_mach_o', label + ': reserved header field')
    require(cpu in {0x0100000C, 0x01000007}, 'unsupported_architecture', label)
    require(filetype in ({0xA} if symbol_companion else {2, 6, 8}),
            'test_symbol_file_type' if symbol_companion else 'unsupported_mach_o', label + ': file type')
    require(0 < count <= limits.load_commands and command_bytes <= limits.load_command_bytes,
            'load_command_limit', label)
    require(command_bytes >= count * 8, 'malformed_load_commands', label)
    check_range(32, command_bytes, len(data), label)
    cursor = 32
    end = 32 + command_bytes
    platforms = []
    dependencies = []
    sections = 0
    has_text = False
    has_text_segment = False
    has_entry = False
    uuids = []
    target_triples = []
    has_debug_info = False
    for _ in range(count):
        require(cursor + 8 <= end, 'truncated_load_command', label)
        command, size = struct.unpack_from(endian + '2I', data, cursor)
        require(size >= 8 and size % 8 == 0 and size <= end - cursor, 'malformed_load_command', label)
        require(not symbol_companion or command in {0x1B, 0x32, 0x2, 0x19, 0x39},
                'test_symbol_load_command', '{}: unsupported symbol load command 0x{:x}'.format(label, command))
        chunk = memoryview(data)[cursor:cursor + size]
        if command == 0x1B:  # Apple's uuid_command: cmd, cmdsize, uuid[16].
            if observed is not None:
                observed['uuid_commands_observed'] += 1
            require(size == 24, 'malformed_uuid_command', label)
            if observed is not None and observed['uuid'] is None:
                observed['uuid'] = bytes(chunk[8:24]).hex()
            require(not uuids, 'duplicate_uuid_command', label)
            require(any(chunk[8:24]), 'invalid_uuid', label)
            uuids.append(bytes(chunk[8:24]).hex())
        elif command == 0x39:  # target_triple_command: cmd, cmdsize, lc_str.
            require(size >= 16, 'malformed_target_triple_command', label)
            require(not target_triples, 'duplicate_target_triple_command', label)
            offset = struct.unpack_from(endian + 'I', chunk, 8)[0]
            require(12 <= offset < size and not any(chunk[12:offset]),
                    'malformed_target_triple_command', label)
            encoded = bytes(chunk[offset:])
            terminator = encoded.find(b'\0')
            require(0 < terminator <= limits.dependency_bytes and not any(encoded[terminator:]),
                    'malformed_target_triple_command', label)
            try:
                triple = encoded[:terminator].decode('ascii')
            except UnicodeError as exc:
                raise ValidationError('malformed_target_triple_command', label) from exc
            require(re.fullmatch(r'[A-Za-z0-9_.+-]+', triple) is not None,
                    'malformed_target_triple_command', label)
            scan_bytes(encoded[:terminator], finding_scope or label, release, allow_watch, findings)
            if observed is not None:
                observed['target_triple'] = triple
            if symbol_companion:
                match = re.fullmatch(r'(aarch64|arm64|x86_64)-apple-ios(?:[0-9]+(?:\.[0-9]+){0,2})?-simulator', triple)
                require(match is not None, 'test_symbol_target_platform', label)
                require((match[1] in {'aarch64', 'arm64'}) == (cpu == 0x0100000C),
                        'test_symbol_target_architecture', label)
            target_triples.append(triple)
        elif command in DYLIB_COMMANDS:
            require(size >= 32, 'malformed_dylib_command', label)
            offset = struct.unpack_from(endian + 'I', chunk, 8)[0]
            require(24 <= offset < size, 'malformed_dylib_command', label)
            encoded = bytes(chunk[offset:])
            terminator = encoded.find(b'\0')
            require(0 < terminator <= limits.dependency_bytes, 'malformed_dylib_command', label)
            require(not any(encoded[terminator:]), 'malformed_dylib_command', label + ': nonzero string padding')
            try:
                name = encoded[:terminator].decode('utf-8')
            except UnicodeError as exc:
                raise ValidationError('malformed_dylib_command', label) from exc
            scan_bytes(encoded[:terminator], finding_scope or label, release, allow_watch, findings)
            dependencies.append({'command': command, 'path': name})
        elif command == 0x32:  # LC_BUILD_VERSION + ntools * build_tool_version.
            require(size >= 24, 'malformed_build_version', label)
            platform, minimum, sdk, tools = struct.unpack_from(endian + '4I', chunk, 8)
            require(size == 24 + tools * 8, 'malformed_build_version', label)
            platforms.append((platform, minimum, sdk))
        elif command in {0x24, 0x25, 0x2F, 0x30}:
            require(size == 16, 'malformed_build_version', label)
            minimum, sdk = struct.unpack_from(endian + '2I', chunk, 8)
            platform = {0x24: 1, 0x25: 7 if cpu == 0x01000007 else 2, 0x2F: 3, 0x30: 4}[command]
            platforms.append((platform, minimum, sdk))
        elif command in {0x21, 0x2C}:
            # 32-bit encryption commands have size 20, and are unsupported in
            # this 64-bit-only shipping gate; LC_ENCRYPTION_INFO_64 is size 24.
            require(command == 0x2C and size == 24, 'malformed_encryption_command', label)
            cryptoff, cryptsize, cryptid, pad = struct.unpack_from(endian + '4I', chunk, 8)
            check_range(cryptoff, cryptsize, len(data), label)
            require(cryptid == 0 and pad == 0, 'encrypted_mach_o', label)
        elif command == 0x19:  # LC_SEGMENT_64 and all section_64 entries.
            require(size >= 72, 'malformed_segment', label)
            segment = struct.unpack_from(endian + 'II16sQQQQIIII', chunk)
            _, _, name, _, memory_size, fileoff, filesize, _, _, nsects, _ = segment
            require(size == 72 + nsects * 80, 'malformed_segment', label)
            sections += nsects
            require(sections <= limits.sections, 'section_limit', label)
            check_range(fileoff, filesize, len(data), label)
            require(memory_size >= filesize, 'malformed_segment', label)
            segment_name = name.rstrip(b'\0')
            if symbol_companion:
                # dsymutil retains virtual addresses for original sections,
                # but only __DWARF, symbol tables and __eh_frame have bytes.
                require(not filesize or segment_name in {b'__DWARF', b'__LINKEDIT', b'__TEXT'},
                        'test_symbol_runtime_code', label)
                require((filesize and fileoff >= end) or (not filesize and fileoff == 0),
                        'test_symbol_runtime_code', label)
            elif segment_name == b'__TEXT':
                require(fileoff == 0 and filesize >= end, 'malformed_segment', label + ': __TEXT does not contain headers')
                has_text_segment = True
            has_eh_frame = False
            for index in range(nsects):
                section = struct.unpack_from(endian + '16s16sQQIIIIIIII', chunk, 72 + index * 80)
                sectname, segname, _, section_size, offset, align, reloff, nreloc, flags, _, _, _ = section
                require(segname == name and align <= 31, 'malformed_section', label)
                section_name = sectname.rstrip(b'\0')
                if symbol_companion and segment_name == b'__DWARF':
                    if observed is not None:
                        headers = observed.setdefault('debug_sections', [])
                        observed['debug_section_headers_observed'] = observed.get('debug_section_headers_observed', 0) + 1
                        if len(headers) < 16:
                            headers.append({'segment': segment_name.decode('ascii', errors='backslashreplace'),
                                            'section': section_name.decode('ascii', errors='backslashreplace'),
                                            'flags': flags, 'type': flags & 255, 'bytes': section_size,
                                            'file_offset': offset, 'relocations': nreloc})
                        else:
                            observed['debug_section_headers_omitted'] = observed.get('debug_section_headers_omitted', 0) + 1
                    # dsymutil writes flags=0 in companion headers; S_ATTR_DEBUG
                    # is an object-section attribute, not required on MH_DSYM.
                    require((flags == 0 or flags & 0x02000000) and flags & 255 == 0,
                            'test_symbol_debug_section', label)
                if symbol_companion and segment_name != b'__DWARF' and section_name != b'__eh_frame':
                    require(offset == 0 and reloff == 0 and nreloc == 0,
                            'test_symbol_runtime_code', label + ': stored original section')
                elif flags & 255 not in {1, 0xC, 0x12}:  # Public zero-fill section types.
                    check_range(offset, section_size, len(data), label)
                    require(fileoff <= offset and section_size <= fileoff + filesize - offset,
                            'malformed_section', label)
                    if symbol_companion:
                        require(not nreloc and not flags & 0x80000400, 'test_symbol_runtime_code', label)
                        if segment_name == b'__DWARF':
                            has_debug_info |= section_name == b'__debug_info' and section_size > 0
                        else:
                            require(segment_name == b'__TEXT' and section_name == b'__eh_frame'
                                    and offset == fileoff and section_size == filesize,
                                    'test_symbol_runtime_code', label)
                            has_eh_frame = True
                    elif section_name == b'__text' and section_size:
                        has_text = True
                check_range(reloff, nreloc * 8, len(data), label)
            require(not symbol_companion or segment_name != b'__TEXT' or not filesize or has_eh_frame,
                    'test_symbol_runtime_code', label + ': stored __TEXT without __eh_frame')
        elif command == 0x2:  # LC_SYMTAB: bounded nlist_64 and string table.
            require(size == 24, 'malformed_symtab', label)
            symoff, nsyms, stroff, strsize = struct.unpack_from(endian + '4I', chunk, 8)
            check_range(symoff, nsyms * 16, len(data), label)
            check_range(stroff, strsize, len(data), label)
            require(not nsyms or (symoff >= end and strsize > 0), 'malformed_symtab', label)
            require(not strsize or stroff >= end, 'malformed_symtab', label)
        elif command in LINKEDIT_COMMANDS:
            require(size == 16, 'malformed_linkedit', label)
            offset, length = struct.unpack_from(endian + '2I', chunk, 8)
            check_range(offset, length, len(data), label)
        elif command in {0x22, 0x80000022}:
            require(size == 48, 'malformed_dyld_info', label)
            pairs = struct.unpack_from(endian + '10I', chunk, 8)
            for index in range(0, 10, 2):
                check_range(pairs[index], pairs[index + 1], len(data), label)
        elif command == 0x80000028:  # LC_MAIN entry_point_command.
            require(size == 24, 'malformed_entry_point', label)
            entryoff = struct.unpack_from(endian + 'Q', chunk, 8)[0]
            require(end <= entryoff < len(data), 'malformed_entry_point', label)
            has_entry = True
        elif command == 0x1:  # A 32-bit segment cannot hide inside our 64-bit scope.
            raise ValidationError('unsupported_mach_o', label + ': LC_SEGMENT')
        cursor += size
    require(cursor == end, 'malformed_load_commands', label)
    require(len(platforms) <= 1 if symbol_companion else len(platforms) == 1, 'mach_o_platform_count', label)
    require(has_debug_info if symbol_companion else has_text and has_text_segment,
            'missing_test_symbol_debug_info' if symbol_companion else 'missing_mach_o_code', label)
    require(filetype != 2 or has_entry, 'missing_mach_o_entry', label)
    platform, minimum, sdk = platforms[0] if platforms else (None, None, None)
    require(not platforms or (minimum > 0 and sdk >= minimum), 'malformed_build_version', label)
    return {'cpu_type': cpu, 'cpu_subtype': subtype,
            'architecture': 'arm64' if cpu == 0x0100000C else 'x86_64',
            'file_type': filetype, 'platform': platform, 'minimum_os': version(minimum) if minimum is not None else None,
            'minimum_os_encoded': minimum, 'dependencies': dependencies,
            'uuid': uuids[0] if uuids else None,
            'target_triple': target_triples[0] if target_triples else None}


def parse_mach_o(data, label, limits, release=True, allow_watch=False, symbol_companion=False, slice_observations=None, findings=None):
    if data[:4] in THIN_MAGICS:
        return [parse_thin(data, label, limits, release, allow_watch, symbol_companion, slice_observations, findings, label)]
    require(data[:4] in FAT_MAGICS, 'unsupported_mach_o', label)
    endian, wide = FAT_MAGICS[data[:4]]
    require(len(data) >= 8, 'truncated_fat_header', label)
    count = struct.unpack_from(endian + 'I', data, 4)[0]
    require(0 < count <= limits.slices, 'fat_slice_limit', label)
    entry_size = 32 if wide else 20
    table_end = 8 + count * entry_size
    require(table_end <= len(data), 'truncated_fat_table', label)
    result = []
    ranges = []
    identities = set()
    for index in range(count):
        entry = struct.unpack_from(endian + ('IIQQII' if wide else 'IIIII'), data, 8 + index * entry_size)
        cpu, subtype, offset, length, alignment = entry[:5]
        require(not wide or entry[5] == 0, 'malformed_fat_slice', label)
        require(alignment <= 31 and offset >= table_end and offset % (1 << alignment) == 0,
                'malformed_fat_slice', label)
        require(length >= 32, 'truncated_fat_slice', label)
        check_range(offset, length, len(data), label)
        require(all(offset + length <= left or offset >= right for left, right in ranges), 'overlapping_fat_slices', label)
        require((cpu, subtype) not in identities, 'duplicate_fat_slice', label)
        identities.add((cpu, subtype))
        ranges.append((offset, offset + length))
        slice_info = parse_thin(data[offset:offset + length], '{} slice {}'.format(label, index), limits,
                                release, allow_watch, symbol_companion, slice_observations, findings, label)
        require((slice_info['cpu_type'], slice_info['cpu_subtype']) == (cpu, subtype), 'fat_header_mismatch', label)
        result.append(slice_info)
    return result


def check_path(relative, limits, test_bound=False, symbol_bound=False, findings=None):
    require(len(relative.encode('utf-8')) <= limits.path_bytes, 'path_limit', relative)
    parts = Path(relative).parts
    require(len(parts) <= limits.depth, 'directory_depth_limit', relative)
    check = require if findings is None else lambda condition, code, detail: findings.check(condition, code, detail, 'inventory-rules', relative)
    for part in parts:
        lowered = part.casefold()
        check(lowered not in {'watch', 'watchos', 'watchsimulator'} and not lowered.endswith(('.watchkitapp', '.watchkitextension')),
                'watch_inventory', relative)
        check(not lowered.endswith('.xctest') or (test_bound and part == 'QRCatcherTests.xctest'
                and (relative == TEST_BUNDLE or relative.startswith(TEST_BUNDLE + '/'))), 'release_test_bundle', relative)
        # Contents can be stripped or marker-free; declared XCTest inventory
        # itself remains forbidden outside the single actual-bound test subtree.
        check(test_bound or symbol_bound or 'xctest' not in lowered, 'shipping_test_inventory', relative)
        check(symbol_bound or not lowered.endswith('.dsym'), 'test_symbol_path', relative)
        check(not lowered.endswith('.app'), 'nested_app', relative)
        check(test_bound or symbol_bound or not any(marker.casefold() in lowered for marker in WATCH_MARKERS), 'watch_inventory', relative)
        check(not test_bound or not lowered.endswith('.appex'), 'foreign_test_bundle', relative)


def read_regular(directory_fd, name, expected, label, limits):
    require(stat.S_ISREG(expected.st_mode), 'unsupported_file_type', label)
    require(expected.st_nlink == 1, 'hardlinked_file', label)
    require(expected.st_size <= limits.file_bytes, 'file_bytes_limit', label)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(name, flags, dir_fd=directory_fd)
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        require(stable_stat(before) == stable_stat(expected), 'package_changed', label)
        require(stat.S_ISREG(before.st_mode), 'unsupported_file_type', label)
        data = source.read(min(limits.file_bytes, before.st_size) + 1)
        after = os.fstat(source.fileno())
        require(len(data) == before.st_size and stable_stat(before) == stable_stat(after), 'package_changed', label)
    return data


def check_archive_path(relative, limits, shipping_app, findings=None):
    require(len(relative.encode('utf-8')) <= limits.path_bytes, 'path_limit', relative)
    parts = Path(relative).parts
    require(len(parts) <= limits.depth, 'directory_depth_limit', relative)
    check = require if findings is None else lambda condition, code, detail: findings.check(condition, code, detail, 'archive-inventory', relative)
    for index, part in enumerate(parts):
        lowered = part.casefold()
        check('xctest' not in lowered and not (lowered.endswith('.dsym') and 'tests' in lowered),
                'archive_test_inventory', relative)
        check(not lowered.endswith('.app') or str(Path(*parts[:index + 1])) == shipping_app,
                'archive_app_inventory', relative)


def relocation_scalar(value, label):
    """The bounded scalar subset emitted by LLVM YAML Output, not full YAML."""
    if value.startswith("'"):
        require(re.fullmatch(r"'(?:[^']|'')*'", value) is not None, 'unsupported_test_relocation_format', label)
        return value[1:-1].replace("''", "'")
    if value.startswith('"'):
        try:
            result = json.loads(value)
        except (ValueError, RecursionError) as exc:
            raise ValidationError('unsupported_test_relocation_format', label) from exc
        require(isinstance(result, str), 'unsupported_test_relocation_format', label)
        return result
    require(value and not any(character in value for character in "{}[],:#&*!|>%@'\"\\")
            and not value.startswith(('-', '?')), 'unsupported_test_relocation_format', label)
    return value


def parse_test_relocations(data, label, limits, test_binary, observation=None, findings=None):
    rejected_stage = None
    def check(condition, code):
        nonlocal rejected_stage
        if findings is None:
            require(condition, code, label)
        elif not condition:
            findings.check(False, code, label, 'relocation-metadata', label)
            if rejected_stage is None:
                rejected_stage = observation.get('stage') if observation is not None else 'metadata'
                if observation is not None:
                    observation['rejection_enum'] = code
        return bool(condition)
    if observation is not None:
        observation['stage'] = 'encoding'
    require(len(data) <= limits.plist_bytes, 'test_relocation_bytes_limit', label)
    require(data[:4] not in MACH_MAGICS, 'test_relocation_runtime_code', label)
    try:
        value = data.decode('utf-8')
    except UnicodeError as exc:
        raise ValidationError('test_relocation_encoding', label) from exc
    require(all(character.isprintable() or character in '\n\r' for character in value),
            'test_relocation_encoding', label)
    lines = value.splitlines()
    if observation is not None:
        observation['stage'] = 'document-structure'
        observation['lines_observed'] = len(lines)
    require(len(lines) <= limits.plist_nodes, 'test_relocation_node_limit', label)
    require(len(lines) >= 5 and lines[0] == '---' and lines[-1] == '...',
            'unsupported_test_relocation_format', label)
    fields = {}
    rows = []
    for line in lines[1:-1]:
        if line.startswith('  - '):
            require('relocations' in fields and fields['relocations'] == '',
                    'unsupported_test_relocation_format', label)
            rows.append(line[4:].strip())
            continue
        match = re.fullmatch(r'([a-z-]+): *(.*)', line)
        require(match is not None and not rows, 'unsupported_test_relocation_format', label)
        key, text = match.groups()
        require(key in {'triple', 'binary-path', 'relocations'}, 'unsupported_test_relocation_field', label)
        require(key not in fields, 'duplicate_test_relocation_field', label)
        fields[key] = text
    require(set(fields) == {'triple', 'binary-path', 'relocations'}
            and fields['relocations'] in {'', '[]'}
            and (bool(rows) or fields['relocations'] == '[]'), 'unsupported_test_relocation_format', label)
    triple = relocation_scalar(fields['triple'], label)
    binary_path = relocation_scalar(fields['binary-path'], label)
    path_matched = binary_path == str(test_binary)
    if observation is not None:
        observation['stage'] = 'binary-path-binding'
        observation['declared_version'] = 'absent-in-this-format'
        observation['top_field_types'] = {'triple': 'scalar-string', 'binary-path': 'scalar-string',
                                         'relocations': 'flow-record-sequence'}
        encoded = triple.encode('utf-8')
        observation['triple_bytes'] = len(encoded)
        observation['triple_sha256'] = hashlib.sha256(encoded).hexdigest()
        technical = len(encoded) <= 128 and re.fullmatch(
            r'(?:arm64|aarch64|x86_64)-apple-(?:darwin|ios|tvos|watchos|macosx)(?:[0-9]+(?:\.[0-9]+){0,2})?(?:-(?:simulator|macabi))?', triple)
        observation['triple'] = triple if technical else 'UNKNOWN: unsupported technical scalar'
        observation['binary_path_exact_match'] = path_matched
        observation['binary_path'] = TEST_BUNDLE + '/QRCatcherTests' if path_matched else 'UNKNOWN: outside exact bound executable'
        observation['relocation_rows_observed'] = len(rows)
        observation['numeric_widths_bits'] = {'offset': 64, 'size': 32, 'addend': 64,
                                             'symObjAddr': 64, 'symBinAddr': 64, 'symSize': 32}
    check(path_matched, 'test_relocation_binary_path')
    architecture = Path(label).parent.name
    triple_match = re.fullmatch(r'(aarch64|arm64|x86_64)-apple-ios(?:[0-9]+(?:\.[0-9]+){0,2})?-simulator', triple)
    darwin_architecture = TEST_DARWIN_RELOCATION_TRIPLES.get(triple)
    if observation is not None:
        observation['stage'] = 'architecture-metadata'
        observation['architecture_directory'] = architecture
        observation['triple_classification'] = ('mach-o-architecture-only' if darwin_architecture else
                                                 'explicit-ios-simulator-metadata' if triple_match else 'unsupported')
        observation['simulator_platform_proof'] = 'not-provided-by-relocation-metadata'
    if check(triple_match is not None or darwin_architecture is not None, 'test_relocation_platform'):
        triple_architecture = darwin_architecture or {'arm64': 'aarch64'}.get(triple_match[1], triple_match[1])
        check(triple_architecture == architecture, 'test_relocation_architecture')
    elif findings is not None:
        findings.unknown(label, 'relocation architecture equality requires a supported technical triple')
    if observation is not None:
        observation['stage'] = 'relocation-records'
    nodes = len(fields) + 1
    required = {'offset', 'size', 'addend', 'symName', 'symBinAddr', 'symSize'}
    for row in rows:
        require(row.startswith('{') and row.endswith('}'), 'unsupported_test_relocation_format', label)
        # Split flow fields only outside LLVM's quoted symbol strings. Tags,
        # aliases, collections, duplicate fields and multiline records fail.
        entries = []
        start = 1
        quote = None
        index = 1
        while index < len(row) - 1:
            character = row[index]
            if quote == '"' and character == '\\':
                index += 2
                continue
            if character == quote:
                if quote == "'" and index + 1 < len(row) - 1 and row[index + 1] == "'":
                    index += 2
                    continue
                quote = None
            elif quote is None and character in "'\"":
                quote = character
            elif quote is None and character == ',':
                entries.append(row[start:index].strip())
                start = index + 1
            index += 1
        require(quote is None, 'unsupported_test_relocation_format', label)
        entries.append(row[start:-1].strip())
        record = {}
        for entry in entries:
            match = re.fullmatch(r'([a-zA-Z]+): *(.*)', entry)
            require(match is not None, 'unsupported_test_relocation_format', label)
            key, text = match.groups()
            require(key in required | {'symObjAddr'}, 'unsupported_test_relocation_field', label)
            require(key not in record, 'duplicate_test_relocation_field', label)
            record[key] = relocation_scalar(text, label)
        require(required <= record.keys(), 'unsupported_test_relocation_format', label)
        nodes += len(record) + 1
        require(nodes <= limits.plist_nodes, 'test_relocation_node_limit', label)
        require(len(record['symName'].encode('utf-8')) <= limits.dependency_bytes,
                'test_relocation_symbol_limit', label)
        for key in record.keys() - {'symName'}:
            digits = 8 if key in {'size', 'symSize'} else 16
            require(re.fullmatch(r'0x[0-9a-fA-F]{1,' + str(digits) + '}', record[key]) is not None,
                    'unsupported_test_relocation_format', label)
        check(int(record['size'], 16) in {4, 8}, 'test_relocation_size')
    if observation is not None:
        observation['stage'] = rejected_stage or 'parsed-metadata-only'
    if rejected_stage is not None:
        return None
    return {'classification': 'test-symbol-relocation-metadata', 'architecture': architecture,
            'triple': triple, 'triple_classification': 'mach-o-architecture-only' if darwin_architecture else 'explicit-ios-simulator-metadata',
            'simulator_platform_proof': 'independently-validated-bound-test-mach-o-required',
            'binary_path': TEST_BUNDLE + '/QRCatcherTests', 'binary_path_exact_match': True,
            'relocation_count': len(rows)}


def inventory(app, limits, release=True, test_bound=False, archive_app=None, initial_totals=None, symbol_observations=None, findings=None):
    files = {}
    directories = set()
    plists = {}
    binaries = {}
    test_markers = set()
    binary_count = 0
    totals = dict(initial_totals) if initial_totals is not None else {'entries': 0, 'file_bytes': 0}
    digest = hashlib.sha256()
    shipping_app = str(archive_app.relative_to(app)) if archive_app is not None else None

    def visit(fd, prefix):
        nonlocal binary_count
        before = os.fstat(fd)
        # Consume at most the cap + 1, without first building an unbounded list.
        names = []
        with os.scandir(fd) as iterator:
            for entry in iterator:
                names.append(entry.name)
                require(len(names) <= limits.directory_entries, 'directory_entry_limit', prefix or '.')
        for name in sorted(names):
            relative = prefix + '/' + name if prefix else name
            totals['entries'] += 1
            require(totals['entries'] <= limits.entries, 'inventory_entry_limit', relative)
            test_only = test_bound and (relative == TEST_BUNDLE or relative.startswith(TEST_BUNDLE + '/'))
            symbol_only = test_bound and (relative == TEST_SYMBOLS or relative.startswith(TEST_SYMBOLS + '/'))
            if archive_app is not None:
                check_archive_path(relative, limits, shipping_app, findings)
            else:
                check_path(relative, limits, test_only, symbol_only, findings)
            item = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if symbol_only and symbol_observations is not None:
                kind = ('symlink' if stat.S_ISLNK(item.st_mode) else 'directory' if stat.S_ISDIR(item.st_mode)
                        else 'regular-file' if stat.S_ISREG(item.st_mode) else 'unsupported-file-type')
                entry = {'path': relative, 'type': kind}
                if stat.S_ISREG(item.st_mode):
                    entry['bytes'] = item.st_size
                symbol_observations['inventory'].append(entry)
            require(not stat.S_ISLNK(item.st_mode), 'symlink', relative)
            if symbol_only:
                require(relative in (TEST_SYMBOL_DIRECTORIES | TEST_RELOCATION_DIRECTORIES
                                     if stat.S_ISDIR(item.st_mode) else TEST_SYMBOL_FILES | TEST_RELOCATION_FILES),
                        'test_symbol_inventory', relative)
            if stat.S_ISDIR(item.st_mode):
                directories.add(relative)
                if relative == shipping_app:
                    # Already fully inspected with shipping rules; count its
                    # root entry once and share that inspection's total budget.
                    digest.update(('D\0' + relative + '\0').encode('utf-8'))
                    continue
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    actual = os.fstat(child)
                    require((actual.st_dev, actual.st_ino) == (item.st_dev, item.st_ino), 'package_changed', relative)
                    visit(child, relative)
                finally:
                    os.close(child)
                digest.update(('D\0' + relative + '\0').encode('utf-8'))
            else:
                require(stat.S_ISREG(item.st_mode), 'unsupported_file_type', relative)
                totals['file_bytes'] += item.st_size
                require(totals['file_bytes'] <= limits.total_bytes, 'total_bytes_limit', relative)
                data = read_regular(fd, name, item, relative, limits)
                if archive_app is None:
                    scan_bytes(data, relative, release, test_only or symbol_only, findings,
                               not release and relative in DEBUG_DETECTION_IMAGES)
                if test_only or symbol_only:
                    for code, marker in BYTE_MARKERS:
                        if marker in data:
                            test_markers.add((relative, code, marker.decode('ascii', errors='replace').replace('\0', '')))
                sha = hashlib.sha256(data).hexdigest()
                files[relative] = {'bytes': len(data), 'sha256': sha}
                if symbol_only and relative in TEST_RELOCATION_FILES:
                    relocation_observation = None
                    if symbol_observations is not None:
                        relocation_observation = {'path': relative, 'bytes': len(data), 'sha256': sha,
                                                  'qualification': 'unqualified'}
                        symbol_observations.setdefault('relocations', []).append(relocation_observation)
                    try:
                        relocation_map = parse_test_relocations(
                            data, relative, limits, app / TEST_BUNDLE / 'QRCatcherTests', relocation_observation, findings)
                        if relocation_map is not None:
                            files[relative]['relocation_map'] = relocation_map
                    except ValidationError as exc:
                        if relocation_observation is not None:
                            relocation_observation.setdefault('rejection_enum', exc.code if exc.code in TEST_RELOCATION_REJECTIONS
                                                              else 'UNKNOWN: relocation validation rejection')
                        if findings is None:
                            raise
                        findings.file_error(exc, 'relocation-metadata', relative)
                digest.update(('F\0' + relative + '\0' + sha + '\0').encode('utf-8'))
                if name.endswith(('.plist', '.xcprivacy')):
                    try:
                        plists[relative] = parse_plist(data, relative, limits, release,
                                                      archive_app is not None or test_only or symbol_only, findings)
                    except ValidationError as exc:
                        if findings is None:
                            raise
                        findings.file_error(exc, 'plist', relative)
                    if relative in plists and symbol_only and relative == TEST_SYMBOLS + '/Contents/Info.plist' and symbol_observations is not None:
                        keys = {}
                        for key in ('CFBundleIdentifier', 'CFBundlePackageType', 'CFBundleInfoDictionaryVersion',
                                    'CFBundleDevelopmentRegion', 'CFBundleSignature', 'CFBundleVersion',
                                    'CFBundleShortVersionString', 'CFBundleExecutable'):
                            if key in plists[relative]:
                                value = plists[relative][key]
                                keys[key] = {'type': type(value).__name__}
                                if isinstance(value, str):
                                    keys[key]['value'] = value[:200]
                                    if len(value) > 200:
                                        keys[key]['truncated'] = True
                        symbol_observations['plist'] = {'path': relative, 'keys': keys}
                    if archive_app is not None and relative in plists:
                        identifier = plists[relative].get('CFBundleIdentifier', '')
                        condition = not isinstance(identifier, str) or not (identifier.casefold().endswith('tests')
                                or 'xctest' in identifier.casefold())
                        if findings is None:
                            require(condition, 'archive_test_metadata', relative)
                        else:
                            findings.check(condition, 'archive_test_metadata', relative, 'archive-metadata', relative)
                if archive_app is None and data[:4] in MACH_MAGICS:
                    binary_count += 1
                    require(binary_count <= limits.binaries, 'binary_limit', relative)
                    slice_observations = None
                    if symbol_only and relative == TEST_DWARF and symbol_observations is not None:
                        slice_observations = []
                        symbol_observations['mach_o'].append({'path': relative, 'slices': slice_observations})
                    try:
                        binaries[relative] = parse_mach_o(data, relative, limits, release, test_only or symbol_only,
                                                        relative == TEST_DWARF and symbol_only, slice_observations, findings)
                    except ValidationError as exc:
                        if findings is None:
                            raise
                        findings.file_error(exc, 'mach-o', relative)
                elif archive_app is None and name.endswith(('.dylib', '.so', '.o', '.a')):
                    if findings is None:
                        raise ValidationError('unsupported_shipping_code', relative)
                    findings.add(ValidationError('unsupported_shipping_code', relative), 'mach-o', relative)
                    findings.unknown(relative, 'unsupported shipping code blocks Mach-O qualification')
        require(stable_stat(before) == stable_stat(os.fstat(fd)), 'package_changed', prefix or '.')

    root_fd = os.open(app, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        visit(root_fd, '')
    finally:
        os.close(root_fd)
    return files, directories, plists, binaries, totals, digest.hexdigest(), sorted(test_markers)


def real_directory(path, label):
    require(not path.is_symlink() and path.is_dir(), 'invalid_package_directory', label)
    return path.resolve(strict=True)


def select_app(package, limits, release=True):
    path = Path(package).absolute()
    require(len(str(path).encode('utf-8')) <= 4096, 'input_path_limit', 'input path')
    root = real_directory(path, 'input package')
    if path.suffix == '.app':
        return root, root, None
    require(path.suffix == '.xcarchive', 'unsupported_package', 'expected an explicit .app or .xcarchive directory')
    products = real_directory(root / 'Products', 'archive Products')
    applications = real_directory(products / 'Applications', 'archive Products/Applications')
    names = []
    with os.scandir(applications) as iterator:
        for entry in iterator:
            names.append(entry.name)
            require(len(names) <= limits.directory_entries, 'directory_entry_limit', 'archive Applications')
    require(names == ['QRCatcher.app'], 'archive_app_inventory',
            'archive Applications must contain only the metadata-bound QRCatcher.app')
    app = real_directory(applications / names[0], 'archive shipping app')
    # Archive Info.plist is read once by the complete outer inventory, then
    # qualified alongside the independent shipping metadata below.
    return root, app, {}


def executable_name(info, label):
    name = info.get('CFBundleExecutable')
    require(isinstance(name, str) and name not in {'', '.', '..'} and '/' not in name and '\\' not in name,
            'bundle_executable', label)
    return name


def bound_path(value, testroot, testhost=None):
    require(isinstance(value, str) and 0 < len(value.encode('utf-8')) <= 4096
            and '\\' not in value and '..' not in value.split('/') and '.' not in value.split('/'),
            'xctestrun_path', 'unsupported/ambiguous test artifact path')
    for token, base in (('__TESTROOT__', testroot), ('__TESTHOST__', testhost)):
        if value == token or value.startswith(token + '/'):
            require(base is not None, 'xctestrun_path', 'placeholder unavailable in this field')
            value = str(base) + value[len(token):]
            break
    require('__' not in value and Path(value).is_absolute(), 'xctestrun_path', 'unexpanded or relative test artifact path')
    path = Path(value)
    # Compare lexical, concrete paths. Resolving first would admit symbolic
    # aliases that point to an otherwise correct host/bundle.
    require(path == testroot or testroot in path.parents, 'xctestrun_path', 'test artifact must remain under the actual xctestrun root')
    current = testroot
    for part in path.relative_to(testroot).parts:
        current = current / part
        require(not current.is_symlink(), 'xctestrun_symlink', 'test artifact path contains a symbolic component')
    require(path.exists(), 'missing_test_artifact', str(path))
    return path


def bind_hosted_test(xctestrun, root, app, platform, configuration, limits):
    require(configuration == 'Debug' and platform == 'simulator' and root == app,
            'xctestrun_scope', 'hosted exception is only for an explicit Debug simulator .app, never Release/archive')
    path = Path(xctestrun).absolute()
    require(path.suffix == '.xctestrun' and not path.is_symlink(), 'xctestrun_path', 'explicit nonsymbolic .xctestrun file required')
    testroot = real_directory(path.parent, 'xctestrun parent')
    require(path.parent == testroot and app.parent.name == 'Debug-iphonesimulator'
            and app.parent.parent == testroot, 'xctestrun_root', 'xctestrun must be directly in this Debug app products root')
    fd = os.open(testroot, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        item = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        require(item.st_size <= limits.plist_bytes, 'plist_bytes_limit', 'xctestrun')
        data = read_regular(fd, path.name, item, 'xctestrun', limits)
    finally:
        os.close(fd)
    info = parse_plist(data, 'xctestrun', limits, release=False, allow_watch=True)
    metadata = info.get('__xctestrun_metadata__', {'FormatVersion': 1})
    require(isinstance(metadata, dict) and type(metadata.get('FormatVersion')) is int
            and metadata['FormatVersion'] in {1, 2}, 'xctestrun_format', 'only public format versions 1 and 2 are supported')
    targets = []
    if metadata['FormatVersion'] == 1:
        require('TestConfigurations' not in info, 'xctestrun_format', 'version 1 cannot contain version 2 test configurations')
        for name, target in info.items():
            if name in {'__xctestrun_metadata__', 'CodeCoverageBuildableInfos'}:
                continue
            require(isinstance(target, dict), 'xctestrun_target', name)
            require(target.get('BlueprintName', name) == name, 'xctestrun_target', name)
            targets.append((name, target, True))
    else:
        configurations = info.get('TestConfigurations')
        require(isinstance(configurations, list) and 0 < len(configurations) <= limits.test_configurations,
                'xctestrun_configurations', 'bounded nonempty TestConfigurations required')
        names = set()
        for config in configurations:
            require(isinstance(config, dict) and isinstance(config.get('Name'), str)
                    and config['Name'] and config['Name'] not in names
                    and type(config.get('IsEnabled', True)) is bool, 'xctestrun_configurations', 'duplicate/invalid configuration')
            names.add(config['Name'])
            entries = config.get('TestTargets')
            require(isinstance(entries, list) and entries, 'xctestrun_target', 'nonempty TestTargets required')
            for target in entries:
                require(isinstance(target, dict) and isinstance(target.get('BlueprintName'), str), 'xctestrun_target', 'BlueprintName required')
                targets.append((target['BlueprintName'], target, config.get('IsEnabled', True)))
                require(len(targets) <= limits.test_targets, 'xctestrun_target_limit', 'test target count')
    require(0 < len(targets) <= limits.test_targets, 'xctestrun_target_limit', 'test target count')
    seen = set()
    bindings = []
    expected_bundle = app / TEST_BUNDLE
    for name, target, enabled in targets:
        require(name not in seen, 'duplicate_test_binding', 'duplicate target/configuration binding')
        seen.add(name)
        require(target.get('UseDestinationArtifacts', False) is False, 'xctestrun_target', 'destination artifacts are outside package inspection')
        host = bound_path(target.get('TestHostPath'), testroot)
        bundle = bound_path(target.get('TestBundlePath'), testroot, host)
        touches_app = host == app or app in host.parents or bundle == app or app in bundle.parents
        if name == 'QRCatcherTests':
            require(enabled and host == app and bundle == expected_bundle
                    and target.get('TestHostBundleIdentifier') == BUNDLE_ID
                    and target.get('IsUITestBundle', False) is False, 'test_host_binding', 'expected one enabled QRCatcherTests binding to this exact host/bundle/owner')
            bindings.append({'target': name, 'host': str(host), 'bundle': str(bundle), 'host_bundle_id': BUNDLE_ID})
        else:
            require(not touches_app, 'foreign_test_binding', 'another test target claims the inspected host or bundle')
    require(len(bindings) == 1, 'missing_test_binding', 'expected exactly one QRCatcherTests hosted binding')
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
            'format_version': metadata['FormatVersion'], 'binding': bindings[0]}


def verify_test_symbols(files, directories, plists, binaries, test_executable, findings):
    if TEST_SYMBOLS not in directories:
        return None
    def check(condition, code, detail, scope=TEST_SYMBOLS):
        return findings.check(condition, code, detail, 'test-symbol-binding', scope)
    check(TEST_SYMBOL_DIRECTORIES <= directories and TEST_SYMBOL_FILES <= files.keys(),
          'missing_test_symbols', TEST_SYMBOLS + ': public Contents/Info.plist and unique DWARF/QRCatcherTests required')
    metadata = plists.get(TEST_SYMBOLS + '/Contents/Info.plist')
    identifiers = {'com.apple.xcode.dsym.' + TEST_BUNDLE_ID,
                   'com.apple.xcode.dsym.QRCatcherTests.xctest'}
    permitted = {'CFBundleDevelopmentRegion', 'CFBundleIdentifier', 'CFBundleInfoDictionaryVersion',
                 'CFBundlePackageType', 'CFBundleSignature', 'CFBundleShortVersionString',
                 'CFBundleVersion', 'Toolchain'}
    if isinstance(metadata, dict):
        unsupported = sorted(set(metadata) - permitted)
        check(not unsupported, 'test_symbol_metadata', TEST_SYMBOLS + ': unsupported plist keys/types ' +
              ', '.join('{}:{}'.format(key[:64], type(metadata[key]).__name__) for key in unsupported[:3]))
        check(isinstance(metadata.get('CFBundleIdentifier'), str)
              and metadata['CFBundleIdentifier'] in identifiers
              and metadata.get('CFBundlePackageType') == 'dSYM'
              and metadata.get('CFBundleInfoDictionaryVersion') == '6.0'
              and metadata.get('CFBundleDevelopmentRegion') == 'English'
              and metadata.get('CFBundleSignature') == '????'
              and isinstance(metadata.get('CFBundleVersion'), str) and metadata['CFBundleVersion']
              and all(isinstance(metadata[key], str) and metadata[key]
                      for key in ('CFBundleShortVersionString', 'Toolchain') if key in metadata),
              'test_symbol_metadata', TEST_SYMBOLS)
    else:
        check(False, 'test_symbol_metadata', TEST_SYMBOLS)
        findings.unknown(TEST_SYMBOLS, 'test symbol metadata qualification requires a parsed property list')
    if not check(TEST_DWARF in binaries, 'missing_test_symbol_mach_o', TEST_DWARF, TEST_DWARF):
        findings.unknown(TEST_DWARF, 'CPU/subtype/UUID/target binding requires a parsed symbol image')
        return None
    if test_executable not in binaries:
        findings.unknown(TEST_DWARF, 'CPU/subtype/UUID/target binding requires a parsed bound test executable')
        return None
    def pairs(slices):
        return {(value['cpu_type'], value['cpu_subtype']): value['uuid'] for value in slices}
    binary_pairs = pairs(binaries[test_executable])
    symbol_pairs = pairs(binaries[TEST_DWARF])
    binary_uuids = check(all(value is not None for value in binary_pairs.values()), 'missing_uuid_command', test_executable, test_executable)
    symbol_uuids = check(all(value is not None for value in symbol_pairs.values()), 'missing_uuid_command', TEST_DWARF, TEST_DWARF)
    check(binary_pairs.keys() == symbol_pairs.keys(), 'test_symbol_architecture', TEST_DWARF, TEST_DWARF)
    if binary_uuids and symbol_uuids:
        check(binary_pairs == symbol_pairs, 'test_symbol_uuid', TEST_DWARF, TEST_DWARF)
    else:
        findings.unknown(TEST_DWARF, 'UUID equality requires UUIDs on both parsed images')
    def triple_pairs(slices):
        return {(value['cpu_type'], value['cpu_subtype']): value['target_triple'] for value in slices}
    check(triple_pairs(binaries[test_executable]) == triple_pairs(binaries[TEST_DWARF]),
          'test_symbol_target_triple', TEST_DWARF + ': optional target triple must match the same bound binary slice', TEST_DWARF)
    for architecture, cpu in RELOCATION_ARCHITECTURES.items():
        if TEST_RELOCATIONS + '/' + architecture in directories:
            check(sum(identity[0] == cpu for identity in binary_pairs) == 1,
                  'test_relocation_architecture', TEST_RELOCATIONS + '/' + architecture, TEST_RELOCATIONS + '/' + architecture)
    resources = [{'path': path, **files[path]} for path in sorted(TEST_RELOCATION_FILES & files.keys())]
    return {'classification': 'test-symbols', 'path': TEST_SYMBOLS,
            'bound_executable': test_executable, 'metadata': metadata,
            'dwarf': {'path': TEST_DWARF, **files[TEST_DWARF], 'slices': binaries[TEST_DWARF]},
            'relocation_metadata': resources,
            'binding': 'identical-cpu-type-subtype-and-LC_UUID-for-every-slice'}


def verify_package(package, platform='device', configuration='Release', limits=DEFAULT_LIMITS, xctestrun=None):
    observations = {}
    findings = PackageFindings(limits)
    try:
        return _verify_package(package, platform, configuration, limits, xctestrun, observations, findings)
    except (ValidationError, OSError, UnicodeError, struct.error, RecursionError) as exc:
        if not isinstance(exc, ValidationError):
            exc = ValidationError('inspection_error', str(exc))
        if exc is not findings.first:
            findings.add(exc, 'inspection-stop', 'package')
            findings.safe_inventory_complete = False
            findings.complete = False
        failure = findings.first
        if observations.get('inventory'):
            # Preserve only observations already obtained under exact binding.
            # They never qualify a failed package or cause another read/scan.
            # Reserve half of the existing report budget for the failure and
            # JSON formatting. Limits are unchanged; overflow loses summaries.
            if len(json.dumps(observations, sort_keys=True, indent=2, ensure_ascii=True).encode('utf-8')) > findings.summary_budget:
                observations = {'scope': observations['scope'], 'qualification': 'unqualified',
                                'summaries_omitted': 'existing-report-budget'}
            failure.symbol_observations = observations
        # Findings and existing observations share the original half-report
        # summary budget. Saturation is explicit and can never become a pass.
        summary = {'findings': findings.items}
        if hasattr(failure, 'symbol_observations'):
            summary['test_symbol_observations'] = failure.symbol_observations
        if len(json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=True).encode('utf-8')) > findings.summary_budget:
            if hasattr(failure, 'symbol_observations'):
                failure.symbol_observations = {'scope': observations['scope'], 'qualification': 'unqualified',
                                               'summaries_omitted': 'existing-report-budget'}
                summary['test_symbol_observations'] = failure.symbol_observations
            while findings.items and len(json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=True).encode('utf-8')) > findings.summary_budget:
                findings.items.pop()
                findings.omitted += 1
                findings.complete = False
        failure.package_diagnostics = dict(findings.identity, qualification='unqualified',
            safe_inventory_complete=findings.safe_inventory_complete,
            findings=findings.items, findings_complete=findings.complete, findings_omitted=findings.omitted)
        raise failure


def _verify_package(package, platform, configuration, limits, xctestrun, symbol_observations, findings):
    require(platform in PLATFORMS, 'unsupported_platform', platform)
    require(configuration in {'Debug', 'Release'}, 'unsupported_configuration', configuration)
    require(Path(package).suffix != '.xcarchive' or (platform == 'device' and configuration == 'Release'),
            'archive_scope', 'archives require device platform and Release configuration')
    require(sys.version_info >= (3, 9) and os.name == 'posix'
            and all(hasattr(os, name) for name in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK'))
            and os.scandir in os.supports_fd
            and os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
            and os.stat in os.supports_follow_symlinks, 'unsupported_filesystem_capabilities',
            'Python 3.9+ POSIX fd-scandir, dir_fd, and no-follow filesystem capabilities are required')
    require(all(type(value) is int and value > 0 for value in asdict(limits).values()), 'invalid_limits', 'all limits must be positive integers')
    root, app, archive_props = select_app(package, limits, configuration == 'Release')
    findings.identity.update(package=str(root), app=str(app), platform=platform, configuration=configuration)
    binding = bind_hosted_test(xctestrun, root, app, platform, configuration, limits) if xctestrun is not None else None
    if binding is not None:
        symbol_observations.update(scope='exact-xctestrun-bound-test-symbol-companion', qualification='unqualified',
                                   path=TEST_SYMBOLS, inventory=[], plist=None, mach_o=[])
    files, directories, plists, binaries, totals, tree_sha, test_markers = inventory(
        app, limits, configuration == 'Release', binding is not None,
        symbol_observations=symbol_observations if binding is not None else None, findings=findings)
    outer_inventory = None
    if archive_props is not None:
        shipping_app = str(app.relative_to(root))
        for relative in files.keys() | directories:
            check_archive_path(shipping_app + '/' + relative, limits, shipping_app, findings)
        outer_files, outer_dirs, outer_plists, _, combined_totals, outer_sha, _ = inventory(
            root, limits, archive_app=app, initial_totals=totals, findings=findings)
        outer_inventory = dict(combined_totals, files=len(files) + len(outer_files),
                               directories=len(directories) + len(outer_dirs),
                               sha256=hashlib.sha256((tree_sha + outer_sha).encode('ascii')).hexdigest(),
                               scope='complete-archive-with-strict-shipping-app')
        archive_info = outer_plists.get('Info.plist')
        archive_props = archive_info.get('ApplicationProperties') if isinstance(archive_info, dict) else None
        findings.check(isinstance(archive_props, dict), 'archive_application_properties', 'archive Info.plist', 'archive-metadata', 'Info.plist')
        if isinstance(archive_props, dict):
            findings.check(archive_props.get('ApplicationPath') == 'Applications/QRCatcher.app'
                           and archive_props.get('CFBundleIdentifier') == BUNDLE_ID, 'archive_identity',
                           'archive application path/identity does not match its shipping app', 'archive-metadata', 'Info.plist')
        else:
            findings.unknown('Info.plist', 'archive identity/version qualification requires valid archive metadata')
    findings.safe_inventory_complete = True
    def check(condition, code, detail, scope='Info.plist', stage='package-metadata'):
        return findings.check(condition, code, detail, stage, scope)
    info = plists.get('Info.plist')
    sdk_name, mach_platform = PLATFORMS[platform]
    main_executable = 'QRCatcher'
    families = None
    if check(isinstance(info, dict), 'missing_bundle_info', 'shipping Info.plist'):
        check(info.get('CFBundleIdentifier') == BUNDLE_ID, 'bundle_identity', 'original bundle ID must be retained')
        check(info.get('CFBundlePackageType') == 'APPL', 'bundle_package_type', 'shipping package must be APPL')
        check(info.get('CFBundleShortVersionString') == '1.1' and info.get('CFBundleVersion') == '2', 'bundle_version', 'expected version 1.1/build 2')
        check(info.get('MinimumOSVersion') == '15.0', 'bundle_minimum_os', 'expected original iOS 15.0 floor')
        families = info.get('UIDeviceFamily')
        check(isinstance(families, list) and all(type(value) is int for value in families)
              and sorted(families) == [1, 2], 'bundle_device_families', 'expected iPhone and iPad families [1, 2]')
        check(info.get('CFBundleSupportedPlatforms') == [sdk_name], 'bundle_platform', 'expected only ' + sdk_name)
        check(info.get('NSCameraUsageDescription') == CAMERA_USAGE, 'bundle_camera_usage', 'original camera-use disclosure must be retained')
        for key in ('CFBundleIcons', 'CFBundleIcons~ipad'):
            icons = info.get(key)
            primary = icons.get('CFBundlePrimaryIcon') if isinstance(icons, dict) else None
            icon_files = primary.get('CFBundleIconFiles') if isinstance(primary, dict) else None
            check(isinstance(primary, dict) and primary.get('CFBundleIconName') == 'AppIcon'
                  and isinstance(icon_files, list) and icon_files
                  and all(isinstance(name, str) and name.startswith('AppIcon') for name in icon_files), 'bundle_icons', key)
        for key in ('UIFileSharingEnabled', 'LSSupportsOpeningDocumentsInPlace'):
            check((configuration == 'Release' and key not in info)
                  or (configuration == 'Debug' and info.get(key) is True), 'bundle_file_sharing', key)
        check(info.get('CFBundleExecutable') == main_executable, 'bundle_executable', 'expected original QRCatcher executable')
    else:
        findings.unknown('Info.plist', 'shipping identity/families/icons/executable metadata requires a parsed property list')
    check('Assets.car' in files and files['Assets.car']['bytes'] > 0, 'missing_compiled_assets', 'shipping Assets.car', 'Assets.car')
    check(plists.get('PrivacyInfo.xcprivacy') == EXPECTED_PRIVACY, 'privacy_manifest',
          'original file-timestamp reasons and no collected data/tracking/domains must be retained', 'PrivacyInfo.xcprivacy')
    check(main_executable in binaries, 'missing_shipping_mach_o', main_executable, main_executable)
    if main_executable not in binaries:
        findings.unknown(main_executable, 'shipping main-image type/platform/dependencies require a parsed Mach-O')
    # These fixed expected identities do not promote invalid metadata to a
    # qualified owner. Every independent parsed image still receives its gates.
    owners = {main_executable: 2}
    test_symbols = None
    if binding is not None:
        test_info = plists.get(TEST_BUNDLE + '/Info.plist')
        check(isinstance(test_info, dict) and test_info.get('CFBundleIdentifier') == TEST_BUNDLE_ID
              and test_info.get('CFBundlePackageType') == 'BNDL'
              and test_info.get('CFBundleExecutable') == 'QRCatcherTests', 'test_bundle_identity', TEST_BUNDLE,
              TEST_BUNDLE + '/Info.plist', 'test-binding')
        test_executable = TEST_BUNDLE + '/QRCatcherTests'
        test_parsed = check(test_executable in binaries, 'missing_test_executable', test_executable, test_executable, 'test-binding')
        owners[test_executable] = 8
        if test_parsed:
            if TEST_SYMBOLS in directories:
                symbol_observations['bound_test_binary'] = {
                    'path': test_executable,
                    'slices': [{key: value[key] for key in ('file_type', 'cpu_type', 'cpu_subtype', 'architecture', 'uuid', 'target_triple')
                                if key != 'target_triple' or value[key] is not None}
                               for value in binaries[test_executable]],
                }
            helper_names = {marker for name, code, marker in test_markers if name == test_executable and code == 'watch_presence'}
            check({'QRWatchPhoneService', 'QRWatchSessionGate'} <= helper_names, 'missing_test_helpers',
                  'bound unit executable must contain its deliberate helper classes', test_executable, 'test-binding')
            check(any('WatchConnectivity.framework/' in dependency['path'] for slice_info in binaries[test_executable]
                      for dependency in slice_info['dependencies']), 'missing_test_watch_dependency', test_executable, test_executable, 'test-binding')
        else:
            findings.unknown(test_executable, 'bound test link/type/platform and symbol binding require a parsed test executable')
        test_symbols = verify_test_symbols(files, directories, plists, binaries, test_executable, findings)
        if TEST_SYMBOLS in directories:
            owners[TEST_DWARF] = 0xA
    for directory in sorted(directories):
        suffix = Path(directory).suffix.casefold()
        if suffix in {'.framework', '.appex', '.bundle'}:
            nested_info = plists.get(directory + '/Info.plist')
            if not check(suffix == '.bundle' or isinstance(nested_info, dict), 'orphan_bundle', directory, directory, 'bundle-ownership'):
                findings.unknown(directory, 'bundle executable ownership requires valid bundle metadata')
            if nested_info and ('CFBundleExecutable' in nested_info or suffix != '.bundle'):
                try:
                    executable = directory + '/' + executable_name(nested_info, directory)
                except ValidationError as exc:
                    findings.add(exc, 'bundle-ownership', directory)
                    findings.unknown(directory, 'bundle executable ownership requires a safe executable name')
                    continue
                if not check(executable in binaries, 'orphan_bundle_executable', executable, directory, 'bundle-ownership'):
                    findings.unknown(directory, 'nested image type/platform/dependencies require a parsed declared executable')
                owners[executable] = 6 if suffix == '.framework' else (2 if suffix == '.appex' else 8)
    for label, nested in plists.items():
        if 'CFBundleSupportedPlatforms' in nested:
            check(nested['CFBundleSupportedPlatforms'] == [sdk_name], 'nested_bundle_platform', label, label, 'nested-metadata')
        if 'UIDeviceFamily' in nested:
            value = nested['UIDeviceFamily']
            check(isinstance(value, list) and value and all(type(family) is int and family in {1, 2} for family in value),
                  'nested_bundle_device_families', label, label, 'nested-metadata')
        if label != 'Info.plist' and 'CFBundleExecutable' in nested:
            try:
                executable = str(Path(label).parent / executable_name(nested, label))
            except ValidationError as exc:
                findings.add(exc, 'nested-metadata', label)
                findings.unknown(label, 'nested bundle ownership requires a safe executable name')
                continue
            check(Path(label).name == 'Info.plist' and str(Path(label).parent) in directories
                  and executable in owners, 'orphan_bundle_info', label, label, 'nested-metadata')
    for relative, slices in binaries.items():
        test_only = binding is not None and relative.startswith(TEST_BUNDLE + '/')
        symbol_only = binding is not None and TEST_SYMBOLS in directories and relative == TEST_DWARF
        expected_type = owners.get(relative)
        if expected_type is None:
            framework_dylib = Path(relative).parent == Path('Frameworks') and Path(relative).suffix == '.dylib'
            debug_dylib = configuration == 'Debug' and relative in {'QRCatcher.debug.dylib', '__preview.dylib'}
            test_dylib = test_only and Path(relative).parent == Path(TEST_BUNDLE + '/Frameworks') and Path(relative).suffix == '.dylib'
            if check(framework_dylib or debug_dylib or test_dylib, 'orphan_mach_o', relative, relative, 'mach-o-rules'):
                expected_type = 6
            else:
                findings.unknown(relative, 'image file type qualification requires a declared or closed allowed owner')
        for slice_info in slices:
            if expected_type is not None:
                check(slice_info['file_type'] == expected_type, 'mach_o_file_type', relative, relative, 'mach-o-rules')
            check(slice_info['platform'] == mach_platform or (symbol_only and slice_info['platform'] is None),
                  'mach_o_platform', relative, relative, 'mach-o-rules')
            check(platform != 'device' or slice_info['architecture'] == 'arm64', 'mach_o_architecture', relative, relative, 'mach-o-rules')
            check(test_only or symbol_only or slice_info['minimum_os_encoded'] <= MINIMUM_OS, 'mach_o_minimum_os', relative, relative, 'mach-o-rules')
            if not test_only and not symbol_only:
                check(not any('xctest' in dependency['path'].casefold() or 'qrcatchertests' in dependency['path'].casefold()
                              for dependency in slice_info['dependencies']), 'shipping_test_dependency', relative, relative, 'mach-o-rules')
            if relative == main_executable:
                check(slice_info['minimum_os_encoded'] == MINIMUM_OS, 'mach_o_minimum_os', relative, relative, 'mach-o-rules')
    if isinstance(archive_props, dict) and isinstance(info, dict):
        for key in ('CFBundleShortVersionString', 'CFBundleVersion'):
            check(archive_props.get(key) == info.get(key), 'archive_identity', key, 'Info.plist', 'archive-metadata')
    findings.reject()
    report = {
        'schema_version': 1, 'status': 'pass',
        'safe_inventory_complete': True, 'findings': [], 'findings_complete': True, 'findings_omitted': 0,
        'scope': 'ios-only-debug-hosted-test-package' if binding else 'ios-only-shipping-package',
        'package': str(root), 'app': str(app), 'platform': platform, 'configuration': configuration,
        'bundle_id': info['CFBundleIdentifier'], 'executable': main_executable,
        'version': info['CFBundleShortVersionString'], 'build': info['CFBundleVersion'],
        'minimum_os': info['MinimumOSVersion'], 'device_families': families,
        'supported_platforms': info['CFBundleSupportedPlatforms'],
        'privacy': plists['PrivacyInfo.xcprivacy'],
        'icons': {key: info[key] for key in ('CFBundleIcons', 'CFBundleIcons~ipad')},
        'assets_car_sha256': files['Assets.car']['sha256'],
        'signing': 'UNKNOWN: signatures are not inspected or validated',
        'entitlements': 'UNKNOWN: unsigned composition inspection cannot prove signed entitlements',
        'inventory': dict(totals, files=len(files), directories=len(directories), sha256=tree_sha),
        'archive_inventory': outer_inventory,
        'mach_o': [{'path': name, **files[name], 'slices': slices} for name, slices in sorted(binaries.items())
                   if binding is None or (not name.startswith(TEST_BUNDLE + '/') and name != TEST_DWARF)],
        'hosted_tests': None if binding is None else {
            'scope': 'exact-xctestrun-bound-test-only-subtree', 'xctestrun': binding,
            'bundle_id': TEST_BUNDLE_ID, 'executable': 'QRCatcherTests',
            'inventory': {'files': sum(name.startswith(TEST_BUNDLE + '/') for name in files),
                          'directories': sum(name == TEST_BUNDLE or name.startswith(TEST_BUNDLE + '/') for name in directories),
                          'file_bytes': sum(item['bytes'] for name, item in files.items() if name.startswith(TEST_BUNDLE + '/'))},
            'mach_o': [{'path': name, **files[name], 'slices': slices} for name, slices in sorted(binaries.items()) if name.startswith(TEST_BUNDLE + '/')],
            'symbols': test_symbols,
            'permitted_test_only_markers': [{'path': name, 'category': code, 'marker': marker} for name, code, marker in test_markers],
        },
        'evidence': ['complete bounded shipping file/directory inventory', 'all shipping property lists',
                     'every recognized Mach-O and fat slice', 'dylib load-command dependencies',
                     'raw ASCII/UTF-16 helper classes, selectors and Release diagnostic markers'],
        'limits': asdict(limits),
        'limitations': 'Static unencrypted package composition only; no runtime, signing, Store, or obfuscated-code proof. Archive outer files share the shipping inventory limits; ordinary outer app symbols are not parsed as shipping runtime code or proven symbol companions.',
    }
    encode_report(report, limits)
    return report


def encode_report(report, limits=DEFAULT_LIMITS):
    try:
        encoded = (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode('utf-8')
    except (ValueError, TypeError) as exc:
        raise ValidationError('report_encoding_error', 'JSON report') from exc
    require(len(encoded) <= limits.report_bytes, 'report_bytes_limit', 'JSON report')
    return encoded


def write_report(output, encoded, package):
    path = Path(output).absolute()
    require(not path.is_symlink() and path.parent.is_dir() and not path.parent.is_symlink(), 'invalid_report_destination', 'report parent must already exist without a symbolic destination')
    resolved = path.resolve()
    root = Path(package).resolve()
    require(root != resolved and root not in resolved.parents, 'report_inside_package', 'report must be outside the inspected package')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.ios-release-', dir=path.parent, delete=False) as target:
            temporary = target.name
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0], allow_abbrev=False)
    parser.add_argument('package', help='explicit existing .app or .xcarchive directory')
    parser.add_argument('--platform', choices=tuple(PLATFORMS), default='device')
    parser.add_argument('--configuration', choices=('Debug', 'Release'), default='Release')
    parser.add_argument('--xctestrun', help='explicit actual .xctestrun binding the single permitted Debug simulator hosted unit bundle')
    parser.add_argument('--output', help='optional bounded JSON report outside the package; parent must exist')
    args = parser.parse_args(argv)
    try:
        report = verify_package(args.package, args.platform, args.configuration, xctestrun=args.xctestrun)
    except (ValidationError, OSError, UnicodeError, struct.error, RecursionError) as exc:
        report = {'schema_version': 1, 'status': 'fail',
                  'reason': exc.code if isinstance(exc, ValidationError) else 'inspection_error',
                  'detail': exc.detail if isinstance(exc, ValidationError) else str(exc)[:400]}
        if isinstance(exc, ValidationError) and hasattr(exc, 'package_diagnostics'):
            report.update(exc.package_diagnostics)
        else:
            report.update(safe_inventory_complete=False, findings=[], findings_complete=False, findings_omitted=0)
        if isinstance(exc, ValidationError) and hasattr(exc, 'symbol_observations'):
            report['test_symbol_observations'] = exc.symbol_observations
    encoded = encode_report(report)
    if args.output:
        try:
            # Replace stale successful evidence with this explicit failure
            # report when validation fails. Never leave a stale pass behind.
            write_report(args.output, encoded, args.package)
        except (ValidationError, OSError) as exc:
            report = {'schema_version': 1, 'status': 'fail',
                      'reason': exc.code if isinstance(exc, ValidationError) else 'report_write_error',
                      'detail': exc.detail if isinstance(exc, ValidationError) else str(exc)[:400]}
            report.update(safe_inventory_complete=False, findings=[], findings_complete=False, findings_omitted=0)
            encoded = encode_report(report)
    sys.stdout.write(encoded.decode('utf-8'))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
