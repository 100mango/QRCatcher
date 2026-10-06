"""Synthetic package evidence only: no Apple build/runtime/signing proof.

Run both:
  python3 Tests/Harness/test_ios_only_release_package.py
  python3 -O Tests/Harness/test_ios_only_release_package.py
All admission checks and unittest assertion methods stay active under -O.
The byte builders use Apple's public layouts, without mocking native tools.
"""

from dataclasses import asdict, replace
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/verify_ios_only_release.py'
SPEC = importlib.util.spec_from_file_location('ios_only_package', SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)
ARM64 = 0x0100000C
X86_64 = 0x01000007
TEST_UUID = bytes(range(1, 17))


def dylib_command(name, command=0xC, endian='<'):
    encoded = name.encode('utf-8') + b'\0'
    size = (24 + len(encoded) + 7) & ~7
    return struct.pack(endian + '6I', command, size, 24, 0, 0x10000, 0x10000) + encoded.ljust(size - 24, b'\0')


def uuid_command(value=TEST_UUID, endian='<'):
    return struct.pack(endian + '2I', 0x1B, 24) + value


def target_triple_command(value='arm64-apple-ios17.0.0-simulator', endian='<', offset=12):
    encoded = value.encode('utf-8') + b'\0'
    size = (offset + len(encoded) + 7) & ~7
    return (struct.pack(endian + '3I', 0x39, size, offset) + b'\0' * (offset - 12)
            + encoded.ljust(size - offset, b'\0'))


def symbol_macho(cpu=ARM64, subtype=0, endian='<', uuid=TEST_UUID,
                 platform=7, filetype=0xA, extra=(), markers=b'',
                 debug_flags=0x02000000, debug_sections=1):
    """Public dsymutil layout: virtual original sections plus stored DWARF.

    These are synthetic structural fixtures, not retained Xcode dSYM bytes.
    """
    commands = []
    if uuid is not None:
        commands.append(uuid_command(uuid, endian))
    if platform is not None:
        commands.append(struct.pack(endian + '6I', 0x32, 24, platform, 17 << 16, 27 << 16, 0))
    commands.extend(extra)
    byte_count = sum(map(len, commands)) + 224 + debug_sections * 80
    data_offset = 32 + byte_count
    payload = b'synthetic DWARF\0' + markers
    text_name = b'__TEXT'.ljust(16, b'\0')
    dwarf_name = b'__DWARF'.ljust(16, b'\0')
    commands.append(struct.pack(endian + 'II16sQQQQIIII', 0x19, 152, text_name,
                                0x100000000, 0x1000, 0, 0, 5, 5, 1, 0)
                    + struct.pack(endian + '16s16sQQIIIIIIII', b'__text'.ljust(16, b'\0'), text_name,
                                  0x100000400, 256, 0, 2, 0, 0, 0x80000400, 0, 0, 0))
    commands.append(struct.pack(endian + 'II16sQQQQIIII', 0x19, 72 + debug_sections * 80, dwarf_name,
                                0x100001000, 0x1000, data_offset, len(payload) * debug_sections,
                                7, 3, debug_sections, 0)
                    + b''.join(struct.pack(endian + '16s16sQQIIIIIIII',
                                  (b'__debug_info' if index == 0 else b'__debug_line').ljust(16, b'\0'), dwarf_name,
                                  0x100001000 + index * len(payload), len(payload), data_offset + index * len(payload),
                                  0, 0, 0, debug_flags, 0, 0, 0) for index in range(debug_sections)))
    return struct.pack(endian + '8I', 0xFEEDFACF, cpu, subtype, filetype,
                        len(commands), byte_count, 0, 0) + b''.join(commands) + payload * debug_sections


def edit_dwarf_section(data, field_offset, fmt, value):
    """Mutate only the first __DWARF header of a little-endian fixture."""
    result = bytearray(data)
    offset = 32
    for _ in range(struct.unpack_from('<I', result, 16)[0]):
        command, length = struct.unpack_from('<2I', result, offset)
        if command == 0x19 and bytes(result[offset + 8:offset + 24]).rstrip(b'\0') == b'__DWARF':
            struct.pack_into('<' + fmt, result, offset + 72 + field_offset, value)
            return bytes(result)
        offset += length
    raise ValueError('Missing synthetic __DWARF segment')


def macho(platform=2, cpu=ARM64, subtype=0, filetype=2, minimum=15 << 16,
          markers=b'', endian='<', extra=(), legacy=False):
    """Minimal structurally supported synthetic 64-bit image, not runnable."""
    payload = b'\x1f\x20\x03\xd5' + markers
    commands = [struct.pack(endian + '4I', 0x25, 16, minimum, 27 << 16) if legacy else
                struct.pack(endian + '6I', 0x32, 24, platform, minimum, 27 << 16, 0)]
    commands.extend(extra)
    commands.append(dylib_command('/System/Library/Frameworks/Foundation.framework/Foundation', endian=endian))
    if filetype == 6:
        commands.append(dylib_command('@rpath/Ordinary.dylib', 0xD, endian))
    # Explicitly empty symbol table models stripping. Raw runtime/class strings
    # and load commands still need to reject forbidden code/dependencies.
    commands.append(struct.pack(endian + '6I', 2, 24, 0, 0, 0, 0))
    byte_count = sum(map(len, commands)) + 152 + (24 if filetype == 2 else 0)
    code_offset = 32 + byte_count
    file_size = code_offset + len(payload)
    segment_name = b'__TEXT'.ljust(16, b'\0')
    segment = struct.pack(endian + 'II16sQQQQIIII', 0x19, 152, segment_name,
                          0x100000000, file_size, 0, file_size, 5, 5, 1, 0)
    section = struct.pack(endian + '16s16sQQIIIIIIII', b'__text'.ljust(16, b'\0'), segment_name,
                          0x100000000 + code_offset, len(payload), code_offset, 2, 0, 0,
                          0x80000400, 0, 0, 0)
    commands.append(segment + section)
    if filetype == 2:
        commands.append(struct.pack(endian + 'IIQQ', 0x80000028, 24, code_offset, 0))
    header = struct.pack(endian + '8I', 0xFEEDFACF, cpu, subtype, filetype,
                         len(commands), byte_count, 0, 0)
    return header + b''.join(commands) + payload


def fat(slices, wide=False, endian='>'):
    entry_size = 32 if wide else 20
    table_end = 8 + len(slices) * entry_size
    output = bytearray(struct.pack(endian + '2I', 0xCAFEBABF if wide else 0xCAFEBABE, len(slices)))
    payloads = bytearray()
    for data in slices:
        slice_endian = '<' if data[:4] == b'\xcf\xfa\xed\xfe' else '>'
        cpu, subtype = struct.unpack_from(slice_endian + '2I', data, 4)
        offset = table_end + len(payloads)
        padding = (-offset) % 8
        payloads.extend(b'\0' * padding)
        offset += padding
        values = (cpu, subtype, offset, len(data), 3, 0) if wide else (cpu, subtype, offset, len(data), 3)
        output.extend(struct.pack(endian + ('IIQQII' if wide else '5I'), *values))
        payloads.extend(data)
    return bytes(output + payloads)


def edit_command(data, command, field_offset, fmt, value):
    result = bytearray(data)
    count = struct.unpack_from('<I', result, 16)[0]
    offset = 32
    for _ in range(count):
        cmd, length = struct.unpack_from('<2I', result, offset)
        if cmd == command:
            struct.pack_into('<' + fmt, result, offset + field_offset, value)
            return bytes(result)
        offset += length
    raise ValueError('Missing synthetic command')


