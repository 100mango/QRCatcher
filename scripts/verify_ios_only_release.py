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
Hosted test bundles outside the selected shipping .app are outside this scope.
Archives require device/Release scope and admit no XCTest inventory or markers.
Debug admits existing fixture/startup diagnostics, while preserving every
Watch/helper/companion and shipping-inventory check. The default is Release.
Only --xctestrun in Debug/simulator/.app scope admits one exact, actual-bound
PlugIns/QRCatcherTests.xctest. Its code is bounded and inspected separately;
test-only helper/framework links are reported, never waived in parent code.
"""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import plistlib
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


DEFAULT_LIMITS = Limits()
BUNDLE_ID = '100mango.QRCatcher'
TEST_BUNDLE = 'PlugIns/QRCatcherTests.xctest'
TEST_BUNDLE_ID = '100mango.QRCatcherTests'
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


class ValidationError(ValueError):
    def __init__(self, code, detail):
        self.code = code
        self.detail = str(detail)[:400]
        super().__init__(self.detail)


def require(condition, code, detail):
    # Never use assert for admission: python -O must retain every gate.
    if not condition:
        raise ValidationError(code, detail)


def version(value):
    return '{}.{}.{}'.format(value >> 16, (value >> 8) & 255, value & 255)


def scan_bytes(data, label, release=True, allow_watch=False):
    for code, marker in BYTE_MARKERS:
        if (code == 'release_diagnostics' and not release) or (code == 'watch_presence' and allow_watch):
            continue
        require(marker not in data, code, '{}: forbidden shipping marker {}'.format(label, marker.decode('ascii', errors='replace')[:100]))


def scan_plist(info, label, limits, release=True, allow_watch=False):
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
                require(key not in WATCH_PLIST_KEYS and not key.startswith(('WKCompanion', 'WKWatchKit', 'CLKComplication')),
                        'watch_plist_key', '{}: {}'.format(label, key))
                stack.append((key, depth + 1))
                stack.append((child, depth + 1))
        elif isinstance(value, list):
            require(len(value) <= limits.plist_nodes, 'plist_limit', label)
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            lowered = value.casefold()
            require(allow_watch or (not any(marker.casefold() in lowered for marker in WATCH_MARKERS)
                    and lowered not in {'watchos', 'watchsimulator', 'watchossimulator'}), 'watch_plist_value', label)
            scan_bytes(value.encode('utf-8'), label, release, allow_watch)


def parse_plist(data, label, limits, release=True, allow_watch=False):
    require(len(data) <= limits.plist_bytes, 'plist_bytes_limit', label)
    try:
        info = plistlib.loads(data)
    except (ValueError, TypeError, OverflowError, RecursionError, plistlib.InvalidFileException,
            ExpatError, IndexError, KeyError, struct.error) as exc:
        raise ValidationError('malformed_plist', label) from exc
    require(isinstance(info, dict), 'malformed_plist', label)
    scan_plist(info, label, limits, release, allow_watch)
    return info


def check_range(offset, size, length, label):
    require(0 <= offset <= length and 0 <= size <= length - offset, 'mach_o_range', label)


def stable_stat(item):
    # Reading can update atime. Only content/identity fields belong to the
    # concurrent-change check, including nanoseconds that stat_result equality
    # would otherwise discard on some platforms.
    return (item.st_dev, item.st_ino, item.st_mode, item.st_nlink,
            item.st_size, item.st_mtime_ns, item.st_ctime_ns)


def parse_thin(data, label, limits, release=True, allow_watch=False):
    endian = THIN_MAGICS.get(data[:4])
    require(endian is not None, 'unsupported_mach_o', label)
    require(len(data) >= 32, 'truncated_mach_o', label)
    _, cpu, subtype, filetype, count, command_bytes, _, reserved = struct.unpack_from(endian + '8I', data)
    require(reserved == 0, 'malformed_mach_o', label + ': reserved header field')
    require(cpu in {0x0100000C, 0x01000007}, 'unsupported_architecture', label)
    require(filetype in {2, 6, 8}, 'unsupported_mach_o', label + ': file type')
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
    for _ in range(count):
        require(cursor + 8 <= end, 'truncated_load_command', label)
        command, size = struct.unpack_from(endian + '2I', data, cursor)
        require(size >= 8 and size % 8 == 0 and size <= end - cursor, 'malformed_load_command', label)
        chunk = memoryview(data)[cursor:cursor + size]
        if command in DYLIB_COMMANDS:
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
            scan_bytes(encoded[:terminator], label, release, allow_watch)
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
            if name.rstrip(b'\0') == b'__TEXT':
                require(fileoff == 0 and filesize >= end, 'malformed_segment', label + ': __TEXT does not contain headers')
                has_text_segment = True
            for index in range(nsects):
                section = struct.unpack_from(endian + '16s16sQQIIIIIIII', chunk, 72 + index * 80)
                sectname, segname, _, section_size, offset, align, reloff, nreloc, flags, _, _, _ = section
                require(segname == name and align <= 31, 'malformed_section', label)
                if flags & 255 not in {1, 0xC, 0x12}:  # Public zero-fill section types.
                    check_range(offset, section_size, len(data), label)
                    require(fileoff <= offset and section_size <= fileoff + filesize - offset,
                            'malformed_section', label)
                    if sectname.rstrip(b'\0') == b'__text' and section_size:
                        has_text = True
                check_range(reloff, nreloc * 8, len(data), label)
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
    require(len(platforms) == 1, 'mach_o_platform_count', label)
    require(has_text and has_text_segment, 'missing_mach_o_code', label)
    require(filetype != 2 or has_entry, 'missing_mach_o_entry', label)
    platform, minimum, sdk = platforms[0]
    require(minimum > 0 and sdk >= minimum, 'malformed_build_version', label)
    return {'cpu_type': cpu, 'cpu_subtype': subtype,
            'architecture': 'arm64' if cpu == 0x0100000C else 'x86_64',
            'file_type': filetype, 'platform': platform, 'minimum_os': version(minimum),
            'minimum_os_encoded': minimum, 'dependencies': dependencies}


def parse_mach_o(data, label, limits, release=True, allow_watch=False):
    if data[:4] in THIN_MAGICS:
        return [parse_thin(data, label, limits, release, allow_watch)]
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
        slice_info = parse_thin(data[offset:offset + length], '{} slice {}'.format(label, index), limits, release, allow_watch)
        require((slice_info['cpu_type'], slice_info['cpu_subtype']) == (cpu, subtype), 'fat_header_mismatch', label)
        result.append(slice_info)
    return result


def check_path(relative, limits, test_bound=False):
    require(len(relative.encode('utf-8')) <= limits.path_bytes, 'path_limit', relative)
    parts = Path(relative).parts
    require(len(parts) <= limits.depth, 'directory_depth_limit', relative)
    for part in parts:
        lowered = part.casefold()
        require(lowered not in {'watch', 'watchos', 'watchsimulator'} and not lowered.endswith(('.watchkitapp', '.watchkitextension')),
                'watch_inventory', relative)
        require(not lowered.endswith('.xctest') or (test_bound and part == 'QRCatcherTests.xctest'
                and (relative == TEST_BUNDLE or relative.startswith(TEST_BUNDLE + '/'))), 'release_test_bundle', relative)
        # Contents can be stripped or marker-free; declared XCTest inventory
        # itself remains forbidden outside the single actual-bound test subtree.
        require(test_bound or 'xctest' not in lowered, 'shipping_test_inventory', relative)
        require(not lowered.endswith('.app'), 'nested_app', relative)
        require(test_bound or not any(marker.casefold() in lowered for marker in WATCH_MARKERS), 'watch_inventory', relative)
        require(not test_bound or not lowered.endswith('.appex'), 'foreign_test_bundle', relative)


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


def inventory(app, limits, release=True, test_bound=False):
    files = {}
    directories = set()
    plists = {}
    binaries = {}
    test_markers = set()
    totals = {'entries': 0, 'file_bytes': 0}
    digest = hashlib.sha256()

    def visit(fd, prefix):
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
            check_path(relative, limits, test_only)
            item = os.stat(name, dir_fd=fd, follow_symlinks=False)
            require(not stat.S_ISLNK(item.st_mode), 'symlink', relative)
            if stat.S_ISDIR(item.st_mode):
                directories.add(relative)
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
                scan_bytes(data, relative, release, test_only)
                if test_only:
                    for code, marker in BYTE_MARKERS:
                        if marker in data:
                            test_markers.add((relative, code, marker.decode('ascii', errors='replace').replace('\0', '')))
                sha = hashlib.sha256(data).hexdigest()
                files[relative] = {'bytes': len(data), 'sha256': sha}
                digest.update(('F\0' + relative + '\0' + sha + '\0').encode('utf-8'))
                if name.endswith(('.plist', '.xcprivacy')):
                    plists[relative] = parse_plist(data, relative, limits, release, test_only)
                if data[:4] in MACH_MAGICS:
                    require(len(binaries) < limits.binaries, 'binary_limit', relative)
                    binaries[relative] = parse_mach_o(data, relative, limits, release, test_only)
                elif name.endswith(('.dylib', '.so', '.o', '.a')):
                    raise ValidationError('unsupported_shipping_code', relative)
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
    require(len(names) == 1 and names[0].endswith('.app'), 'archive_app_inventory', 'archive must contain exactly one shipping .app and no orphan Applications entries')
    app = real_directory(applications / names[0], 'archive shipping app')
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info_stat = os.stat('Info.plist', dir_fd=fd, follow_symlinks=False)
        data = read_regular(fd, 'Info.plist', info_stat, 'archive Info.plist', limits)
    finally:
        os.close(fd)
    info = parse_plist(data, 'archive Info.plist', limits, release)
    props = info.get('ApplicationProperties')
    require(isinstance(props, dict), 'archive_application_properties', 'archive Info.plist')
    require(props.get('ApplicationPath') == 'Applications/' + names[0]
            and props.get('CFBundleIdentifier') == BUNDLE_ID, 'archive_identity', 'archive application path/identity does not match its shipping app')
    return root, app, props


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


def verify_package(package, platform='device', configuration='Release', limits=DEFAULT_LIMITS, xctestrun=None):
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
    binding = bind_hosted_test(xctestrun, root, app, platform, configuration, limits) if xctestrun is not None else None
    files, directories, plists, binaries, totals, tree_sha, test_markers = inventory(app, limits, configuration == 'Release', binding is not None)
    info = plists.get('Info.plist')
    require(isinstance(info, dict), 'missing_bundle_info', 'shipping Info.plist')
    require(info.get('CFBundleIdentifier') == BUNDLE_ID, 'bundle_identity', 'original bundle ID must be retained')
    require(info.get('CFBundlePackageType') == 'APPL', 'bundle_package_type', 'shipping package must be APPL')
    require(info.get('CFBundleShortVersionString') == '1.1' and info.get('CFBundleVersion') == '2', 'bundle_version', 'expected version 1.1/build 2')
    require(info.get('MinimumOSVersion') == '15.0', 'bundle_minimum_os', 'expected original iOS 15.0 floor')
    families = info.get('UIDeviceFamily')
    require(isinstance(families, list) and all(type(value) is int for value in families)
            and sorted(families) == [1, 2], 'bundle_device_families', 'expected iPhone and iPad families [1, 2]')
    sdk_name, mach_platform = PLATFORMS[platform]
    require(info.get('CFBundleSupportedPlatforms') == [sdk_name], 'bundle_platform', 'expected only ' + sdk_name)
    require(info.get('NSCameraUsageDescription') == CAMERA_USAGE, 'bundle_camera_usage', 'original camera-use disclosure must be retained')
    require('Assets.car' in files and files['Assets.car']['bytes'] > 0, 'missing_compiled_assets', 'shipping Assets.car')
    require(plists.get('PrivacyInfo.xcprivacy') == EXPECTED_PRIVACY, 'privacy_manifest', 'original file-timestamp reasons and no collected data/tracking/domains must be retained')
    for key in ('CFBundleIcons', 'CFBundleIcons~ipad'):
        icons = info.get(key)
        primary = icons.get('CFBundlePrimaryIcon') if isinstance(icons, dict) else None
        icon_files = primary.get('CFBundleIconFiles') if isinstance(primary, dict) else None
        require(isinstance(primary, dict) and primary.get('CFBundleIconName') == 'AppIcon'
                and isinstance(icon_files, list) and icon_files
                and all(isinstance(name, str) and name.startswith('AppIcon') for name in icon_files), 'bundle_icons', key)
    for key in ('UIFileSharingEnabled', 'LSSupportsOpeningDocumentsInPlace'):
        require((configuration == 'Release' and key not in info)
                or (configuration == 'Debug' and info.get(key) is True), 'bundle_file_sharing', key)
    main_executable = executable_name(info, 'shipping Info.plist')
    require(main_executable == 'QRCatcher', 'bundle_executable', 'expected original QRCatcher executable')
    require(main_executable in binaries, 'missing_shipping_mach_o', main_executable)
    owners = {main_executable: 2}
    if binding is not None:
        test_info = plists.get(TEST_BUNDLE + '/Info.plist')
        require(isinstance(test_info, dict) and test_info.get('CFBundleIdentifier') == TEST_BUNDLE_ID
                and test_info.get('CFBundlePackageType') == 'BNDL'
                and executable_name(test_info, TEST_BUNDLE) == 'QRCatcherTests', 'test_bundle_identity', TEST_BUNDLE)
        test_executable = TEST_BUNDLE + '/QRCatcherTests'
        require(test_executable in binaries, 'missing_test_executable', test_executable)
        owners[test_executable] = 8
        helper_names = {marker for name, code, marker in test_markers if name == test_executable and code == 'watch_presence'}
        require({'QRWatchPhoneService', 'QRWatchSessionGate'} <= helper_names, 'missing_test_helpers', 'bound unit executable must contain its deliberate helper classes')
        require(any('WatchConnectivity.framework/' in dependency['path'] for slice_info in binaries[test_executable]
                    for dependency in slice_info['dependencies']), 'missing_test_watch_dependency', test_executable)
    for directory in sorted(directories):
        suffix = Path(directory).suffix.casefold()
        if suffix in {'.framework', '.appex', '.bundle'}:
            nested_info = plists.get(directory + '/Info.plist')
            require(suffix == '.bundle' or isinstance(nested_info, dict), 'orphan_bundle', directory)
            if nested_info and ('CFBundleExecutable' in nested_info or suffix != '.bundle'):
                executable = directory + '/' + executable_name(nested_info, directory)
                require(executable in binaries, 'orphan_bundle_executable', executable)
                owners[executable] = 6 if suffix == '.framework' else (2 if suffix == '.appex' else 8)
    for label, nested in plists.items():
        if 'CFBundleSupportedPlatforms' in nested:
            require(nested['CFBundleSupportedPlatforms'] == [sdk_name], 'nested_bundle_platform', label)
        if 'UIDeviceFamily' in nested:
            value = nested['UIDeviceFamily']
            require(isinstance(value, list) and value and all(type(family) is int and family in {1, 2} for family in value), 'nested_bundle_device_families', label)
        if label != 'Info.plist' and 'CFBundleExecutable' in nested:
            executable = str(Path(label).parent / executable_name(nested, label))
            require(Path(label).name == 'Info.plist' and str(Path(label).parent) in directories
                    and executable in owners, 'orphan_bundle_info', label)
    for relative, slices in binaries.items():
        test_only = binding is not None and relative.startswith(TEST_BUNDLE + '/')
        expected_type = owners.get(relative)
        if expected_type is None:
            framework_dylib = Path(relative).parent == Path('Frameworks') and Path(relative).suffix == '.dylib'
            debug_dylib = configuration == 'Debug' and relative in {'QRCatcher.debug.dylib', '__preview.dylib'}
            test_dylib = test_only and Path(relative).parent == Path(TEST_BUNDLE + '/Frameworks') and Path(relative).suffix == '.dylib'
            require(framework_dylib or debug_dylib or test_dylib, 'orphan_mach_o', relative)
            expected_type = 6
        for slice_info in slices:
            require(slice_info['file_type'] == expected_type, 'mach_o_file_type', relative)
            require(slice_info['platform'] == mach_platform, 'mach_o_platform', relative)
            require(platform != 'device' or slice_info['architecture'] == 'arm64', 'mach_o_architecture', relative)
            require(test_only or slice_info['minimum_os_encoded'] <= MINIMUM_OS, 'mach_o_minimum_os', relative)
            if not test_only:
                require(not any('.xctest' in dependency['path'].casefold() or 'QRCatcherTests' in dependency['path']
                                for dependency in slice_info['dependencies']), 'shipping_test_dependency', relative)
            if relative == main_executable:
                require(slice_info['minimum_os_encoded'] == MINIMUM_OS, 'mach_o_minimum_os', relative)
    if archive_props is not None:
        for key in ('CFBundleShortVersionString', 'CFBundleVersion'):
            require(archive_props.get(key) == info[key], 'archive_identity', key)
    report = {
        'schema_version': 1, 'status': 'pass',
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
        'mach_o': [{'path': name, **files[name], 'slices': slices} for name, slices in sorted(binaries.items())
                   if binding is None or not name.startswith(TEST_BUNDLE + '/')],
        'hosted_tests': None if binding is None else {
            'scope': 'exact-xctestrun-bound-test-only-subtree', 'xctestrun': binding,
            'bundle_id': TEST_BUNDLE_ID, 'executable': 'QRCatcherTests',
            'inventory': {'files': sum(name.startswith(TEST_BUNDLE + '/') for name in files),
                          'directories': sum(name == TEST_BUNDLE or name.startswith(TEST_BUNDLE + '/') for name in directories),
                          'file_bytes': sum(item['bytes'] for name, item in files.items() if name.startswith(TEST_BUNDLE + '/'))},
            'mach_o': [{'path': name, **files[name], 'slices': slices} for name, slices in sorted(binaries.items()) if name.startswith(TEST_BUNDLE + '/')],
            'permitted_test_only_markers': [{'path': name, 'category': code, 'marker': marker} for name, code, marker in test_markers],
        },
        'evidence': ['complete bounded shipping file/directory inventory', 'all shipping property lists',
                     'every recognized Mach-O and fat slice', 'dylib load-command dependencies',
                     'raw ASCII/UTF-16 helper classes, selectors and Release diagnostic markers'],
        'limits': asdict(limits),
        'limitations': 'Static unencrypted package composition only; no runtime, signing, Store, or obfuscated-code proof. Archive siblings, including hosted test bundles, are outside the shipping app scope.',
    }
    encode_report(report, limits)
    return report


def encode_report(report, limits=DEFAULT_LIMITS):
    encoded = (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode('utf-8')
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
            encoded = encode_report(report)
    sys.stdout.write(encoded.decode('utf-8'))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