def normalize_owned_temporary_leaf(path):
    """Give only a newly allocated empty owned leaf an unambiguous name."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError('Owned positive fixture leaf must be a real directory')
    with os.scandir(path) as entries:
        if next(entries, None) is not None:
            raise ValueError('Only an empty owned fixture leaf may be renamed')
    parent = path.resolve(strict=True).parent
    if '__' in str(parent):
        raise ValueError('Owned positive fixture has a reserved marker in an ancestor: ' + str(parent))
    destination = path.with_name('qrcatcher-fixture-' + uuid4().hex)
    path.rename(destination)
    return destination


class OwnedTemporaryDirectory:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory()
        try:
            self.name = str(normalize_owned_temporary_leaf(self.temporary.name))
        except Exception:
            self.temporary.cleanup()
            raise

    def cleanup(self):
        try:
            if Path(self.name).exists():
                shutil.rmtree(self.name)
        finally:
            self.temporary.cleanup()

    def __enter__(self):
        return self.name

    def __exit__(self, *_):
        self.cleanup()


def owned_temporary_directory():
    return OwnedTemporaryDirectory()


class IOSOnlyPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = owned_temporary_directory()
        self.addCleanup(self.temp.cleanup)
        # Own the concrete fixture directory even when macOS TMPDIR uses /var
        # for /private/var. The verifier must still reject supplied aliases.
        self.base = Path(self.temp.name).resolve(strict=True)
        self.app = self.base / 'QRCatcher.app'
        self.app.mkdir()
        self.info = {
            'CFBundleIdentifier': gate.BUNDLE_ID, 'CFBundleExecutable': 'QRCatcher',
            'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '1.1',
            'CFBundleVersion': '2', 'MinimumOSVersion': '15.0',
            'UIDeviceFamily': [1, 2], 'CFBundleSupportedPlatforms': ['iPhoneOS'],
            'NSCameraUsageDescription': 'QRCatcher uses the camera to scan QR codes. Camera images are not stored or uploaded.',
            'CFBundleIcons': {'CFBundlePrimaryIcon': {'CFBundleIconName': 'AppIcon', 'CFBundleIconFiles': ['AppIcon60x60']}},
            'CFBundleIcons~ipad': {'CFBundlePrimaryIcon': {'CFBundleIconName': 'AppIcon', 'CFBundleIconFiles': ['AppIcon60x60', 'AppIcon76x76']}},
        }
        self.write_info()
        self.write_binary(macho())
        (self.app / 'Assets.car').write_bytes(b'ordinary synthetic asset')
        (self.app / 'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps({
            'NSPrivacyAccessedAPITypes': [{'NSPrivacyAccessedAPIType': 'NSPrivacyAccessedAPICategoryFileTimestamp',
                                         'NSPrivacyAccessedAPITypeReasons': ['C617.1', '3B52.1']}],
            'NSPrivacyCollectedDataTypes': [], 'NSPrivacyTracking': False, 'NSPrivacyTrackingDomains': [],
        }))

    def write_info(self, fmt=plistlib.FMT_XML):
        (self.app / 'Info.plist').write_bytes(plistlib.dumps(self.info, fmt=fmt))

    def write_binary(self, data):
        (self.app / 'QRCatcher').write_bytes(data)

    def rejected(self, reason=None, **kwargs):
        with self.assertRaises(gate.ValidationError) as raised:
            gate.verify_package(self.app, **kwargs)
        if reason:
            self.assertEqual(raised.exception.code, reason)
        return raised.exception

    def simulator(self):
        self.info['CFBundleSupportedPlatforms'] = ['iPhoneSimulator']
        self.write_info()
        self.write_binary(macho(platform=7))

    def debug(self):
        self.info['UIFileSharingEnabled'] = True
        self.info['LSSupportsOpeningDocumentsInPlace'] = True
        self.write_info()

    def archive(self):
        archive = self.base / 'Release.xcarchive'
        applications = archive / 'Products/Applications'
        applications.mkdir(parents=True)
        destination = applications / self.app.name
        self.app.rename(destination)
        self.app = destination
        props = {'ApplicationPath': 'Applications/' + self.app.name,
                 'CFBundleIdentifier': gate.BUNDLE_ID,
                 'CFBundleShortVersionString': '1.1', 'CFBundleVersion': '2'}
        (archive / 'Info.plist').write_bytes(plistlib.dumps({'ApplicationProperties': props}))
        return archive

    def framework(self, name='Ordinary', data=None):
        folder = self.app / 'Frameworks' / (name + '.framework')
        folder.mkdir(parents=True)
        (folder / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'example.' + name, 'CFBundleExecutable': name,
            'CFBundlePackageType': 'FMWK', 'CFBundleSupportedPlatforms': self.info['CFBundleSupportedPlatforms']}))
        (folder / name).write_bytes(data if data is not None else macho(filetype=6))
        return folder

    def hosted(self, format_version=1, absolute_paths=False, ui_target=False):
        """Write actual synthetic product/xctestrun bytes in Xcode's public layout."""
        self.simulator()
        self.debug()
        products = self.base / 'Build/Products'
        destination = products / 'Debug-iphonesimulator/QRCatcher.app'
        destination.parent.mkdir(parents=True)
        self.app.rename(destination)
        self.app = destination
        self.test_bundle = self.app / gate.TEST_BUNDLE
        self.test_bundle.mkdir(parents=True)
        self.test_info = {'CFBundleIdentifier': gate.TEST_BUNDLE_ID,
                          'CFBundleExecutable': 'QRCatcherTests',
                          'CFBundlePackageType': 'BNDL',
                          'CFBundleSupportedPlatforms': ['iPhoneSimulator']}
        self.write_test_info()
        self.write_test_binary()
        self.test_target = {'BlueprintName': 'QRCatcherTests',
                            'TestHostPath': str(self.app) if absolute_paths else '__TESTROOT__/Debug-iphonesimulator/QRCatcher.app',
                            'TestBundlePath': str(self.test_bundle) if absolute_paths else '__TESTHOST__/PlugIns/QRCatcherTests.xctest',
                            'TestHostBundleIdentifier': gate.BUNDLE_ID,
                            'IsUITestBundle': False}
        targets = [self.test_target]
        if ui_target:
            ui_host = destination.parent / 'QRCatcherUITests-Runner.app'
            ui_bundle = ui_host / 'PlugIns/QRCatcherUITests.xctest'
            ui_bundle.mkdir(parents=True)
            # Outside the selected .app, so no exception applies to this sibling.
            (ui_bundle / 'QRCatcherUITests').write_bytes(b'outside selected package')
            targets.append({'BlueprintName': 'QRCatcherUITests', 'IsUITestBundle': True,
                            'TestHostPath': '__TESTROOT__/Debug-iphonesimulator/QRCatcherUITests-Runner.app',
                            'TestBundlePath': '__TESTHOST__/PlugIns/QRCatcherUITests.xctest',
                            'UITargetAppPath': '__TESTROOT__/Debug-iphonesimulator/QRCatcher.app'})
        self.run_info = {'__xctestrun_metadata__': {'FormatVersion': format_version}}
        if format_version == 1:
            self.run_info.update({target['BlueprintName']: target for target in targets})
        else:
            self.run_info['TestConfigurations'] = [{'Name': 'Default', 'IsEnabled': True,
                                                     'TestTargets': targets}]
        self.xctestrun = products / 'QRCatcher_iphonesimulator.xctestrun'
        self.write_xctestrun()
        return {'platform': 'simulator', 'configuration': 'Debug', 'xctestrun': self.xctestrun}

    def write_xctestrun(self):
        self.xctestrun.write_bytes(plistlib.dumps(self.run_info))

    def write_test_info(self):
        (self.test_bundle / 'Info.plist').write_bytes(plistlib.dumps(self.test_info))

    def write_test_binary(self, **changes):
        settings = {'platform': 7, 'filetype': 8, 'minimum': 17 << 16,
                    'markers': b'QRWatchPhoneService\0QRWatchSessionGate\0XCTestCase\0',
                    'extra': [dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity'),
                              dylib_command('/Developer/Library/Frameworks/XCTest.framework/XCTest'), uuid_command()]}
        settings.update(changes)
        (self.test_bundle / 'QRCatcherTests').write_bytes(macho(**settings))

    def symbols(self, data=None):
        folder = self.app / gate.TEST_SYMBOLS
        dwarf = self.app / gate.TEST_DWARF
        dwarf.parent.mkdir(parents=True, exist_ok=True)
        self.symbol_info = {'CFBundleDevelopmentRegion': 'English',
                            'CFBundleIdentifier': 'com.apple.xcode.dsym.' + gate.TEST_BUNDLE_ID,
                            'CFBundleInfoDictionaryVersion': '6.0', 'CFBundlePackageType': 'dSYM',
                            'CFBundleSignature': '????', 'CFBundleShortVersionString': '1.0',
                            'CFBundleVersion': '1'}
        self.write_symbol_info()
        dwarf.write_bytes(symbol_macho(markers=b'QRWatchPhoneService\0QRWatchSessionGate\0XCTestCase\0')
                          if data is None else data)
        return folder, dwarf

    def write_symbol_info(self):
        (self.app / gate.TEST_SYMBOLS / 'Contents/Info.plist').write_bytes(plistlib.dumps(self.symbol_info))

    def relocation_yaml(self, architecture='aarch64', records=(), triple=None, binary_path=None):
        """LLVM RelocationMap's public emitted shape, not observed native bytes."""
        triple = triple or architecture + '-apple-ios17.0.0-simulator'
        binary_path = binary_path or str(self.test_bundle / 'QRCatcherTests')
        lines = ['---', 'triple:          ' + repr(triple),
                 'binary-path:     ' + json.dumps(binary_path),
                 'relocations:' + ('' if records else '    []')]
        lines.extend('  - ' + record for record in records)
        return ('\n'.join(lines + ['...']) + '\n').encode('utf-8')

    def relocations(self, architecture='aarch64', data=None):
        path = self.app / gate.TEST_RELOCATIONS / architecture / 'QRCatcherTests.yml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.relocation_yaml(architecture) if data is None else data)
        return path

    def test_owned_temporary_alias_is_resolved_without_admitting_bound_path_aliases(self):
        alias = self.base / 'temporary-alias'
        alias.symlink_to(self.base, target_is_directory=True)
        with patch.object(tempfile, 'tempdir', str(alias)), patch.dict(os.environ, TMPDIR=str(alias)):
            ambiguous = alias / 'owned__empty'
            ambiguous.mkdir()
            normalized = normalize_owned_temporary_leaf(ambiguous)
            self.assertFalse(ambiguous.exists())
            self.assertEqual(normalized.parent, alias)
            self.assertTrue(normalized.is_dir())
            self.assertNotIn('__', normalized.name)
            normalized.rmdir()
            fixture = IOSOnlyPackageTests()
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
            raw_base = Path(fixture.temp.name)
            self.assertNotIn('__', raw_base.name)
            self.assertNotEqual(raw_base, fixture.base)
            self.assertEqual(raw_base.parent, alias)
            self.assertEqual(raw_base.resolve(strict=True), fixture.base)
            options = fixture.hosted(format_version=2, absolute_paths=True)
            aliased_run = raw_base / fixture.xctestrun.relative_to(fixture.base)
            self.assertEqual(aliased_run.resolve(strict=True), fixture.xctestrun)
            ambiguous_root = fixture.base / 'case__name'
            shutil.copytree(fixture.base / 'Build', ambiguous_root / 'Build')
            ambiguous_app = ambiguous_root / fixture.app.relative_to(fixture.base)
            ambiguous_run = ambiguous_root / fixture.xctestrun.relative_to(fixture.base)
            ambiguous_info = plistlib.loads(ambiguous_run.read_bytes())
            ambiguous_target = ambiguous_info['TestConfigurations'][0]['TestTargets'][0]
            ambiguous_target.update(TestHostPath='__TESTROOT__/Debug-iphonesimulator/QRCatcher.app',
                                    TestBundlePath='__TESTHOST__/PlugIns/QRCatcherTests.xctest')
            ambiguous_run.write_bytes(plistlib.dumps(ambiguous_info))
            for optimized in (False, True):
                with self.subTest(optimized=optimized), patch.dict(os.environ, PYTHONOPTIMIZE='1' if optimized else '0'):
                    arguments = ('--platform', 'simulator', '--configuration', 'Debug', '--xctestrun')
                    result, report = fixture.cli(*arguments, str(fixture.xctestrun), optimized=optimized)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(report['hosted_tests']['xctestrun']['binding']['host'], str(fixture.app))
                    result, report = fixture.cli(*arguments, str(aliased_run), optimized=optimized)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(report['reason'], 'xctestrun_root')
                    for field, concrete in (('TestHostPath', fixture.app), ('TestBundlePath', fixture.test_bundle)):
                        with self.subTest(field=field):
                            aliased = raw_base / concrete.relative_to(fixture.base)
                            self.assertEqual(aliased.resolve(strict=True), concrete)
                            fixture.test_target[field] = str(aliased)
                            fixture.write_xctestrun()
                            result, report = fixture.cli(*arguments, str(fixture.xctestrun), optimized=optimized)
                            self.assertEqual(result.returncode, 1)
                            self.assertEqual(report['reason'], 'xctestrun_path')
                            fixture.test_target[field] = str(concrete)
                            fixture.write_xctestrun()
                    concrete_app = fixture.app
                    try:
                        fixture.app = ambiguous_app
                        result, report = fixture.cli(*arguments, str(ambiguous_run), optimized=optimized)
                    finally:
                        fixture.app = concrete_app
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(report['reason'], 'xctestrun_path')
                    self.assertIn('unexpanded', report['detail'])

    def test_exact_hosted_debug_binding_reports_test_only_evidence_in_both_formats(self):
        options = self.hosted(ui_target=True)
        for format_version in (1, 2):
            for absolute_paths in (False, True):
                with self.subTest(format_version=format_version, absolute_paths=absolute_paths):
                    targets = [self.test_target, self.run_info['QRCatcherUITests']]
                    if absolute_paths:
                        self.test_target['TestHostPath'] = str(self.app)
                        self.test_target['TestBundlePath'] = str(self.test_bundle)
                    else:
                        self.test_target['TestHostPath'] = '__TESTROOT__/Debug-iphonesimulator/QRCatcher.app'
                        self.test_target['TestBundlePath'] = '__TESTHOST__/PlugIns/QRCatcherTests.xctest'
                    info = {'__xctestrun_metadata__': {'FormatVersion': format_version}}
                    if format_version == 1:
                        info.update({target['BlueprintName']: target for target in targets})
                    else:
                        info['TestConfigurations'] = [{'Name': 'Default', 'IsEnabled': True, 'TestTargets': targets}]
                    self.xctestrun.write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
                    report = gate.verify_package(self.app, **options)
                    self.assertEqual(report['scope'], 'ios-only-debug-hosted-test-package')
                    self.assertEqual([image['path'] for image in report['mach_o']], ['QRCatcher'])
                    tests = report['hosted_tests']
                    self.assertEqual(tests['bundle_id'], gate.TEST_BUNDLE_ID)
                    self.assertEqual(tests['executable'], 'QRCatcherTests')
                    self.assertEqual(tests['xctestrun']['binding']['host'], str(self.app))
                    self.assertEqual(tests['xctestrun']['binding']['bundle'], str(self.test_bundle))
                    self.assertEqual(tests['xctestrun']['format_version'], format_version)
                    self.assertEqual([image['path'] for image in tests['mach_o']], [gate.TEST_BUNDLE + '/QRCatcherTests'])
                    self.assertEqual(tests['inventory']['files'], 2)
                    self.assertGreaterEqual({item['marker'] for item in tests['permitted_test_only_markers']},
                                            {'QRWatchPhoneService', 'QRWatchSessionGate', 'WatchConnectivity', 'XCTestCase', 'XCTest.framework'})

    def test_hosted_bundle_without_actual_binding_remains_rejected(self):
        options = self.hosted()
        del options['xctestrun']
        self.rejected('release_test_bundle', **options)
        with self.assertRaises(gate.ValidationError) as raised:
            gate.verify_package(self.app, **dict(options, xctestrun=self.xctestrun.with_name('missing.xctestrun')))
        self.assertEqual(raised.exception.code, 'inspection_error')
        self.assertIs(raised.exception.package_diagnostics['safe_inventory_complete'], False)
        self.xctestrun.write_bytes(b'<plist><dict>')
        self.rejected('malformed_plist', **dict(options, xctestrun=self.xctestrun))

    def test_hosted_binding_requires_exact_host_bundle_owner_and_enabled_unit_target(self):
        options = self.hosted()
        other = self.app.parent / 'Other.app'
        other.mkdir()
        other_bundle = self.app.parent / 'Other.xctest'
        other_bundle.mkdir()
        original = dict(self.test_target)
        defects = [('TestHostPath', str(other)), ('TestBundlePath', str(other_bundle)),
                   ('TestHostBundleIdentifier', 'example.Other'), ('IsUITestBundle', True),
                   ('UseDestinationArtifacts', True), ('TestHostPath', None), ('TestBundlePath', None)]
        for key, value in defects:
            with self.subTest(key=key, value=value):
                self.test_target.clear()
                self.test_target.update(original)
                if value is None:
                    self.test_target.pop(key)
                else:
                    self.test_target[key] = value
                self.write_xctestrun()
                self.rejected(**options)

    def test_missing_foreign_and_duplicate_xctestrun_bindings_fail_closed(self):
        options = self.hosted(format_version=2)
        configuration = self.run_info['TestConfigurations'][0]
        for targets, enabled in (([dict(self.test_target, BlueprintName='OtherTests')], True),
                                 ([self.test_target, dict(self.test_target)], True),
                                 ([self.test_target, dict(self.test_target, BlueprintName='OtherTests')], True),
                                 ([self.test_target], False)):
            with self.subTest(targets=[target['BlueprintName'] for target in targets], enabled=enabled):
                configuration['TestTargets'] = targets
                configuration['IsEnabled'] = enabled
                self.write_xctestrun()
                self.rejected(**options)
        configuration.update(IsEnabled=True, TestTargets=[self.test_target])
        self.run_info['TestConfigurations'].append({'Name': 'Second', 'IsEnabled': True,
                                                   'TestTargets': [dict(self.test_target)]})
        self.write_xctestrun()
        self.rejected('duplicate_test_binding', **options)

    def test_xctestrun_foreign_root_traversal_placeholder_and_symlink_paths_rejected(self):
        options = self.hosted()
        wrong_root = self.base / self.xctestrun.name
        wrong_root.write_bytes(self.xctestrun.read_bytes())
        self.rejected('xctestrun_root', **dict(options, xctestrun=wrong_root))
        symbolic_run = self.xctestrun.with_name('symbolic.xctestrun')
        symbolic_run.symlink_to(self.xctestrun)
        self.rejected('xctestrun_path', **dict(options, xctestrun=symbolic_run))
        original = dict(self.test_target)
        for path in ('../QRCatcher.app', '__TESTROOT__/../Debug-iphonesimulator/QRCatcher.app',
                     '__UNKNOWN__/QRCatcher.app', '__TESTHOST__/QRCatcher.app', str(self.base),
                     '__TESTROOT__/Debug-iphonesimulator/./QRCatcher.app'):
            with self.subTest(path=path):
                self.test_target['TestHostPath'] = path
                self.write_xctestrun()
                self.rejected('xctestrun_path', **options)
        self.test_target.clear()
        self.test_target.update(original)
        alias = self.app.parent / 'Alias.app'
        alias.symlink_to(self.app, target_is_directory=True)
        self.test_target['TestHostPath'] = str(alias)
        self.write_xctestrun()
        self.rejected('xctestrun_symlink', **options)
        self.test_target.update(original)
        saved = self.test_bundle.with_name('saved-test-bundle')
        self.test_bundle.rename(saved)
        self.test_bundle.symlink_to(saved, target_is_directory=True)
        self.write_xctestrun()
        self.rejected('xctestrun_symlink', **options)

    def test_hosted_executable_bundle_identity_and_required_helper_ownership_are_exact(self):
        options = self.hosted()
        original = dict(self.test_info)
        for key, value in (('CFBundleIdentifier', 'example.Other'), ('CFBundlePackageType', 'APPL'),
                           ('CFBundleExecutable', 'OtherTests'), ('CFBundleExecutable', '../QRCatcherTests')):
            with self.subTest(key=key, value=value):
                self.test_info = dict(original, **{key: value})
                self.write_test_info()
                self.rejected(**options)
        self.test_info = original
        self.write_test_info()
        executable = self.test_bundle / 'QRCatcherTests'
        executable.unlink()
        self.rejected('missing_test_executable', **options)
        for markers in (b'QRWatchPhoneService\0', b'QRWatchSessionGate\0', b'XCTestCase\0'):
            self.write_test_binary(markers=markers)
            self.rejected('missing_test_helpers', **options)
        self.write_test_binary(extra=[])
        self.rejected('missing_test_watch_dependency', **options)
        self.write_test_binary(filetype=2)
        self.rejected('mach_o_file_type', **options)
        self.write_test_binary(platform=4)
        self.rejected('mach_o_platform', **options)

    def test_hosted_exception_does_not_admit_arbitrary_plugins_or_nested_tests(self):
        options = self.hosted()
        for relative in ('PlugIns/Other.xctest', 'PlugIns/nested/QRCatcherTests.xctest',
                         gate.TEST_BUNDLE + '/Other.xctest', gate.TEST_BUNDLE + '/Other.appex',
                         gate.TEST_BUNDLE + '/Other.app'):
            with self.subTest(relative=relative):
                directory = self.app / relative
                directory.mkdir(parents=True)
                self.rejected(**options)
                shutil.rmtree(directory)

    def test_shipping_app_and_every_shipping_image_remain_watch_strict_with_binding(self):
        options = self.hosted()
        framework = self.framework(data=macho(platform=7, filetype=6))
        for relative in ('QRCatcher', 'QRCatcher.debug.dylib', '__preview.dylib', 'Frameworks/Ordinary.framework/Ordinary'):
            with self.subTest(relative=relative):
                destination = self.app / relative
                existing = destination.read_bytes() if destination.exists() else None
                destination.write_bytes(macho(platform=7, filetype=2 if relative == 'QRCatcher' else 6,
                                               markers=b'QRWatchSessionGate\0'))
                self.rejected('watch_presence', **options)
                if existing is None:
                    destination.unlink()
                else:
                    destination.write_bytes(existing)
        (framework / 'Ordinary').write_bytes(macho(platform=7, filetype=6,
                                                  extra=[dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity')]))
        self.rejected('watch_presence', **options)

    def test_shipping_cannot_link_bound_test_bundle_or_hide_helper_in_resource(self):
        options = self.hosted()
        self.write_binary(macho(platform=7, extra=[dylib_command('@rpath/QRCatcherTests.xctest/QRCatcherTests')]))
        self.rejected('shipping_test_dependency', **options)
        self.write_binary(macho(platform=7))
        (self.app / 'ordinary-resource').write_bytes(b'QRWatchPhoneService')
        self.rejected('watch_presence', **options)

    def test_bound_test_subtree_still_obeys_type_symlink_and_code_inventory_checks(self):
        options = self.hosted()
        hidden = self.test_bundle / 'hidden-code'
        hidden.write_bytes(macho(platform=7, filetype=6))
        self.rejected('orphan_mach_o', **options)
        hidden.unlink()
        outside = self.base / 'outside-test-resource'
        outside.write_bytes(b'ordinary')
        hidden.symlink_to(outside)
        self.rejected('symlink', **options)
        hidden.unlink()
        hidden.write_bytes(b'not Mach-O')
        hidden.rename(hidden.with_suffix('.dylib'))
        self.rejected('unsupported_shipping_code', **options)

    def test_hosted_exception_never_applies_to_release_device_or_archive_scope(self):
        options = self.hosted()
        self.rejected('xctestrun_scope', **dict(options, configuration='Release'))
        self.rejected('xctestrun_scope', **dict(options, platform='device'))
        archive = self.archive()
        with self.assertRaises(gate.ValidationError) as raised:
            gate.verify_package(archive, **options)
        self.assertEqual(raised.exception.code, 'archive_scope')

    def test_release_rejects_xctest_bundle_framework_and_class_without_any_exception(self):
        archive = self.archive()
        for marker in (b'XCTest.framework', b'XCTestCase', b'XCTestObservation'):
            for package in (self.app, archive):
                with self.subTest(marker=marker, package=package.suffix):
                    self.write_binary(macho(markers=marker))
                    with self.assertRaises(gate.ValidationError) as raised:
                        gate.verify_package(package)
                    self.assertEqual(raised.exception.code, 'release_diagnostics')

    def test_shipping_xctest_inventory_names_rejected_without_any_literal_binary_marker(self):
        framework = self.framework(name='XCTest', data=macho(filetype=6))
        self.rejected('shipping_test_inventory')
        shutil.rmtree(framework)
        self.simulator()
        self.debug()
        for name in ('XCTest.framework', 'libXCTest.dylib', 'XCTestCore.framework', 'xCtEsT-support'):
            with self.subTest(name=name):
                entry = self.app / 'Frameworks' / name
                entry.parent.mkdir(exist_ok=True)
                entry.mkdir()
                self.rejected('shipping_test_inventory', platform='simulator', configuration='Debug')
                entry.rmdir()

    def test_bound_test_framework_inventory_is_permitted_only_inside_the_exact_test_subtree(self):
        options = self.hosted()
        framework = self.test_bundle / 'Frameworks/XCTest.framework'
        framework.mkdir(parents=True)
        (framework / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'com.apple.dt.XCTest', 'CFBundleExecutable': 'XCTest',
            'CFBundlePackageType': 'FMWK', 'CFBundleSupportedPlatforms': ['iPhoneSimulator']}))
        (framework / 'XCTest').write_bytes(macho(platform=7, filetype=6, minimum=17 << 16,
                                                markers=b'XCTestCase\0'))
        report = gate.verify_package(self.app, **options)
        self.assertEqual(len(report['hosted_tests']['mach_o']), 2)
        self.assertEqual(len(report['mach_o']), 1)
        shipping_framework = self.app / 'Frameworks/XCTest.framework'
        shipping_framework.parent.mkdir()
        shutil.copytree(framework, shipping_framework)
        self.rejected('shipping_test_inventory', **options)

    def test_archives_require_release_device_even_when_debug_binaries_look_valid(self):
        self.debug()
        self.write_binary(macho(markers=b'XCTest.framework\0XCTestCase\0'))
        archive = self.archive()
        for platform, configuration in (('device', 'Debug'), ('simulator', 'Debug'), ('simulator', 'Release')):
            with self.subTest(platform=platform, configuration=configuration):
                with self.assertRaises(gate.ValidationError) as raised:
                    gate.verify_package(archive, platform=platform, configuration=configuration)
                self.assertEqual(raised.exception.code, 'archive_scope')

    def test_hosted_cli_success_and_wrong_host_rejection_remain_active_under_optimization(self):
        options = self.hosted()
        arguments = ('--platform', 'simulator', '--configuration', 'Debug', '--xctestrun', str(options['xctestrun']))
        for optimized in (False, True):
            result, report = self.cli(*arguments, optimized=optimized)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(report['hosted_tests']['bundle_id'], gate.TEST_BUNDLE_ID)
        self.test_target['TestHostBundleIdentifier'] = 'example.WrongHost'
        self.write_xctestrun()
        for optimized in (False, True):
            result, report = self.cli(*arguments, optimized=optimized)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['reason'], 'test_host_binding')

    def test_bound_symbols_are_separate_from_runtime_images_and_use_public_metadata(self):
        options = self.hosted(format_version=2)
        self.symbols()
        for identifier in ('com.apple.xcode.dsym.' + gate.TEST_BUNDLE_ID,
                           'com.apple.xcode.dsym.QRCatcherTests.xctest'):
            self.symbol_info['CFBundleIdentifier'] = identifier
            self.write_symbol_info()
            with patch('subprocess.run', side_effect=AssertionError('no native symbol tools')):
                report = gate.verify_package(self.app, **options)
            self.assertEqual([entry['path'] for entry in report['mach_o']], ['QRCatcher'])
            self.assertEqual([entry['path'] for entry in report['hosted_tests']['mach_o']],
                             [gate.TEST_BUNDLE + '/QRCatcherTests'])
            symbols = report['hosted_tests']['symbols']
            self.assertEqual(symbols['classification'], 'test-symbols')
            self.assertEqual(symbols['bound_executable'], gate.TEST_BUNDLE + '/QRCatcherTests')
            self.assertEqual(symbols['dwarf']['path'], gate.TEST_DWARF)
            self.assertEqual(symbols['dwarf']['slices'][0]['uuid'], TEST_UUID.hex())
            self.assertEqual(symbols['dwarf']['slices'][0]['file_type'], 0xA)
            self.assertEqual(symbols['metadata']['CFBundleIdentifier'], identifier)
        dwarf = self.app / gate.TEST_DWARF
        dwarf.write_bytes(symbol_macho(platform=None))
        self.assertIsNone(gate.verify_package(self.app, **options)['hosted_tests']['symbols']['dwarf']['slices'][0]['platform'])

    def test_dsymutil_zero_flags_and_debug_attribute_keep_exact_bound_symbol_scope(self):
        options = self.hosted(format_version=2)
        for cpu in (ARM64, X86_64):
            for endian in ('<', '>'):
                self.write_test_binary(cpu=cpu, endian=endian, extra=[
                    dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity', endian=endian),
                    dylib_command('/Developer/Library/Frameworks/XCTest.framework/XCTest', endian=endian),
                    uuid_command(TEST_UUID, endian)])
                for flags in (0, 0x02000000):
                    with self.subTest(cpu=cpu, endian=endian, flags=flags):
                        self.symbols(symbol_macho(cpu=cpu, endian=endian, debug_flags=flags))
                        with patch('subprocess.run', side_effect=AssertionError('no native symbol tools')):
                            report = gate.verify_package(self.app, **options)
                        symbols = report['hosted_tests']['symbols']
                        self.assertEqual(symbols['classification'], 'test-symbols')
                        self.assertEqual(symbols['dwarf']['slices'][0]['uuid'], TEST_UUID.hex())
                        self.assertEqual(symbols['dwarf']['slices'][0]['file_type'], 0xA)
                        self.assertEqual([row['path'] for row in report['mach_o']], ['QRCatcher'])

    def test_zero_flags_do_not_admit_nonregular_types_instructions_relocations_or_ranges(self):
        options = self.hosted()
        _, dwarf = self.symbols(symbol_macho(debug_flags=0))
        good = dwarf.read_bytes()
        cases = [(symbol_macho(debug_flags=flags), 'test_symbol_debug_section')
                 for flags in (1, 2, 0xC, 0x12, 0x02000001, 0x80000400)]
        cases.extend([(symbol_macho(debug_flags=0x82000400), 'test_symbol_runtime_code'),
                      (edit_dwarf_section(good, 60, 'I', 1), 'test_symbol_runtime_code'),
                      (edit_dwarf_section(good, 56, 'I', len(good) + 1), 'mach_o_range'),
                      (edit_dwarf_section(good, 48, 'I', len(good) + 1), 'mach_o_range'),
                      (edit_dwarf_section(good, 40, 'Q', len(good) + 1), 'mach_o_range'),
                      (edit_dwarf_section(good, 0, '16s', b'__other'.ljust(16, b'\0')),
                       'missing_test_symbol_debug_info')])
        for data, reason in cases:
            with self.subTest(reason=reason):
                dwarf.write_bytes(data)
                self.rejected(reason, **options)

    def test_zero_flags_keep_filetype_cpu_uuid_binding_and_release_rejections(self):
        options = self.hosted()
        _, dwarf = self.symbols(symbol_macho(debug_flags=0))
        for data, reason in ((symbol_macho(debug_flags=0, filetype=8), 'test_symbol_file_type'),
                             (symbol_macho(debug_flags=0, cpu=X86_64), 'test_symbol_architecture'),
                             (symbol_macho(debug_flags=0, subtype=1), 'test_symbol_architecture'),
                             (symbol_macho(debug_flags=0, uuid=bytes(range(17, 33))), 'test_symbol_uuid')):
            with self.subTest(reason=reason):
                dwarf.write_bytes(data)
                self.rejected(reason, **options)
        dwarf.write_bytes(symbol_macho(debug_flags=0))
        self.rejected('release_test_bundle', platform='simulator', configuration='Debug')
        self.rejected('xctestrun_scope', platform='simulator', configuration='Release', xctestrun=options['xctestrun'])
        self.test_target['TestHostBundleIdentifier'] = 'example.foreign'
        self.write_xctestrun()
        self.rejected('test_host_binding', **options)
        archive = self.archive()
        with self.assertRaises(gate.ValidationError):
            gate.verify_package(archive)

    def test_zero_flag_debug_header_failure_retention_is_bounded_and_contains_no_dwarf_content(self):
        options = self.hosted()
        _, dwarf = self.symbols(symbol_macho(debug_flags=0, uuid=bytes(range(17, 33)),
                                           markers=b'private DWARF content sentinel'))
        with patch.object(gate, 'read_regular', wraps=gate.read_regular) as reader:
            error = self.rejected('test_symbol_uuid', **options)
        observed = error.symbol_observations['mach_o'][0]['slices'][0]
        self.assertEqual(observed['debug_section_headers_observed'], 1)
        self.assertEqual(observed['debug_sections'][0]['segment'], '__DWARF')
        self.assertEqual(observed['debug_sections'][0]['section'], '__debug_info')
        self.assertEqual(observed['debug_sections'][0]['flags'], 0)
        self.assertEqual(observed['debug_sections'][0]['type'], 0)
        self.assertEqual(observed['debug_sections'][0]['relocations'], 0)
        self.assertNotIn('debug_section_headers_omitted', observed)
        encoded = gate.encode_report({'schema_version': 1, 'status': 'fail', 'reason': error.code,
                                      'test_symbol_observations': error.symbol_observations})
        self.assertNotIn(b'private DWARF content sentinel', encoded)
        self.assertLessEqual(len(encoded), gate.DEFAULT_LIMITS.report_bytes)
        self.assertEqual(sum(call.args[3] == gate.TEST_DWARF for call in reader.call_args_list), 1)
        dwarf.write_bytes(symbol_macho(debug_flags=2))
        error = self.rejected('test_symbol_debug_section', **options)
        observed = error.symbol_observations['mach_o'][0]['slices'][0]
        self.assertEqual(observed['debug_sections'][0]['flags'], 2)
        self.assertEqual(observed['debug_sections'][0]['type'], 2)
        self.assertEqual(error.symbol_observations['qualification'], 'unqualified')

    def test_debug_header_retention_caps_sixteen_without_waiving_later_section_validation(self):
        options = self.hosted()
        _, dwarf = self.symbols(symbol_macho(debug_flags=0, debug_sections=17, uuid=bytes(range(17, 33))))
        error = self.rejected('test_symbol_uuid', **options)
        observed = error.symbol_observations['mach_o'][0]['slices'][0]
        self.assertEqual(observed['debug_section_headers_observed'], 17)
        self.assertEqual(observed['debug_section_headers_omitted'], 1)
        self.assertEqual(len(observed['debug_sections']), 16)
        bad = bytearray(symbol_macho(debug_flags=0, debug_sections=17))
        offset = 32 + 24 + 24 + 152 + 72 + 16 * 80 + 64
        struct.pack_into('<I', bad, offset, 2)
        dwarf.write_bytes(bad)
        error = self.rejected('test_symbol_debug_section', **options)
        self.assertEqual(error.symbol_observations['mach_o'][0]['slices'][0]['debug_section_headers_omitted'], 1)
        dwarf.write_bytes(symbol_macho(debug_flags=0))
        report = gate.verify_package(self.app, **options)
        self.assertEqual(report['limits'], asdict(gate.DEFAULT_LIMITS))

    def test_zero_flag_cli_success_and_header_failure_remain_active_under_optimization(self):
        options = self.hosted()
        _, dwarf = self.symbols(symbol_macho(debug_flags=0))
        arguments = ('--platform', 'simulator', '--configuration', 'Debug', '--xctestrun', str(options['xctestrun']))
        for optimized in (False, True):
            dwarf.write_bytes(symbol_macho(debug_flags=0))
            result, report = self.cli(*arguments, optimized=optimized)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(report['hosted_tests']['symbols']['classification'], 'test-symbols')
            dwarf.write_bytes(symbol_macho(debug_flags=2, markers=b'private content sentinel'))
            result, report = self.cli(*arguments, optimized=optimized)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['reason'], 'test_symbol_debug_section')
            self.assertEqual(report['test_symbol_observations']['mach_o'][0]['slices'][0]['debug_sections'][0]['flags'], 2)
            self.assertNotIn('private content sentinel', json.dumps(report))

    def test_symbols_match_every_fat_slice_by_architecture_not_position(self):
        options = self.hosted()
        second_uuid = bytes(range(17, 33))
        arm = (self.test_bundle / 'QRCatcherTests').read_bytes()
        self.write_test_binary(cpu=X86_64, endian='>', extra=[
            dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity', endian='>'),
            uuid_command(second_uuid, '>')])
        intel = (self.test_bundle / 'QRCatcherTests').read_bytes()
        for wide in (False, True):
            for endian in ('<', '>'):
                with self.subTest(wide=wide, endian=endian):
                    (self.test_bundle / 'QRCatcherTests').write_bytes(fat([arm, intel], wide, endian))
                    self.symbols(fat([symbol_macho(cpu=X86_64, endian='>', uuid=second_uuid),
                                      symbol_macho()], wide, endian))
                    report = gate.verify_package(self.app, **options)
                    self.assertEqual(len(report['hosted_tests']['symbols']['dwarf']['slices']), 2)
                    (self.app / gate.TEST_DWARF).write_bytes(fat([symbol_macho(cpu=X86_64, uuid=TEST_UUID),
                                                              symbol_macho()], wide, endian))
                    self.rejected('test_symbol_uuid', **options)

    def test_symbol_uuid_missing_duplicate_zero_malformed_or_foreign_is_rejected(self):
        options = self.hosted()
        _, dwarf = self.symbols()
        good_binary = (self.test_bundle / 'QRCatcherTests').read_bytes()
        cases = ((symbol_macho(uuid=bytes(range(17, 33))), 'test_symbol_uuid'),
                 (symbol_macho(uuid=None), 'missing_uuid_command'),
                 (symbol_macho(extra=[uuid_command()]), 'duplicate_uuid_command'),
                 (symbol_macho(uuid=b'\0' * 16), 'invalid_uuid'),
                 (edit_command(symbol_macho(), 0x1B, 4, 'I', 16), 'malformed_uuid_command'))
        for data, reason in cases:
            with self.subTest(reason=reason):
                dwarf.write_bytes(data)
                self.rejected(reason, **options)
        dwarf.write_bytes(symbol_macho())
        watch_link = dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity')
        for extra, reason in (([watch_link], 'missing_uuid_command'),
                              ([watch_link, uuid_command(), uuid_command()], 'duplicate_uuid_command')):
            self.write_test_binary(extra=extra)
            self.rejected(reason, **options)
        (self.test_bundle / 'QRCatcherTests').write_bytes(good_binary)

    def test_symbols_reject_missing_duplicate_foreign_or_subtype_architectures(self):
        options = self.hosted()
        _, dwarf = self.symbols()
        for data, reason in ((symbol_macho(cpu=X86_64), 'test_symbol_architecture'),
                             (symbol_macho(subtype=1), 'test_symbol_architecture'),
                             (fat([symbol_macho(), symbol_macho(cpu=X86_64)]), 'test_symbol_architecture'),
                             (fat([symbol_macho(), symbol_macho()]), 'duplicate_fat_slice')):
            with self.subTest(reason=reason):
                dwarf.write_bytes(data)
                self.rejected(reason, **options)
        first = (self.test_bundle / 'QRCatcherTests').read_bytes()
        self.write_test_binary(cpu=X86_64)
        second = (self.test_bundle / 'QRCatcherTests').read_bytes()
        (self.test_bundle / 'QRCatcherTests').write_bytes(fat([first, second]))
        dwarf.write_bytes(symbol_macho())
        self.rejected('test_symbol_architecture', **options)

    def test_symbols_require_exact_sibling_and_unique_dwarf_file(self):
        options = self.hosted()
        folder, dwarf = self.symbols()
        for destination in (self.app / 'QRCatcherTests.xctest.dSYM',
                            self.test_bundle / 'QRCatcherTests.xctest.dSYM',
                            self.app / 'PlugIns/nested/QRCatcherTests.xctest.dSYM',
                            self.app / 'PlugIns/Other.xctest.dSYM'):
            with self.subTest(destination=destination.relative_to(self.app)):
                destination.parent.mkdir(parents=True, exist_ok=True)
                folder.rename(destination)
                self.rejected(**options)
                destination.rename(folder)
        original = dwarf.read_bytes()
        dwarf.unlink()
        self.rejected('missing_test_symbols', **options)
        dwarf.write_bytes(original)
        duplicate = dwarf.with_name('Other')
        duplicate.write_bytes(original)
        self.rejected('test_symbol_inventory', **options)
        duplicate.unlink()
        dwarf.rename(duplicate)
        self.rejected('test_symbol_inventory', **options)

    def test_symbol_metadata_cannot_declare_foreign_or_executable_bundle(self):
        options = self.hosted()
        folder, _ = self.symbols()
        original = dict(self.symbol_info)
        for key, value in (('CFBundleIdentifier', 'com.apple.xcode.dsym.Foreign'),
                           ('CFBundleIdentifier', []),
                           ('CFBundlePackageType', 'BNDL'), ('CFBundleInfoDictionaryVersion', '5.0'),
                           ('CFBundleExecutable', 'QRCatcherTests'), ('CFBundleVersion', 1),
                           ('CFBundleSignature', 'OTHER'), ('CFBundleDevelopmentRegion', 'unknown'),
                           ('Toolchain', []), ('CFBundleShortVersionString', '')):
            with self.subTest(key=key):
                self.symbol_info = dict(original, **{key: value})
                self.write_symbol_info()
                error = self.rejected('test_symbol_metadata', **options)
                if key == 'CFBundleExecutable':
                    self.assertIn('CFBundleExecutable:str', error.detail)
        self.symbol_info = original
        self.write_symbol_info()
        metadata = folder / 'Contents/Info.plist'
        metadata.write_bytes(b'<plist><dict>')
        self.rejected('malformed_plist', **options)
        metadata.unlink()
        self.rejected('missing_test_symbols', **options)

    def test_symbols_reject_symlinks_special_files_runtime_types_and_extra_code(self):
        options = self.hosted()
        folder, dwarf = self.symbols()
        original = dwarf.read_bytes()
        for path in (folder, folder / 'Contents', folder / 'Contents/Info.plist', dwarf):
            with self.subTest(path=path.relative_to(self.app)):
                saved = self.base / 'saved-symbol-entry'
                path.rename(saved)
                path.symlink_to(saved, target_is_directory=saved.is_dir())
                self.rejected('symlink', **options)
                path.unlink()
                saved.rename(path)
        dwarf.unlink()
        os.mkfifo(dwarf)
        self.rejected('unsupported_file_type', **options)
        dwarf.unlink()
        for data, reason in ((macho(platform=7, filetype=8), 'test_symbol_file_type'),
                             (symbol_macho(filetype=2), 'test_symbol_file_type'),
                             (symbol_macho(extra=[dylib_command('@rpath/Extra.dylib')]), 'test_symbol_load_command'),
                             (symbol_macho(extra=[struct.pack('<IIQQ', 0x80000028, 24, 4096, 0)]), 'test_symbol_load_command'),
                             (symbol_macho(platform=4), 'mach_o_platform'),
                             (edit_command(symbol_macho(), 0x19, 40, 'Q', 32), 'test_symbol_runtime_code'),
                             (edit_command(symbol_macho(), 0x19, 120, 'I', 32), 'test_symbol_runtime_code')):
            with self.subTest(reason=reason):
                dwarf.write_bytes(data)
                self.rejected(reason, **options)
        dwarf.write_bytes(original)
        extra = folder / 'Contents/Resources/extra-code'
        extra.write_bytes(macho(platform=7, filetype=6))
        self.rejected('test_symbol_inventory', **options)

    def test_symbol_unknown_metadata_and_load_command_details_are_bounded_non_source_summaries(self):
        options = self.hosted()
        _, dwarf = self.symbols()
        self.symbol_info['NewMetadata'] = {'payload': 'private metadata sentinel'}
        self.write_symbol_info()
        error = self.rejected('test_symbol_metadata', **options)
        self.assertIn('NewMetadata:dict', error.detail)
        self.assertNotIn('private metadata sentinel', json.dumps(error.symbol_observations))
        self.assertNotIn('private metadata sentinel', error.detail)
        del self.symbol_info['NewMetadata']
        self.write_symbol_info()
        dwarf.write_bytes(symbol_macho(extra=[struct.pack('<2I', 0x7FFFFFFE, 8)]))
        error = self.rejected('test_symbol_load_command', **options)
        self.assertIn('0x7ffffffe', error.detail)
        self.assertLessEqual(len(error.detail), 400)

    def test_symbol_exception_never_weakens_shipping_helpers_or_test_frameworks(self):
        options = self.hosted()
        self.symbols()
        for markers, reason in ((b'QRWatchPhoneService', 'watch_presence'),
                                (b'QRWatchSessionGate', 'watch_presence')):
            self.write_binary(macho(platform=7, markers=markers))
            self.rejected(reason, **options)
        self.write_binary(macho(platform=7))
        self.framework(name='XCTest', data=macho(platform=7, filetype=6))
        self.rejected('shipping_test_inventory', **options)

    def test_bound_symbols_keep_shipping_xctest_bytes_and_links_strict_in_debug(self):
        options = self.hosted()
        self.symbols()
        framework = self.framework(data=macho(platform=7, filetype=6))
        self.write_binary(macho(platform=7, markers=b'-ui-testing\0-fixture-payload\0QRStartupObservation\0'))
        debug_dylib = self.app / 'QRCatcher.debug.dylib'
        debug_dylib.write_bytes(macho(platform=7, filetype=6, markers=b'-mini-startup-fixture\0'))
        self.assertEqual(gate.verify_package(self.app, **options)['status'], 'pass')
        for location in (self.app / 'QRCatcher', debug_dylib, framework / 'Ordinary'):
            filetype = 2 if location.name == 'QRCatcher' else 6
            original = location.read_bytes()
            for marker in ('XCTestCase', 'XCTestObservation'):
                for encoding in ('ascii', 'utf-16-le', 'utf-16-be'):
                    with self.subTest(location=location.name, marker=marker, encoding=encoding):
                        location.write_bytes(macho(platform=7, filetype=filetype, markers=marker.encode(encoding)))
                        if marker == 'XCTestCase' and location.name in gate.DEBUG_DETECTION_IMAGES:
                            self.assertEqual(gate.verify_package(self.app, **options)['status'], 'pass')
                        else:
                            self.rejected('release_diagnostics', **options)
            location.write_bytes(macho(platform=7, filetype=filetype, extra=[
                dylib_command('/Developer/Library/Frameworks/XCTest.framework/XCTest')]))
            self.rejected('release_diagnostics', **options)
            location.write_bytes(macho(platform=7, filetype=filetype, extra=[
                dylib_command('/Developer/Library/Frameworks/xCtEsT.framework/xCtEsT')]))
            self.rejected('shipping_test_dependency', **options)
            location.write_bytes(original)
        self.assertEqual(gate.verify_package(self.app, **options)['status'], 'pass')

    def test_symbol_cli_positive_and_uuid_failure_keep_gates_under_optimization(self):
        options = self.hosted()
        _, dwarf = self.symbols()
        arguments = ('--platform', 'simulator', '--configuration', 'Debug', '--xctestrun', str(options['xctestrun']))
        for optimized in (False, True):
            with self.subTest(optimized=optimized):
                dwarf.write_bytes(symbol_macho())
                result, report = self.cli(*arguments, optimized=optimized)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(report['hosted_tests']['symbols']['classification'], 'test-symbols')
                dwarf.write_bytes(symbol_macho(uuid=bytes(range(17, 33))))
                result, report = self.cli(*arguments, optimized=optimized)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(report['reason'], 'test_symbol_uuid')

    def test_release_and_unbound_debug_reject_even_empty_test_symbol_inventory(self):
        folder = self.app / gate.TEST_SYMBOLS
        folder.mkdir(parents=True)
        self.rejected('shipping_test_inventory')
        self.simulator()
        self.debug()
        self.rejected('shipping_test_inventory', platform='simulator', configuration='Debug')
        folder.rmdir()
        folder = self.app / 'PlugIns/QRCatcherTests.dSYM'
        folder.mkdir()
        self.rejected('test_symbol_path', platform='simulator', configuration='Debug')
        archive = self.archive()
        with self.assertRaises(gate.ValidationError):
            gate.verify_package(archive)

    def test_official_darwin_relocation_triples_are_architecture_metadata_with_bound_relative_path(self):
        options = self.hosted(format_version=2)
        for architecture, cpu, triples in (('aarch64', ARM64, ('arm64-apple-darwin', 'aarch64-apple-ios17.0.0-simulator')),
                                            ('x86_64', X86_64, ('x86_64-apple-darwin', 'x86_64-apple-ios17.0.0-simulator'))):
            for endian in ('<', '>'):
                self.write_test_binary(cpu=cpu, endian=endian, extra=[
                    dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity', endian=endian),
                    dylib_command('/Developer/Library/Frameworks/XCTest.framework/XCTest', endian=endian),
                    uuid_command(TEST_UUID, endian)])
                self.symbols(symbol_macho(cpu=cpu, endian=endian, platform=None, debug_flags=0))
                for triple in triples:
                    path = self.relocations(architecture=architecture)
                    path.write_bytes(self.relocation_yaml(architecture=architecture, triple=triple))
                    with patch('subprocess.run', side_effect=AssertionError('no native metadata tools')):
                        report = gate.verify_package(self.app, **options)
                    metadata = report['hosted_tests']['symbols']['relocation_metadata'][0]['relocation_map']
                    self.assertEqual(metadata['triple'], triple)
                    self.assertEqual(metadata['architecture'], architecture)
                    self.assertEqual(metadata['triple_classification'],
                                     'mach-o-architecture-only' if triple.endswith('-darwin') else 'explicit-ios-simulator-metadata')
                    self.assertEqual(metadata['binary_path'], gate.TEST_BUNDLE + '/QRCatcherTests')
                    self.assertIs(metadata['binary_path_exact_match'], True)
                    self.assertNotIn(str(self.base), json.dumps(metadata))
                    self.assertEqual(report['hosted_tests']['symbols']['binding'],
                                     'identical-cpu-type-subtype-and-LC_UUID-for-every-slice')
                    path.unlink()
                    path.parent.rmdir()

    def test_darwin_metadata_cannot_replace_real_test_platform_cpu_subtype_or_uuid_gates(self):
        options = self.hosted()
        _, dwarf = self.symbols(symbol_macho(debug_flags=0, platform=None))
        path = self.relocations()
        path.write_bytes(self.relocation_yaml(triple='arm64-apple-darwin'))
        for platform in (2, 4, 9):
            self.write_test_binary(platform=platform)
            self.rejected('mach_o_platform', **options)
        self.write_test_binary()
        for data, reason in ((symbol_macho(debug_flags=0, platform=None, cpu=X86_64), 'test_symbol_architecture'),
                             (symbol_macho(debug_flags=0, platform=None, subtype=1), 'test_symbol_architecture'),
                             (symbol_macho(debug_flags=0, platform=None, uuid=bytes(range(17, 33))), 'test_symbol_uuid')):
            dwarf.write_bytes(data)
            self.rejected(reason, **options)
        dwarf.write_bytes(symbol_macho(debug_flags=0, platform=None))
        self.assertEqual(gate.verify_package(self.app, **options)['status'], 'pass')
        self.rejected('xctestrun_scope', platform='simulator', configuration='Release', xctestrun=options['xctestrun'])

    def test_darwin_enum_rejects_unknown_vendor_version_environment_alias_and_wrong_directory(self):
        options = self.hosted()
        self.symbols(symbol_macho(debug_flags=0))
        path = self.relocations()
        rejected = ('aarch64-apple-darwin', 'arm64-apple-darwin23.0.0', 'arm64-apple-darwin-simulator',
                    'arm64-other-darwin', 'arm64e-apple-darwin', 'arm64-apple-macosx',
                    'aarch64-apple-ios17.0.0', 'arm64-apple-tvos17.0-simulator',
                    'arm64-apple-watchos10.0-simulator', 'arm64-apple-ios17.0-macabi')
        for triple in rejected:
            with self.subTest(triple=triple):
                path.write_bytes(self.relocation_yaml(triple=triple))
                self.rejected('test_relocation_platform', **options)
        path.write_bytes(self.relocation_yaml(triple='x86_64-apple-darwin'))
        self.rejected('test_relocation_architecture', **options)

    def test_relocation_failure_retains_safe_top_metadata_without_paths_symbols_or_second_read(self):
        options = self.hosted()
        self.symbols(symbol_macho(debug_flags=0))
        path = self.relocations()
        row = "{ offset: 0x8, size: 0x8, addend: 0x0, symName: 'private symbol sentinel', symBinAddr: 0x100000000, symSize: 0x10 }"
        path.write_bytes(self.relocation_yaml(triple='arm64-apple-darwin23', records=(row,)))
        with patch.object(gate, 'read_regular', wraps=gate.read_regular) as reader:
            error = self.rejected('test_relocation_platform', **options)
        observed = error.symbol_observations['relocations'][0]
        self.assertEqual(observed['qualification'], 'unqualified')
        self.assertEqual(observed['triple'], 'arm64-apple-darwin23')
        self.assertEqual(observed['architecture_directory'], 'aarch64')
        self.assertEqual(observed['stage'], 'architecture-metadata')
        self.assertEqual(observed['rejection_enum'], 'test_relocation_platform')
        self.assertEqual(observed['declared_version'], 'absent-in-this-format')
        self.assertEqual(observed['relocation_rows_observed'], 1)
        self.assertIs(observed['binary_path_exact_match'], True)
        self.assertEqual(observed['binary_path'], gate.TEST_BUNDLE + '/QRCatcherTests')
        self.assertEqual(observed['bytes'], path.stat().st_size)
        self.assertEqual(sum(call.args[3] == str(path.relative_to(self.app)) for call in reader.call_args_list), 1)
        encoded = json.dumps(error.symbol_observations)
        self.assertNotIn(str(self.base), encoded)
        self.assertNotIn('private symbol sentinel', encoded)
        path.write_bytes(self.relocation_yaml(triple='private-sensitive-token', binary_path='/private/unowned/secret'))
        error = self.rejected('test_relocation_binary_path', **options)
        observed = error.symbol_observations['relocations'][0]
        self.assertEqual(observed['triple'], 'UNKNOWN: unsupported technical scalar')
        self.assertEqual(observed['triple_bytes'], len('private-sensitive-token'))
        self.assertEqual(len(observed['triple_sha256']), 64)
        self.assertIs(observed['binary_path_exact_match'], False)
        self.assertEqual(observed['binary_path'], 'UNKNOWN: outside exact bound executable')
        self.assertNotIn('private-sensitive-token', json.dumps(error.symbol_observations))
        self.assertNotIn('/private/unowned/secret', json.dumps(error.symbol_observations))

    def test_darwin_metadata_keeps_all_yaml_scalar_flow_field_number_and_size_rejections(self):
        options = self.hosted()
        self.symbols(symbol_macho(debug_flags=0))
        path = self.relocations()
        good = self.relocation_yaml(triple='arm64-apple-darwin')
        row = "{ offset: 0x8, size: 0x8, addend: 0x0, symName: 'synthetic', symBinAddr: 0x100000000, symSize: 0x10 }"
        cases = ((good.replace(b'triple:', b'unknown:'), 'unsupported_test_relocation_field'),
                 (good.replace(b'binary-path:', b'triple:'), 'duplicate_test_relocation_field'),
                 (good.replace(b"'arm64-apple-darwin'", b'&alias arm64-apple-darwin'), 'unsupported_test_relocation_format'),
                 (self.relocation_yaml(triple='arm64-apple-darwin', records=(row.replace('0x8, size', '0x10000000000000000, size'),)), 'unsupported_test_relocation_format'),
                 (self.relocation_yaml(triple='arm64-apple-darwin', records=(row.replace('size: 0x8', 'size: 0x100000000'),)), 'unsupported_test_relocation_format'),
                 (self.relocation_yaml(triple='arm64-apple-darwin', records=(row.replace('size: 0x8', 'size: 0x2'),)), 'test_relocation_size'),
                 (self.relocation_yaml(triple='arm64-apple-darwin', records=(row.replace('symSize:', 'unknown:'),)), 'unsupported_test_relocation_field'))
        for data, reason in cases:
            with self.subTest(reason=reason):
                path.write_bytes(data)
                self.rejected(reason, **options)

    def test_relocation_observations_respect_original_caps_and_unknown_summary_omission(self):
        options = self.hosted()
        self.symbols(symbol_macho(debug_flags=0))
        path = self.relocations()
        path.write_bytes(self.relocation_yaml(triple='arm64-apple-darwin23'))
        error = self.rejected('test_relocation_platform', limits=replace(gate.DEFAULT_LIMITS, report_bytes=512), **options)
        self.assertEqual(error.symbol_observations['summaries_omitted'], 'existing-report-budget')
        path.write_bytes(self.relocation_yaml(triple='arm64-apple-darwin'))
        report = gate.verify_package(self.app, **options)
        self.assertEqual(report['limits'], asdict(gate.DEFAULT_LIMITS))
        with self.assertRaises(gate.ValidationError) as raised:
            gate.parse_test_relocations(path.read_bytes(), str(path.relative_to(self.app)),
                                        replace(gate.DEFAULT_LIMITS, plist_bytes=128), self.test_bundle / 'QRCatcherTests')
        self.assertEqual(raised.exception.code, 'test_relocation_bytes_limit')

    def test_darwin_cli_qualification_and_unknown_failed_metadata_remain_strict_under_optimization(self):
        options = self.hosted()
        self.symbols(symbol_macho(debug_flags=0))
        path = self.relocations()
        arguments = ('--platform', 'simulator', '--configuration', 'Debug', '--xctestrun', str(options['xctestrun']))
        for optimized in (False, True):
            path.write_bytes(self.relocation_yaml(triple='arm64-apple-darwin'))
            result, report = self.cli(*arguments, optimized=optimized)
            self.assertEqual(result.returncode, 0, result.stderr)
            metadata = report['hosted_tests']['symbols']['relocation_metadata'][0]['relocation_map']
            self.assertEqual(metadata['binary_path'], gate.TEST_BUNDLE + '/QRCatcherTests')
            self.assertEqual(metadata['triple_classification'], 'mach-o-architecture-only')
            self.assertNotIn(str(self.base), json.dumps(metadata))
            path.write_bytes(self.relocation_yaml(triple='arm64-apple-darwin23'))
            result, report = self.cli(*arguments, optimized=optimized)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['reason'], 'test_relocation_platform')
            self.assertEqual(report['test_symbol_observations']['relocations'][0]['triple'], 'arm64-apple-darwin23')
            self.assertEqual(report['test_symbol_observations']['relocations'][0]['rejection_enum'], 'test_relocation_platform')
            self.assertLessEqual(len(result.stdout.encode()), gate.DEFAULT_LIMITS.report_bytes)

    def test_optional_relocation_metadata_accepts_public_empty_and_nonempty_flow_maps(self):
        options = self.hosted(format_version=2)
        self.symbols()
        row = "{ offset: 0x8, size: 0x8, addend: 0x0, symName: '-[QRWatchPhoneService item:]', symObjAddr: 0x0, symBinAddr: 0x100000000, symSize: 0x10 }"
        quoted_row = row.replace("'-[QRWatchPhoneService item:]'", "'symbol, with a doubled ''quote'''" )
        path = self.relocations()
        for records in ((), (row,), (row, quoted_row),
                        (row.replace('symObjAddr: 0x0, ', '').replace("'-[QRWatchPhoneService item:]'", json.dumps('symbol"name')),)):
            with self.subTest(records=len(records)):
                path.write_bytes(self.relocation_yaml(records=records))
                report = gate.verify_package(self.app, **options)
                resources = report['hosted_tests']['symbols']['relocation_metadata']
                self.assertEqual(len(resources), 1)
                self.assertEqual(resources[0]['path'], str(path.relative_to(self.app)))
                metadata = resources[0]['relocation_map']
                self.assertEqual(metadata['classification'], 'test-symbol-relocation-metadata')
                self.assertEqual(metadata['relocation_count'], len(records))
                self.assertEqual(metadata['binary_path'], gate.TEST_BUNDLE + '/QRCatcherTests')
                self.assertIs(metadata['binary_path_exact_match'], True)
                self.assertEqual([image['path'] for image in report['mach_o']], ['QRCatcher'])
                self.assertEqual(len(report['hosted_tests']['mach_o']), 1)
        for triple in ('arm64-apple-ios17.0.0-simulator', 'aarch64-apple-ios-simulator'):
            path.write_bytes(self.relocation_yaml(triple=triple))
            self.assertEqual(gate.verify_package(self.app, **options)['status'], 'pass')

    def test_relocation_metadata_owns_exact_test_binary_simulator_triple_and_architecture(self):
        options = self.hosted()
        self.symbols()
        path = self.relocations()
        for binary_path in (str(self.app / 'QRCatcher'), str(self.base / 'QRCatcherTests'),
                            str(self.test_bundle / '..' / 'QRCatcherTests.xctest/QRCatcherTests')):
            with self.subTest(binary_path=binary_path):
                path.write_bytes(self.relocation_yaml(binary_path=binary_path))
                self.rejected('test_relocation_binary_path', **options)
        for triple in ('aarch64-apple-ios17.0.0', 'aarch64-apple-tvos17.0.0-simulator',
                       'aarch64-unknown-ios17.0.0-simulator', 'aarch64-apple-watchos17.0.0-simulator'):
            with self.subTest(triple=triple):
                path.write_bytes(self.relocation_yaml(triple=triple))
                self.rejected('test_relocation_platform', **options)
        path.write_bytes(self.relocation_yaml(triple='x86_64-apple-ios17.0.0-simulator'))
        self.rejected('test_relocation_architecture', **options)
        path.write_bytes(self.relocation_yaml())
        foreign = self.relocations(architecture='x86_64')
        self.rejected('test_relocation_architecture', **options)
        foreign.unlink()
        foreign.parent.rmdir()

    def test_relocation_metadata_rejects_duplicates_unknown_fields_malformed_yaml_and_code(self):
        options = self.hosted()
        self.symbols()
        row = "{ offset: 0x8, size: 0x4, addend: 0x0, symName: _ordinary, symBinAddr: 0x100000000, symSize: 0x10 }"
        valid = self.relocation_yaml(records=(row,))
        path = self.relocations()
        cases = ((valid.replace(b'triple:', b'triple: aarch64-apple-ios-simulator\ntriple:', 1), 'duplicate_test_relocation_field'),
                 (valid.replace(b'size: 0x4,', b'size: 0x4, size: 0x8,'), 'duplicate_test_relocation_field'),
                 (valid.replace(b'triple:', b'unknown:'), 'unsupported_test_relocation_field'),
                 (valid.replace(b'symSize: 0x10', b'symSize: 0x10, unknown: 0x0'), 'unsupported_test_relocation_field'),
                 (valid.replace(b'offset: 0x8', b'offset: 0x10000000000000000'), 'unsupported_test_relocation_format'),
                 (valid.replace(b'size: 0x4', b'size: 0x2'), 'test_relocation_size'),
                 (valid.replace(b'symSize: 0x10', b'symSize: []'), 'unsupported_test_relocation_format'),
                 (valid.replace(b'symName: _ordinary, ', b''), 'unsupported_test_relocation_format'),
                 (valid.replace(b'{ offset: 0x8, ', b'offset: 0x8\n    '), 'unsupported_test_relocation_format'),
                 (valid.replace(b'symName: _ordinary', b'symName: *alias'), 'unsupported_test_relocation_format'),
                 (valid.replace(b'...\n', b'...\n---\n'), 'unsupported_test_relocation_format'),
                 (valid[:-5], 'unsupported_test_relocation_format'),
                 (b'\xff\xfeinvalid', 'test_relocation_encoding'),
                 (valid + b'\0', 'test_relocation_encoding'),
                 (macho(platform=7, filetype=8), 'test_relocation_runtime_code'))
        for data, reason in cases:
            with self.subTest(reason=reason, data=data[:40]):
                path.write_bytes(data)
                self.rejected(reason, **options)

    def test_relocation_metadata_reuses_existing_size_node_symbol_and_total_limits(self):
        options = self.hosted()
        self.symbols()
        row = "{ offset: 0x8, size: 0x4, addend: 0x0, symName: _ordinary, symBinAddr: 0x100000000, symSize: 0x10 }"
        path = self.relocations()
        path.write_bytes(b'x' * (gate.DEFAULT_LIMITS.plist_bytes + 1))
        self.rejected('test_relocation_bytes_limit', **options)
        path.write_bytes(self.relocation_yaml(records=(row,) * 100))
        self.rejected('test_relocation_node_limit', limits=replace(gate.DEFAULT_LIMITS, plist_nodes=256), **options)
        path.write_bytes(self.relocation_yaml(records=(row.replace('_ordinary', 'x' * (gate.DEFAULT_LIMITS.dependency_bytes + 1)),)))
        self.rejected('test_relocation_symbol_limit', **options)
        path.write_bytes(self.relocation_yaml())
        report = gate.verify_package(self.app, **options)
        self.rejected('total_bytes_limit', limits=replace(gate.DEFAULT_LIMITS, total_bytes=report['inventory']['file_bytes'] - 1), **options)

    def test_relocation_inventory_requires_exact_filename_regular_type_and_closed_resources(self):
        options = self.hosted()
        folder, _ = self.symbols()
        path = self.relocations()
        original = path.read_bytes()
        wrong = path.with_name('Foreign.yml')
        path.rename(wrong)
        self.rejected('test_symbol_inventory', **options)
        wrong.rename(path)
        outside = self.base / 'outside-relocations.yml'
        path.rename(outside)
        path.symlink_to(outside)
        self.rejected('symlink', **options)
        path.unlink()
        os.mkfifo(path)
        self.rejected('unsupported_file_type', **options)
        path.unlink()
        path.write_bytes(original)
        for relative in ('Contents/Resources/Relocations/arm64',
                         'Contents/Resources/Swift/aarch64', 'Contents/Resources/Remarks',
                         'Contents/Resources/Relocations/aarch64/nested'):
            with self.subTest(relative=relative):
                entry = folder / relative
                entry.mkdir(parents=True)
                self.rejected('test_symbol_inventory', **options)
                entry.rmdir()
                if relative.startswith('Contents/Resources/Swift/'):
                    entry.parent.rmdir()

    def test_relocation_metadata_and_platform_rejection_remain_active_under_optimization(self):
        options = self.hosted()
        self.symbols()
        path = self.relocations()
        arguments = ('--platform', 'simulator', '--configuration', 'Debug', '--xctestrun', str(options['xctestrun']))
        for optimized in (False, True):
            path.write_bytes(self.relocation_yaml())
            result, report = self.cli(*arguments, optimized=optimized)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(report['hosted_tests']['symbols']['relocation_metadata'][0]['relocation_map']['relocation_count'], 0)
            path.write_bytes(self.relocation_yaml(triple='aarch64-apple-ios17.0.0'))
            result, report = self.cli(*arguments, optimized=optimized)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['reason'], 'test_relocation_platform')

    def test_symbol_failures_retain_only_bounded_unqualified_observations_from_existing_reads(self):
        options = self.hosted()
        _, dwarf = self.symbols(symbol_macho(uuid=bytes(range(17, 33)), markers=b'private DWARF source sentinel'))
        self.relocations()
        with patch.object(gate, 'read_regular', wraps=gate.read_regular) as reader:
            error = self.rejected('test_symbol_uuid', **options)
        evidence = error.symbol_observations
        self.assertEqual(evidence['qualification'], 'unqualified')
        self.assertEqual(evidence['scope'], 'exact-xctestrun-bound-test-symbol-companion')
        self.assertEqual(evidence['path'], gate.TEST_SYMBOLS)
        self.assertTrue(all(entry['path'].startswith(gate.TEST_SYMBOLS) and not Path(entry['path']).is_absolute()
                            for entry in evidence['inventory']))
        self.assertEqual(evidence['plist']['keys']['CFBundlePackageType']['value'], 'dSYM')
        observed = evidence['mach_o'][0]['slices'][0]
        self.assertEqual(observed['file_type'], 0xA)
        self.assertEqual(observed['architecture'], 'arm64')
        self.assertEqual(observed['uuid'], bytes(range(17, 33)).hex())
        reference = evidence['bound_test_binary']
        self.assertEqual(set(reference), {'path', 'slices'})
        self.assertEqual(reference['path'], gate.TEST_BUNDLE + '/QRCatcherTests')
        self.assertFalse(Path(reference['path']).is_absolute())
        self.assertEqual(reference['slices'], [{'file_type': 8, 'cpu_type': ARM64, 'cpu_subtype': 0,
                                               'architecture': 'arm64', 'uuid': TEST_UUID.hex()}])
        self.assertNotEqual(reference['slices'][0]['uuid'], observed['uuid'])
        self.assertEqual(sum(call.args[3] == gate.TEST_DWARF for call in reader.call_args_list), 1)
        self.assertEqual(sum(call.args[3] == gate.TEST_BUNDLE + '/QRCatcherTests'
                             for call in reader.call_args_list), 1)
        encoded = gate.encode_report({'schema_version': 1, 'status': 'fail', 'reason': error.code,
                                      'test_symbol_observations': evidence})
        self.assertLessEqual(len(encoded), gate.DEFAULT_LIMITS.report_bytes)
        self.assertNotIn(b'private DWARF source sentinel', encoded)
        self.assertNotIn(b'QRWatchPhoneService', encoded)
        dwarf.write_bytes(symbol_macho())
        self.symbol_info['CFBundlePackageType'] = 'BNDL'
        self.write_symbol_info()
        error = self.rejected('test_symbol_metadata', **options)
        self.assertEqual(error.symbol_observations['plist']['keys']['CFBundlePackageType']['value'], 'BNDL')
        self.symbol_info['CFBundlePackageType'] = 'dSYM'
        self.write_symbol_info()
        dwarf.write_bytes(macho(platform=7, filetype=8))
        error = self.rejected('test_symbol_file_type', **options)
        self.assertEqual(error.symbol_observations['mach_o'][0]['slices'][0]['file_type'], 8)
        self.assertIsNone(error.symbol_observations['mach_o'][0]['slices'][0]['uuid'])
        dwarf.write_bytes(symbol_macho(extra=[uuid_command()]))
        error = self.rejected('duplicate_uuid_command', **options)
        self.assertEqual(error.symbol_observations['mach_o'][0]['slices'][0]['uuid_commands_observed'], 2)
        dwarf.write_bytes(symbol_macho(uuid=bytes(range(17, 33))))
        error = self.rejected('test_symbol_uuid', limits=replace(gate.DEFAULT_LIMITS, report_bytes=512), **options)
        self.assertEqual(error.symbol_observations['summaries_omitted'], 'existing-report-budget')

    def test_symbol_failure_json_retention_obeys_actual_binding_and_optimization(self):
        options = self.hosted()
        _, dwarf = self.symbols(symbol_macho(uuid=bytes(range(17, 33)), markers=b'private DWARF source sentinel'))
        arguments = ('--platform', 'simulator', '--configuration', 'Debug', '--xctestrun', str(options['xctestrun']))
        for optimized in (False, True):
            result, report = self.cli(*arguments, optimized=optimized)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['reason'], 'test_symbol_uuid')
            evidence = report['test_symbol_observations']
            self.assertEqual(evidence['qualification'], 'unqualified')
            self.assertEqual(evidence['mach_o'][0]['slices'][0]['uuid'], bytes(range(17, 33)).hex())
            reference = evidence['bound_test_binary']
            self.assertEqual(set(reference), {'path', 'slices'})
            self.assertEqual(reference['path'], gate.TEST_BUNDLE + '/QRCatcherTests')
            self.assertFalse(Path(reference['path']).is_absolute())
            self.assertEqual(reference['slices'][0]['uuid'], TEST_UUID.hex())
            self.assertEqual(set(reference['slices'][0]), {'file_type', 'cpu_type', 'cpu_subtype', 'architecture', 'uuid'})
            self.assertNotIn('private DWARF source sentinel', json.dumps(report))
            self.assertLessEqual(len(result.stdout.encode('utf-8')), gate.DEFAULT_LIMITS.report_bytes)
        self.test_target['TestHostBundleIdentifier'] = 'example.foreign'
        self.write_xctestrun()
        result, report = self.cli(*arguments)
        self.assertEqual(report['reason'], 'test_host_binding')
        self.assertNotIn('test_symbol_observations', report)

    def test_optional_target_triple_matches_bound_arm64_x86_fat_and_both_endiannesses(self):
        options = self.hosted()
        for endian in ('<', '>'):
            images = []
            companions = []
            for cpu, subtype, architecture, uuid in ((ARM64, 0, 'arm64', TEST_UUID),
                                                     (X86_64, 3, 'x86_64', bytes(range(17, 33)))):
                triple = architecture + '-apple-ios17.0.0-simulator'
                self.write_test_binary(cpu=cpu, subtype=subtype, endian=endian, extra=[
                    dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity', endian=endian),
                    uuid_command(uuid, endian), target_triple_command(triple, endian)])
                image = (self.test_bundle / 'QRCatcherTests').read_bytes()
                companion = symbol_macho(cpu=cpu, subtype=subtype, endian=endian, uuid=uuid,
                                         extra=[target_triple_command(triple, endian)])
                self.symbols(companion)
                report = gate.verify_package(self.app, **options)
                self.assertEqual(report['hosted_tests']['symbols']['dwarf']['slices'][0]['target_triple'], triple)
                images.append(image)
                companions.append(companion)
            for wide in (False, True):
                for fat_endian in ('<', '>'):
                    with self.subTest(endian=endian, wide=wide, fat_endian=fat_endian):
                        (self.test_bundle / 'QRCatcherTests').write_bytes(fat(images, wide, fat_endian))
                        self.symbols(fat(list(reversed(companions)), wide, fat_endian))
                        report = gate.verify_package(self.app, **options)
                        self.assertEqual(len(report['hosted_tests']['symbols']['dwarf']['slices']), 2)

    def test_target_triple_rejects_malformed_offset_nul_padding_encoding_size_and_duplicates(self):
        options = self.hosted()
        _, dwarf = self.symbols()
        command = target_triple_command()
        size = len(command)
        padded = bytearray(target_triple_command(offset=16))
        padded[12] = 1
        cases = ((struct.pack('<3I', 0x39, size, 11) + command[12:], 'malformed_target_triple_command'),
                 (struct.pack('<3I', 0x39, size, size) + command[12:], 'malformed_target_triple_command'),
                 (command[:12] + b'X' * (size - 12), 'malformed_target_triple_command'),
                 (command[:-1] + b'X', 'malformed_target_triple_command'),
                 (target_triple_command(''), 'malformed_target_triple_command'),
                 (target_triple_command('arm64-apple-ios17.0.0-simulator\n'), 'malformed_target_triple_command'),
                 (target_triple_command('arm64-apple-ios17.0.0-simulatör'), 'malformed_target_triple_command'),
                 (target_triple_command('x' * (gate.DEFAULT_LIMITS.dependency_bytes + 1)), 'malformed_target_triple_command'),
                 (bytes(padded), 'malformed_target_triple_command'),
                 (struct.pack('<2I', 0x39, 8), 'malformed_target_triple_command'))
        for value, reason in cases:
            with self.subTest(value=value[:24]):
                dwarf.write_bytes(symbol_macho(extra=[value]))
                self.rejected(reason, **options)
        dwarf.write_bytes(symbol_macho(extra=[command, command]))
        self.rejected('duplicate_target_triple_command', **options)
        self.write_test_binary(extra=[
            dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity'),
            uuid_command(), command, command])
        dwarf.write_bytes(symbol_macho(extra=[command]))
        self.rejected('duplicate_target_triple_command', **options)

    def test_target_triple_requires_both_sides_exact_simulator_architecture_and_platform(self):
        options = self.hosted()
        _, dwarf = self.symbols()
        command = target_triple_command()
        dwarf.write_bytes(symbol_macho(extra=[command]))
        self.rejected('test_symbol_target_triple', **options)
        self.write_test_binary(extra=[
            dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity'),
            uuid_command(), command])
        dwarf.write_bytes(symbol_macho())
        self.rejected('test_symbol_target_triple', **options)
        dwarf.write_bytes(symbol_macho(extra=[target_triple_command('arm64-apple-ios18.0.0-simulator')]))
        self.rejected('test_symbol_target_triple', **options)
        dwarf.write_bytes(symbol_macho(extra=[target_triple_command('x86_64-apple-ios17.0.0-simulator')]))
        self.rejected('test_symbol_target_architecture', **options)
        for triple in ('arm64-apple-ios17.0.0', 'arm64-apple-tvos17.0.0-simulator',
                       'arm64-apple-watchos17.0.0-simulator', 'arm64-apple-macosx17.0.0',
                       'arm64-unknown-ios17.0.0-simulator'):
            with self.subTest(triple=triple):
                dwarf.write_bytes(symbol_macho(extra=[target_triple_command(triple)]))
                self.rejected('test_symbol_target_platform', **options)
        padded = target_triple_command(offset=16)
        self.write_test_binary(extra=[
            dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity'),
            uuid_command(), padded])
        dwarf.write_bytes(symbol_macho(extra=[padded]))
        self.assertEqual(gate.verify_package(self.app, **options)['status'], 'pass')

    def test_target_triple_cli_positive_and_mismatch_remain_active_under_optimization(self):
        options = self.hosted()
        command = target_triple_command()
        self.write_test_binary(extra=[
            dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity'),
            uuid_command(), command])
        _, dwarf = self.symbols()
        arguments = ('--platform', 'simulator', '--configuration', 'Debug', '--xctestrun', str(options['xctestrun']))
        for optimized in (False, True):
            dwarf.write_bytes(symbol_macho(extra=[command]))
            result, report = self.cli(*arguments, optimized=optimized)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(report['hosted_tests']['symbols']['dwarf']['slices'][0]['target_triple'], 'arm64-apple-ios17.0.0-simulator')
            dwarf.write_bytes(symbol_macho(extra=[target_triple_command('arm64-apple-ios18.0.0-simulator')]))
            result, report = self.cli(*arguments, optimized=optimized)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['reason'], 'test_symbol_target_triple')
            observations = report['test_symbol_observations']
            self.assertEqual(observations['qualification'], 'unqualified')
            self.assertEqual(observations['bound_test_binary']['slices'][0]['target_triple'], 'arm64-apple-ios17.0.0-simulator')
            self.assertEqual(observations['mach_o'][0]['slices'][0]['target_triple'], 'arm64-apple-ios18.0.0-simulator')

    def test_device_identity_inventory_and_stripped_symbol_table(self):
        with patch('subprocess.run', side_effect=AssertionError('must not execute Apple tools')):
            report = gate.verify_package(self.app)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['bundle_id'], gate.BUNDLE_ID)
        self.assertEqual(report['device_families'], [1, 2])
        self.assertEqual(report['supported_platforms'], ['iPhoneOS'])
        self.assertEqual(report['minimum_os'], '15.0')
        self.assertEqual(report['inventory']['files'], 4)
        self.assertEqual(len(report['inventory']['sha256']), 64)
        self.assertEqual(report['mach_o'][0]['slices'][0]['architecture'], 'arm64')

    def test_simulator_fat_both_architectures_all_endianness_and_widths(self):
        self.simulator()
        for wide in (False, True):
            for endian in ('<', '>'):
                with self.subTest(wide=wide, endian=endian):
                    self.write_binary(fat([macho(platform=7), macho(platform=7, cpu=X86_64, endian='>')], wide, endian))
                    report = gate.verify_package(self.app, platform='simulator')
                    self.assertEqual([value['architecture'] for value in report['mach_o'][0]['slices']], ['arm64', 'x86_64'])

    def test_legacy_ios_platform_command_supported(self):
        self.write_binary(macho(legacy=True))
        self.assertEqual(gate.verify_package(self.app)['status'], 'pass')
        self.simulator()
        self.write_binary(macho(platform=7, cpu=X86_64, legacy=True))
        self.assertEqual(gate.verify_package(self.app, platform='simulator')['status'], 'pass')

    def test_metadata_original_identity_and_ios_families_are_closed(self):
        original = self.info.copy()
        defects = {'CFBundleIdentifier': ['example.Changed'],
                   'CFBundleExecutable': ['Other', '../QRCatcher', 'nested/QRCatcher', '..'],
                   'CFBundlePackageType': ['BNDL'], 'CFBundleShortVersionString': ['2.0'],
                   'CFBundleVersion': [2, '3'], 'MinimumOSVersion': ['17.0'],
                   'UIDeviceFamily': [[1], [2], [1, 2, 4], [True, 2], [1, 2, 2]],
                   'CFBundleSupportedPlatforms': [['WatchOS'], ['iPhoneOS', 'WatchOS'], ['iPhoneSimulator'], []]}
        for key, values in defects.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.info = dict(original, **{key: value})
                    self.write_info()
                    self.rejected()
        self.info = original

    def test_binary_device_simulator_watch_tv_catalyst_platform_mismatch(self):
        for platform in (1, 3, 4, 6, 7, 8, 9, 11, 12, 0):
            with self.subTest(platform=platform):
                self.write_binary(macho(platform=platform))
                self.rejected('mach_o_platform')
        self.write_binary(macho(cpu=X86_64))
        self.rejected('mach_o_architecture')
        self.write_binary(macho(cpu=0x0200000C))
        self.rejected('unsupported_architecture')

    def test_raised_or_lowered_main_binary_floor_rejected(self):
        for minimum in (14 << 16, 17 << 16):
            self.write_binary(macho(minimum=minimum))
            self.rejected('mach_o_minimum_os')

    def test_nested_framework_may_keep_older_ios_floor(self):
        self.framework(data=macho(filetype=6, minimum=13 << 16))
        report = gate.verify_package(self.app)
        self.assertEqual(len(report['mach_o']), 2)

    def test_every_framework_and_dylib_inspected_for_watch(self):
        framework = self.framework()
        (framework / 'Ordinary').write_bytes(macho(filetype=6, platform=4))
        self.rejected('mach_o_platform')
        (framework / 'Ordinary').write_bytes(macho(filetype=6))
        (self.app / 'Frameworks/libOrdinary.dylib').write_bytes(macho(filetype=6, markers=b'QRWatchSessionGate\0'))
        self.rejected('watch_presence')

    def test_all_dependency_command_variants_reject_watch_connectivity_without_symbols(self):
        for command in gate.DYLIB_COMMANDS:
            with self.subTest(command=command):
                self.write_binary(macho(extra=[dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity', command)]))
                self.rejected('watch_presence')

    def test_stripped_helper_class_names_and_utf16_strings_rejected(self):
        for marker in ('QRWatchPhoneService', 'QRWatchSessionGate', 'WCSession', 'WatchPhoneTransport'):
            for encoding in ('ascii', 'utf-16-le', 'utf-16-be'):
                with self.subTest(marker=marker, encoding=encoding):
                    self.write_binary(macho(markers=marker.encode(encoding) + b'\0'))
                    self.rejected('watch_presence')

    def test_watch_metadata_keys_rejected_even_false_nested_or_binary_plist(self):
        for key in ('WKApplication', 'WKWatchKitApp', 'WKCompanionAppBundleIdentifier',
                    'WKRunsIndependentlyOfCompanionApp', 'WKAppBundleIdentifier', 'WKSupportsRunningWithoutiOSAppInstallation'):
            with self.subTest(key=key):
                extra = self.app / 'orphan.plist'
                extra.write_bytes(plistlib.dumps({'NSExtension': {key: False}}, fmt=plistlib.FMT_BINARY))
                self.rejected('watch_plist_key')
                extra.unlink()

    def test_watch_extension_point_and_family_rejected(self):
        extra = self.app / 'metadata.plist'
        for payload in ({'NSExtension': {'NSExtensionPointIdentifier': 'com.apple.watchkit'}},
                        {'UIDeviceFamily': [4]}, {'CFBundleSupportedPlatforms': ['WatchOS']}):
            extra.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_BINARY))
            self.rejected()

    def test_orphan_empty_watch_directories_and_renamed_apps_rejected(self):
        for name in ('Watch', 'wAtCh', 'WatchOS', 'Plugin.watchkitextension', 'Plugin.watchkitapp',
                     'innocent.app', 'QRCatcherWatch.bundle', 'WatchConnectivity.framework'):
            with self.subTest(name=name):
                folder = self.app / name
                folder.mkdir()
                self.rejected()
                folder.rmdir()

    def test_orphan_framework_and_undeclared_code_rejected(self):
        folder = self.app / 'Frameworks/Orphan.framework'
        folder.mkdir(parents=True)
        self.rejected('orphan_bundle')
        folder.rmdir()
        (self.app / 'unclaimed').write_bytes(macho(filetype=6))
        self.rejected('orphan_mach_o')

    def test_orphan_info_executable_and_malformed_named_dylib_rejected(self):
        extra = self.app / 'orphan.plist'
        extra.write_bytes(plistlib.dumps({'CFBundleExecutable': 'QRCatcher'}))
        self.rejected('orphan_bundle_info')
        extra.unlink()
        (self.app / 'unreadable.dylib').write_bytes(b'pretend dylib')
        self.rejected('unsupported_shipping_code')

    def test_missing_or_non_mach_o_main_executable_rejected(self):
        for value in (b'', b'ordinary fake executable', b'\xce\xfa\xed\xfe' + b'\0' * 64):
            self.write_binary(value)
            self.rejected()
        (self.app / 'QRCatcher').unlink()
        self.rejected('missing_shipping_mach_o')

    def test_release_diagnostics_raw_strings_and_plist_strings_rejected(self):
        for marker in gate.DIAGNOSTIC_MARKERS:
            with self.subTest(marker=marker):
                self.write_binary(macho(markers=marker.encode('ascii')))
                self.rejected('release_diagnostics')
        self.write_binary(macho())
        (self.app / 'diagnostic.plist').write_bytes(plistlib.dumps({'Marker': '-mini-startup-observation-v1'}, fmt=plistlib.FMT_BINARY))
        self.rejected('release_diagnostics')

    def test_debug_diagnostics_and_all_known_debug_dylibs_allowed(self):
        self.simulator()
        self.debug()
        self.write_binary(macho(platform=7, markers=b'QRStartupObservationBegin\0'))
        for name in ('QRCatcher.debug.dylib', '__preview.dylib'):
            (self.app / name).write_bytes(macho(platform=7, filetype=6, markers=b'-ui-testing\0'))
        report = gate.verify_package(self.app, platform='simulator', configuration='Debug')
        self.assertEqual(report['configuration'], 'Debug')
        self.assertEqual(len(report['mach_o']), 3)
        self.rejected('release_diagnostics', platform='simulator')

    def test_debug_dylibs_cannot_hide_watch_helpers_or_platforms(self):
        self.simulator()
        self.debug()
        for data in (macho(platform=7, filetype=6, markers=b'QRWatchPhoneService\0'),
                     macho(platform=9, filetype=6)):
            (self.app / 'QRCatcher.debug.dylib').write_bytes(data)
            self.rejected(platform='simulator', configuration='Debug')

    def test_release_rejects_debug_layout_even_without_diagnostic_strings(self):
        (self.app / '__preview.dylib').write_bytes(macho(filetype=6))
        self.rejected('orphan_mach_o')

    def test_release_archive_rejects_test_packages_symbols_and_xctest_outer_inventory(self):
        archive = self.archive()
        for relative in ('Products/Tests/Hosted.xctest', 'dSYMs/QRCatcherTests.xctest.dSYM',
                         'dSYMs/QRCatcherTests.dSYM', 'Products/Library/XCTest.framework',
                         'Symbols/xCtEsT-support'):
            with self.subTest(relative=relative):
                entry = archive / relative
                entry.mkdir(parents=True)
                with self.assertRaises(gate.ValidationError) as raised:
                    gate.verify_package(archive)
                self.assertEqual(raised.exception.code, 'archive_test_inventory')
                entry.rmdir()

    def test_release_archive_preserves_normal_app_symbols_and_metadata_under_shared_limits(self):
        archive = self.archive()
        symbols = archive / 'dSYMs/QRCatcher.app.dSYM/Contents/Resources/DWARF'
        symbols.mkdir(parents=True)
        (symbols / 'QRCatcher').write_bytes(symbol_macho(platform=2))
        (symbols.parent.parent / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'com.apple.xcode.dsym.' + gate.BUNDLE_ID,
            'CFBundlePackageType': 'dSYM', 'CFBundleInfoDictionaryVersion': '6.0'}))
        report = gate.verify_package(archive)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(len(report['mach_o']), 1)
        self.assertEqual(report['inventory']['files'], 4)
        self.assertEqual(report['archive_inventory']['files'], 7)
        self.assertGreater(report['archive_inventory']['entries'], report['inventory']['entries'])
        for field in ('entries', 'file_bytes'):
            limits = replace(gate.DEFAULT_LIMITS, **{field if field == 'entries' else 'total_bytes':
                                                   report['archive_inventory'][field] - 1})
            with self.subTest(field=field), self.assertRaises(gate.ValidationError) as raised:
                gate.verify_package(archive, limits=limits)
            self.assertEqual(raised.exception.code, 'inventory_entry_limit' if field == 'entries' else 'total_bytes_limit')

    def test_release_archive_rejects_outer_test_symbol_metadata_and_path_aliases(self):
        archive = self.archive()
        symbols = archive / 'dSYMs/Ordinary.dSYM/Contents'
        symbols.mkdir(parents=True)
        metadata = symbols / 'Info.plist'
        metadata.write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.apple.xcode.dsym.' + gate.TEST_BUNDLE_ID,
                                             'CFBundlePackageType': 'dSYM'}))
        with self.assertRaises(gate.ValidationError) as raised:
            gate.verify_package(archive)
        self.assertEqual(raised.exception.code, 'archive_test_metadata')
        metadata.unlink()
        outside = self.base / 'outside-symbols'
        outside.mkdir()
        link = archive / 'dSYMs/linked'
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(gate.ValidationError) as raised:
            gate.verify_package(archive)
        self.assertEqual(raised.exception.code, 'symlink')

    def test_release_archive_rejects_additional_or_renamed_installed_apps(self):
        archive = self.archive()
        other = archive / 'Products/Applications/Other.app'
        other.mkdir()
        with self.assertRaises(gate.ValidationError) as raised:
            gate.verify_package(archive)
        self.assertEqual(raised.exception.code, 'archive_app_inventory')
        other.rmdir()
        renamed = self.app.with_name('Other.app')
        self.app.rename(renamed)
        props = plistlib.loads((archive / 'Info.plist').read_bytes())
        props['ApplicationProperties']['ApplicationPath'] = 'Applications/Other.app'
        (archive / 'Info.plist').write_bytes(plistlib.dumps(props))
        with self.assertRaises(gate.ValidationError) as raised:
            gate.verify_package(archive)
        self.assertEqual(raised.exception.code, 'archive_app_inventory')

    def test_release_archive_outer_inventory_gate_remains_active_under_optimization(self):
        archive = self.archive()
        self.app = archive
        for optimized in (False, True):
            result, report = self.cli(optimized=optimized)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNotNone(report['archive_inventory'])
        tests = archive / 'Products/Tests/Hosted.xctest'
        tests.mkdir(parents=True)
        for optimized in (False, True):
            result, report = self.cli(optimized=optimized)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['reason'], 'archive_test_inventory')

    def test_shipped_test_bundle_rejected(self):
        (self.app / 'PlugIns/Hosted.xctest').mkdir(parents=True)
        self.rejected('release_test_bundle')
        archive = self.archive()
        with self.assertRaises(gate.ValidationError) as raised:
            gate.verify_package(archive)
        self.assertEqual(raised.exception.code, 'release_test_bundle')

    def test_archive_identity_and_orphan_applications_rejected(self):
        archive = self.archive()
        props = plistlib.loads((archive / 'Info.plist').read_bytes())
        props['ApplicationProperties']['ApplicationPath'] = '../other.app'
        (archive / 'Info.plist').write_bytes(plistlib.dumps(props))
        with self.assertRaises(gate.ValidationError) as raised:
            gate.verify_package(archive)
        self.assertEqual(raised.exception.code, 'archive_identity')
        (archive / 'Products/Applications/orphan').write_bytes(b'ordinary orphan')
        with self.assertRaises(gate.ValidationError) as raised:
            gate.verify_package(archive)
        self.assertEqual(raised.exception.code, 'archive_app_inventory')

    def test_symlinks_root_directory_files_and_archive_metadata_rejected(self):
        link = self.base / 'Linked.app'
        link.symlink_to(self.app, target_is_directory=True)
        with self.assertRaises(gate.ValidationError):
            gate.verify_package(link)
        for is_directory in (False, True):
            target = self.base / ('outside-dir' if is_directory else 'outside-file')
            target.mkdir() if is_directory else target.write_bytes(b'ordinary')
            shipped = self.app / 'linked'
            shipped.symlink_to(target, target_is_directory=is_directory)
            self.rejected('symlink')
            shipped.unlink()
        archive = self.archive()
        metadata = archive / 'Info.plist'
        outside = self.base / 'archive-info.plist'
        metadata.rename(outside)
        metadata.symlink_to(outside)
        with self.assertRaises(gate.ValidationError):
            gate.verify_package(archive)

    def test_special_fifo_and_hardlinked_files_fail_before_read(self):
        fifo = self.app / 'pipe'
        os.mkfifo(fifo)
        self.rejected('unsupported_file_type')
        fifo.unlink()
        outside = self.base / 'hardlink-source'
        outside.write_bytes(b'ordinary')
        os.link(outside, self.app / 'hardlink')
        self.rejected('hardlinked_file')

    def test_byte_limits_precede_read_and_include_all_files(self):
        limits = replace(gate.DEFAULT_LIMITS, file_bytes=32)
        with patch.object(gate, 'read_regular', wraps=gate.read_regular) as reader:
            self.rejected('file_bytes_limit', limits=limits)
            self.assertTrue(reader.called)
        self.rejected('total_bytes_limit', limits=replace(gate.DEFAULT_LIMITS, total_bytes=1))
        self.rejected('plist_bytes_limit', limits=replace(gate.DEFAULT_LIMITS, plist_bytes=1))

    def test_entry_limits_count_empty_directories_without_unbounded_list(self):
        for index in range(3):
            (self.app / ('empty-' + str(index))).mkdir()
        self.rejected('inventory_entry_limit', limits=replace(gate.DEFAULT_LIMITS, entries=5))
        self.rejected('directory_entry_limit', limits=replace(gate.DEFAULT_LIMITS, directory_entries=5))

    def test_path_depth_plist_nodes_and_report_caps(self):
        (self.app / 'a/b/c/d/e/f/g/h/i').mkdir(parents=True)
        self.rejected('directory_depth_limit', limits=replace(gate.DEFAULT_LIMITS, depth=8))
        self.rejected('path_limit', limits=replace(gate.DEFAULT_LIMITS, path_bytes=4))
        self.rejected('plist_limit', limits=replace(gate.DEFAULT_LIMITS, plist_nodes=2))
        self.rejected('report_bytes_limit', limits=replace(gate.DEFAULT_LIMITS, report_bytes=128))

    def test_missing_malformed_and_overly_nested_plists_fail_closed(self):
        for value in (b'', b'<plist><dict>', b'bplist00' + b'\0' * 16, plistlib.dumps(['wrong root'])):
            (self.app / 'Info.plist').write_bytes(value)
            self.rejected('malformed_plist')
        self.write_info()
        nested = 'ordinary'
        for _ in range(40):
            nested = [nested]
        (self.app / 'deep.plist').write_bytes(plistlib.dumps({'nested': nested}))
        self.rejected('plist_limit')
        (self.app / 'Info.plist').unlink()
        (self.app / 'deep.plist').unlink()
        self.rejected('missing_bundle_info')

    def test_truncated_binary_header_command_table_segment_and_payload(self):
        good = macho()
        for end in (4, 20, 31, 32, len(good) - 4, len(good) - 1):
            with self.subTest(end=end):
                self.write_binary(good[:end])
                self.rejected()

    def test_malformed_load_command_sizes_counts_and_reserved_header(self):
        good = macho()
        for field, value in ((16, 0), (16, 5000), (20, 0), (20, 2 << 20), (28, 1),
                             (36, 0), (36, 7), (36, 0xFFFFFFF8)):
            with self.subTest(field=field, value=value):
                data = bytearray(good)
                struct.pack_into('<I', data, field, value)
                self.write_binary(data)
                self.rejected()

    def test_malformed_section_offsets_counts_and_symbol_ranges(self):
        good = macho()
        defects = [(0x19, 64, 'I', 2), (0x19, 48, 'Q', 1 << 40),
                   (0x19, 72 + 48, 'I', 0xFFFFFFFF), (0x19, 72 + 40, 'Q', 1 << 40),
                   (2, 8, 'I', 0xFFFFFFFF), (2, 12, 'I', 1)]
        for command, offset, fmt, value in defects:
            with self.subTest(command=command, offset=offset):
                self.write_binary(edit_command(good, command, offset, fmt, value))
                self.rejected()

    def test_build_version_platform_count_tools_and_main_entry_fail_closed(self):
        good = macho()
        for data in (edit_command(good, 0x32, 20, 'I', 1),
                     macho(extra=[struct.pack('<6I', 0x32, 24, 2, 15 << 16, 27 << 16, 0)]),
                     edit_command(good, 0x32, 0, 'I', 0x1B),
                     edit_command(good, 0x80000028, 8, 'Q', 0),
                     edit_command(good, 0x80000028, 8, 'Q', 1 << 40)):
            self.write_binary(data)
            self.rejected()

    def test_missing_text_code_section_and_unknown_file_types(self):
        data = bytearray(macho())
        location = data.find(b'__text')
        data[location:location + 6] = b'__data'
        self.write_binary(data)
        self.rejected('missing_mach_o_code')
        self.write_binary(macho(filetype=1))
        self.rejected('unsupported_mach_o')
        self.write_binary(macho(filetype=6))
        self.rejected('mach_o_file_type')

    def test_encrypted_and_out_of_bounds_linkedit_cannot_hide_markers(self):
        encryption = struct.pack('<6I', 0x2C, 24, 0, 0, 1, 0)
        self.write_binary(macho(extra=[encryption]))
        self.rejected('encrypted_mach_o')
        linkedit = struct.pack('<4I', 0x80000033, 16, 0xFFFFFFFF, 10)
        self.write_binary(macho(extra=[linkedit]))
        self.rejected('mach_o_range')

    def test_malformed_dylib_string_offsets_termination_padding_and_length(self):
        good = macho()
        cases = [edit_command(good, 0xC, 8, 'I', 0), edit_command(good, 0xC, 8, 'I', 0xFFFFFFFF)]
        for data in cases:
            self.write_binary(data)
            self.rejected('malformed_dylib_command')
        self.write_binary(macho(extra=[dylib_command('x' * 1025)]))
        self.rejected('malformed_dylib_command')
        unterminated = struct.pack('<6I', 0xC, 32, 24, 0, 0, 0) + b'XXXXXXXX'
        self.write_binary(macho(extra=[unterminated]))
        self.rejected('malformed_dylib_command')
        nonzero_padding = struct.pack('<6I', 0xC, 32, 24, 0, 0, 0) + b'x\0y\0\0\0\0\0'
        self.write_binary(macho(extra=[nonzero_padding]))
        self.rejected('malformed_dylib_command')

    def test_fat_all_slices_watch_and_stripped_helpers_are_rejected(self):
        for hidden in (macho(platform=4, subtype=2), macho(subtype=2, markers=b'QRWatchSessionGate')):
            self.write_binary(fat([macho(), hidden]))
            self.rejected()

    def test_fat_slice_limit_truncation_overlap_identity_and_range(self):
        good = fat([macho(), macho(subtype=2)])
        self.write_binary(good)
        self.rejected('fat_slice_limit', limits=replace(gate.DEFAULT_LIMITS, slices=1))
        for end in (4, 7, 20, len(good) - 1):
            self.write_binary(good[:end])
            self.rejected()
        for field, value in ((8, X86_64), (16, 0), (20, 0xFFFFFFFF), (24, 32), (36, 48)):
            with self.subTest(field=field):
                data = bytearray(good)
                struct.pack_into('>I', data, field, value)
                self.write_binary(data)
                self.rejected()
        self.write_binary(fat([macho(), macho()]))
        self.rejected('duplicate_fat_slice')
        data = bytearray(fat([macho()], wide=True))
        struct.pack_into('>I', data, 36, 1)
        self.write_binary(data)
        self.rejected('malformed_fat_slice')

    def test_binary_and_section_count_limits(self):
        self.framework()
        self.rejected('binary_limit', limits=replace(gate.DEFAULT_LIMITS, binaries=1))
        self.rejected('load_command_limit', limits=replace(gate.DEFAULT_LIMITS, load_commands=1))
        self.rejected('load_command_limit', limits=replace(gate.DEFAULT_LIMITS, load_command_bytes=16))

    def cli(self, *args, optimized=False):
        command = [sys.executable] + (['-O'] if optimized else []) + [str(SCRIPT), str(self.app)] + list(args)
        result = subprocess.run(command, text=True, capture_output=True, timeout=10)
        self.assertLessEqual(len(result.stdout.encode()), gate.DEFAULT_LIMITS.report_bytes)
        self.assertNotIn('Traceback', result.stderr)
        return result, json.loads(result.stdout)

    def test_cli_json_success_and_atomic_report_in_normal_and_optimized_python(self):
        for optimized in (False, True):
            output = self.base / ('report-O.json' if optimized else 'report.json')
            result, report = self.cli('--output', str(output), optimized=optimized)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_bytes()), report)
            self.assertEqual(report['status'], 'pass')
        self.assertEqual(list(self.base.glob('.ios-release-*')), [])

    def test_cli_closed_fail_json_under_python_O_and_stale_evidence_replaced(self):
        output = self.base / 'report.json'
        output.write_text('{"status":"pass"}')
        defects = (macho(platform=4), macho(markers=b'QRWatchPhoneService'),
                   macho(markers=b'-mini-startup-observation-v1'), macho()[:31], fat([macho(), macho(platform=9, subtype=2)]))
        for data in defects:
            self.write_binary(data)
            for optimized in (False, True):
                result, report = self.cli('--output', str(output), optimized=optimized)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(report['status'], 'fail')
                self.assertEqual(json.loads(output.read_bytes())['status'], 'fail')

    def test_cli_rejects_inside_package_symbolic_or_absent_output_parent(self):
        outside = self.base / 'outside.json'
        outside.write_text('ordinary')
        symbolic = self.base / 'symbolic.json'
        symbolic.symlink_to(outside)
        for output in (self.app / 'report.json', symbolic, self.base / 'missing/report.json'):
            result, report = self.cli('--output', str(output), optimized=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['status'], 'fail')
        self.assertFalse((self.app / 'report.json').exists())
        self.assertEqual(outside.read_text(), 'ordinary')

    def test_cli_debug_simulator_configuration_is_explicit(self):
        self.simulator()
        self.debug()
        self.write_binary(macho(platform=7, markers=b'-ui-testing'))
        result, report = self.cli('--platform', 'simulator', '--configuration', 'Debug', optimized=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report['configuration'], 'Debug')
        result, report = self.cli('--platform', 'simulator', optimized=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['reason'], 'release_diagnostics')

    def test_cli_malformed_xml_yields_bounded_json_instead_of_traceback(self):
        (self.app / 'Info.plist').write_bytes(b'<plist><dict>')
        result, report = self.cli(optimized=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['reason'], 'malformed_plist')

    def test_retained_privacy_manifest_matches_source_and_rejects_changed_semantics(self):
        source = plistlib.loads((ROOT / 'QRCatcher/PrivacyInfo.xcprivacy').read_bytes())
        self.assertEqual(gate.EXPECTED_PRIVACY, source)
        manifest = self.app / 'PrivacyInfo.xcprivacy'
        for key, value in (('NSPrivacyTracking', True), ('NSPrivacyTrackingDomains', ['example.com']),
                           ('NSPrivacyCollectedDataTypes', [{}]), ('NSPrivacyAccessedAPITypes', [])):
            manifest.write_bytes(plistlib.dumps(dict(source, **{key: value})))
            self.rejected('privacy_manifest')
        manifest.unlink()
        self.rejected('privacy_manifest')

    def test_icons_assets_camera_and_release_file_sharing_are_preserved(self):
        original = self.info.copy()
        for key, value in (('NSCameraUsageDescription', 'changed'), ('CFBundleIcons', {}),
                           ('CFBundleIcons~ipad', {}), ('UIFileSharingEnabled', False),
                           ('LSSupportsOpeningDocumentsInPlace', True)):
            self.info = dict(original, **{key: value})
            self.write_info()
            self.rejected()
        self.info = original
        self.write_info()
        (self.app / 'Assets.car').write_bytes(b'')
        self.rejected('missing_compiled_assets')
        (self.app / 'Assets.car').unlink()
        self.rejected('missing_compiled_assets')

    def test_webkit_app_bound_domains_are_not_watch_metadata(self):
        self.info['WKAppBoundDomains'] = ['example.com']
        self.write_info()
        self.assertEqual(gate.verify_package(self.app)['status'], 'pass')

    def test_debug_file_sharing_contract_and_unsigned_evidence_are_explicit(self):
        self.rejected('bundle_file_sharing', configuration='Debug')
        self.debug()
        report = gate.verify_package(self.app, configuration='Debug')
        self.assertTrue(report['signing'].startswith('UNKNOWN'))
        self.assertTrue(report['entitlements'].startswith('UNKNOWN'))

    def test_missing_native_fd_capabilities_fail_explicitly(self):
        with patch.object(os, 'supports_fd', set()):
            self.rejected('unsupported_filesystem_capabilities')

    def test_debug_dynamic_detection_name_is_exact_and_limited_to_known_images(self):
        self.simulator()
        self.debug()
        options = {'platform': 'simulator', 'configuration': 'Debug'}
        for encoding in ('ascii', 'utf-16-le', 'utf-16-be'):
            marker = ('XCTestCase\0').encode(encoding)
            self.write_binary(macho(platform=7, markers=marker))
            for name in ('QRCatcher.debug.dylib', '__preview.dylib'):
                (self.app / name).write_bytes(macho(platform=7, filetype=6, markers=marker))
            report = gate.verify_package(self.app, **options)
            self.assertIs(report['safe_inventory_complete'], True)
            self.assertEqual(report['findings'], [])
            self.assertIs(report['findings_complete'], True)
            for token in ('OtherXCTestCase\0', 'XCTestCaseOther\0', 'XCTestCase/Dependency\0',
                          'path/XCTestCase\0', 'NS.XCTestCase\0', ' XCTestCase\0', 'XCTestCase\0OtherXCTestCase\0'):
                self.write_binary(macho(platform=7, markers=token.encode(encoding)))
                self.rejected('release_diagnostics', **options)
            self.write_binary(macho(platform=7, markers=marker))
            resource = self.app / 'ordinary-resource'
            resource.write_bytes(marker)
            self.rejected('release_diagnostics', **options)
            resource.unlink()
        (self.app / 'ordinary.plist').write_bytes(plistlib.dumps({'Detection': 'XCTestCase'}))
        self.rejected('release_diagnostics', **options)

    def test_debug_detection_name_does_not_waive_real_test_links_or_scope(self):
        options = self.hosted()
        self.write_binary(macho(platform=7, markers=b'XCTestCase\0', extra=[
            dylib_command('/Developer/Library/Frameworks/xCtEsT.framework/xCtEsT')]))
        error = self.rejected('shipping_test_dependency', **options)
        self.assertIs(error.package_diagnostics['safe_inventory_complete'], True)
        self.write_binary(macho(platform=4, markers=b'XCTestCase\0QRWatchPhoneService\0'))
        error = self.rejected('watch_presence', **options)
        self.assertIn('mach_o_platform', {item['code'] for item in error.package_diagnostics['findings']})
        self.write_binary(macho(platform=7, markers=b'XCTestCase\0'))
        self.rejected('release_test_bundle', platform='simulator', configuration='Debug')
        error = self.rejected('xctestrun_scope', **dict(options, configuration='Release'))
        self.assertIs(error.package_diagnostics['safe_inventory_complete'], False)

    def test_combined_owned_defects_keep_all_independent_gates_without_second_reads(self):
        options = self.hosted()
        self.symbols()
        self.info['UIDeviceFamily'] = [3]
        self.info['NSCameraUsageDescription'] = 'private disclosure sentinel'
        self.write_info()
        self.write_binary(macho(platform=4, markers=b'XCTestCase\0QRWatchPhoneService\0', extra=[
            dylib_command('/Developer/Library/Frameworks/xCtEsT.framework/xCtEsT')]))
        (self.app / 'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps({'Unrelated': 'private value sentinel'}))
        with patch.object(gate, 'read_regular', wraps=gate.read_regular) as reader:
            error = self.rejected('watch_presence', **options)
        receipt = error.package_diagnostics
        self.assertIs(receipt['safe_inventory_complete'], True)
        self.assertIs(receipt['findings_complete'], True)
        self.assertEqual(receipt['findings_omitted'], 0)
        self.assertEqual(receipt['package'], str(self.app))
        self.assertEqual(receipt['app'], str(self.app))
        self.assertEqual(receipt['platform'], 'simulator')
        self.assertEqual(receipt['configuration'], 'Debug')
        self.assertEqual(receipt['qualification'], 'unqualified')
        codes = {item['code'] for item in receipt['findings']}
        self.assertTrue({'watch_presence', 'bundle_device_families', 'bundle_camera_usage', 'privacy_manifest',
                         'nested_bundle_device_families', 'mach_o_platform', 'shipping_test_dependency'} <= codes)
        self.assertEqual(receipt['findings'][0]['code'], error.code)
        labels = [call.args[3] for call in reader.call_args_list]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(error.symbol_observations['qualification'], 'unqualified')
        self.assertEqual(error.symbol_observations['mach_o'][0]['slices'][0]['uuid'], TEST_UUID.hex())
        serialized = json.dumps(receipt['findings'])
        for sentinel in ('private disclosure sentinel', 'private value sentinel', 'QRWatchPhoneService',
                         'XCTestCase', str(self.base), '/Developer/Library'):
            self.assertNotIn(sentinel, serialized)
        self.assertTrue(all(set(item) == {'code', 'stage', 'scope'} and not Path(item['scope']).is_absolute()
                            for item in receipt['findings']))

    def test_malformed_owned_files_block_dependencies_but_keep_independent_owned_findings(self):
        (self.app / 'A-broken.plist').write_bytes(b'<plist><dict>')
        self.write_binary(macho()[:31])
        framework = self.framework(data=macho(platform=4, filetype=6))
        (self.app / 'z-watch.plist').write_bytes(plistlib.dumps({'WKWatchKitApp': False}))
        with patch.object(gate, 'read_regular', wraps=gate.read_regular) as reader:
            error = self.rejected('malformed_plist')
        receipt = error.package_diagnostics
        self.assertIs(receipt['safe_inventory_complete'], True)
        self.assertIs(receipt['findings_complete'], False)
        self.assertEqual(receipt['findings_omitted'], 0)
        self.assertTrue({'malformed_plist', 'truncated_mach_o', 'watch_plist_key', 'missing_shipping_mach_o',
                         'mach_o_platform', 'dependent_checks_unknown'} <= {item['code'] for item in receipt['findings']})
        self.assertTrue(any(item['code'] == 'dependent_checks_unknown' and item['scope'] == 'QRCatcher'
                            for item in receipt['findings']))
        self.assertTrue(any(item['code'] == 'mach_o_platform' and item['scope'] == str((framework / 'Ordinary').relative_to(self.app))
                            for item in receipt['findings']))
        labels = [call.args[3] for call in reader.call_args_list]
        self.assertEqual(len(labels), len(set(labels)))

    def test_bad_main_metadata_keeps_input_identity_and_independent_image_gates_in_cli(self):
        (self.app / 'Info.plist').write_bytes(b'<plist><dict>')
        self.write_binary(macho(platform=4, extra=[
            dylib_command('/Developer/Library/Frameworks/xCtEsT.framework/xCtEsT')]))
        for optimized in (False, True):
            result, report = self.cli(optimized=optimized)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['reason'], 'malformed_plist')
            self.assertEqual(report['package'], str(self.app))
            self.assertEqual(report['app'], str(self.app))
            self.assertEqual(report['qualification'], 'unqualified')
            self.assertIs(report['safe_inventory_complete'], True)
            self.assertIs(report['findings_complete'], False)
            self.assertTrue({'missing_bundle_info', 'dependent_checks_unknown', 'mach_o_platform', 'shipping_test_dependency'}
                            <= {item['code'] for item in report['findings']})
            self.assertNotIn('bundle_id', report)

    def test_findings_scope_never_comes_from_unowned_executable_metadata(self):
        framework = self.framework()
        sentinel = 'private-executable-sentinel-' + 'x' * 2048
        (framework / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': sentinel}))
        error = self.rejected('orphan_bundle_executable')
        findings = error.package_diagnostics['findings']
        self.assertNotIn(sentinel, json.dumps(findings))
        self.assertTrue(all(len(item['scope'].encode()) <= gate.DEFAULT_LIMITS.path_bytes for item in findings))
        self.assertTrue(any(item['code'] == 'orphan_bundle_executable' and item['scope'] == 'Frameworks/Ordinary.framework'
                            for item in findings))
        self.assertIs(error.package_diagnostics['findings_complete'], False)

    def test_multiple_symbol_and_relocation_bindings_fail_independently_without_leakage(self):
        options = self.hosted()
        self.write_test_binary(extra=[dylib_command('/System/Library/Frameworks/WatchConnectivity.framework/WatchConnectivity'),
                                     uuid_command(), target_triple_command()])
        self.symbols(symbol_macho(uuid=bytes(range(17, 33)), extra=[target_triple_command('arm64-apple-ios18.0.0-simulator')]))
        self.symbol_info['CFBundlePackageType'] = 'OTHER'
        self.write_symbol_info()
        row = "{ offset: 0x8, size: 0x3, addend: 0x0, symName: 'private symbol sentinel', symBinAddr: 0x100000000, symSize: 0x10 }"
        self.relocations(data=self.relocation_yaml(triple='arm64-apple-watchos', binary_path='/private/foreign/sentinel', records=(row,)))
        with patch.object(gate, 'read_regular', wraps=gate.read_regular) as reader:
            error = self.rejected('test_relocation_binary_path', **options)
        receipt = error.package_diagnostics
        self.assertIs(receipt['safe_inventory_complete'], True)
        self.assertIs(receipt['findings_complete'], False)
        self.assertTrue({'test_relocation_binary_path', 'test_relocation_platform', 'test_relocation_size',
                         'test_symbol_metadata', 'test_symbol_uuid', 'test_symbol_target_triple',
                         'dependent_checks_unknown'} <= {item['code'] for item in receipt['findings']})
        labels = [call.args[3] for call in reader.call_args_list]
        self.assertEqual(len(labels), len(set(labels)))
        encoded = json.dumps(receipt['findings']) + json.dumps(error.symbol_observations)
        self.assertNotIn('private symbol sentinel', encoded)
        self.assertNotIn('/private/foreign/sentinel', encoded)
        self.assertNotIn(str(self.base), encoded)

    def test_structural_uncertainty_stops_after_existing_findings_and_never_reads_later_files(self):
        (self.app / 'A-marker').write_bytes(b'QRWatchPhoneService')
        unsafe = self.app / 'Z-unsafe'
        later = self.app / 'ZZ-never-read'
        later.write_bytes(b'XCTestObservation')
        for kind, code in (('symlink', 'symlink'), ('hardlink', 'hardlinked_file'), ('fifo', 'unsupported_file_type')):
            with self.subTest(kind=kind):
                if kind == 'symlink':
                    unsafe.symlink_to(self.base / 'unowned-private-target')
                elif kind == 'hardlink':
                    os.link(self.app / 'Assets.car', unsafe)
                else:
                    os.mkfifo(unsafe)
                with patch.object(gate, 'read_regular', wraps=gate.read_regular) as reader:
                    error = self.rejected('watch_presence')
                receipt = error.package_diagnostics
                self.assertIs(receipt['safe_inventory_complete'], False)
                self.assertIs(receipt['findings_complete'], False)
                self.assertIn(code, {item['code'] for item in receipt['findings']})
                self.assertNotIn(later.name, [call.args[3] for call in reader.call_args_list])
                unsafe.unlink()

    def test_inventory_and_parser_budgets_still_stop_cumulative_inspection(self):
        (self.app / 'A-marker').write_bytes(b'QRWatchPhoneService')
        (self.app / 'ZZ-never-read').write_bytes(b'XCTestObservation')
        cases = (replace(gate.DEFAULT_LIMITS, total_bytes=20),
                 replace(gate.DEFAULT_LIMITS, binaries=1),
                 replace(gate.DEFAULT_LIMITS, plist_nodes=2),
                 replace(gate.DEFAULT_LIMITS, load_commands=1))
        self.framework()
        for limits in cases:
            with self.subTest(limits=limits):
                with patch.object(gate, 'read_regular', wraps=gate.read_regular) as reader:
                    error = self.rejected('watch_presence', limits=limits)
                self.assertIs(error.package_diagnostics['safe_inventory_complete'], False)
                self.assertIs(error.package_diagnostics['findings_complete'], False)
                self.assertTrue(any(item['code'].endswith('_limit') for item in error.package_diagnostics['findings']))
                self.assertNotIn('ZZ-never-read', [call.args[3] for call in reader.call_args_list])

    def test_findings_saturation_is_bounded_explicit_and_cannot_pass(self):
        for index in range(70):
            (self.app / ('diagnostic-%03d' % index)).write_bytes(b'QRWatchPhoneService')
        with patch.object(gate, 'read_regular', wraps=gate.read_regular) as reader:
            error = self.rejected('watch_presence')
        receipt = error.package_diagnostics
        self.assertIs(receipt['safe_inventory_complete'], True)
        self.assertIs(receipt['findings_complete'], False)
        self.assertEqual(len(receipt['findings']), 64)
        self.assertEqual(receipt['findings_omitted'], 6)
        self.assertEqual(len(reader.call_args_list), 74)
        error = self.rejected('watch_presence', limits=replace(gate.DEFAULT_LIMITS, findings=2))
        self.assertEqual(len(error.package_diagnostics['findings']), 2)
        self.assertEqual(error.package_diagnostics['findings_omitted'], 68)
        error = self.rejected('watch_presence', limits=replace(gate.DEFAULT_LIMITS, report_bytes=2048))
        self.assertGreater(error.package_diagnostics['findings_omitted'], 6)
        summary = json.dumps({'findings': error.package_diagnostics['findings']}, sort_keys=True, indent=2).encode()
        self.assertLessEqual(len(summary), 1024)

    def test_invalid_findings_caps_and_nonfinite_report_data_fail_with_closed_receipts(self):
        for cap in (0, -1, True, 'unbounded'):
            with self.subTest(cap=cap):
                error = self.rejected('invalid_limits', limits=replace(gate.DEFAULT_LIMITS, findings=cap))
                self.assertIs(error.package_diagnostics['safe_inventory_complete'], False)
        for budget in (0, -1, True, 'unbounded'):
            with self.subTest(report_bytes=budget):
                error = self.rejected('invalid_limits', limits=replace(gate.DEFAULT_LIMITS, report_bytes=budget))
                self.assertIs(error.package_diagnostics['safe_inventory_complete'], False)
        self.info['CFBundleIcons']['Unrelated'] = float('nan')
        self.write_info()
        for optimized in (False, True):
            result, report = self.cli(optimized=optimized)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['reason'], 'report_encoding_error')
            self.assertIs(report['safe_inventory_complete'], False)
            self.assertIs(report['findings_complete'], False)

    def test_archive_semantic_failure_reads_each_owned_file_once_and_keeps_app_failures(self):
        self.write_binary(macho(platform=4, markers=b'QRWatchPhoneService'))
        archive = self.archive()
        (archive / 'Info.plist').write_bytes(plistlib.dumps({'ApplicationProperties': {
            'ApplicationPath': 'Applications/Foreign.app', 'CFBundleIdentifier': 'foreign'}}))
        with patch.object(gate, 'read_regular', wraps=gate.read_regular) as reader:
            with self.assertRaises(gate.ValidationError) as raised:
                gate.verify_package(archive)
        receipt = raised.exception.package_diagnostics
        self.assertIs(receipt['safe_inventory_complete'], True)
        self.assertEqual(receipt['package'], str(archive))
        self.assertEqual(receipt['app'], str(self.app))
        self.assertTrue({'watch_presence', 'mach_o_platform', 'archive_identity'} <= {item['code'] for item in receipt['findings']})
        self.assertEqual(sum(call.args[3] == 'Info.plist' for call in reader.call_args_list), 2)
        self.assertEqual(len(reader.call_args_list), 5)

    def test_cumulative_cli_receipts_and_unknown_dependencies_remain_closed_under_optimization(self):
        self.info['UIDeviceFamily'] = [3]
        self.write_info()
        self.write_binary(macho(platform=4, markers=b'QRWatchPhoneService', extra=[
            dylib_command('/Developer/Library/Frameworks/xCtEsT.framework/xCtEsT')]))
        for optimized in (False, True):
            with self.subTest(optimized=optimized):
                result, report = self.cli(optimized=optimized)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(report['status'], 'fail')
                self.assertEqual(report['reason'], report['findings'][0]['code'])
                self.assertIs(report['safe_inventory_complete'], True)
                self.assertEqual(report['package'], str(self.app))
                self.assertEqual(report['app'], str(self.app))
                self.assertEqual(report['configuration'], 'Release')
                self.assertEqual(report['platform'], 'device')
                self.assertIs(report['findings_complete'], True)
                self.assertTrue({'watch_presence', 'bundle_device_families', 'mach_o_platform', 'shipping_test_dependency'}
                                <= {item['code'] for item in report['findings']})
        self.write_binary(macho()[:31])
        for optimized in (False, True):
            result, report = self.cli(optimized=optimized)
            self.assertEqual(result.returncode, 1)
            self.assertIs(report['safe_inventory_complete'], True)
            self.assertIs(report['findings_complete'], False)
            self.assertIn('dependent_checks_unknown', {item['code'] for item in report['findings']})


if __name__ == '__main__':
    unittest.main()
