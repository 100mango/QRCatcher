"""Synthetic package evidence only: no Apple build/runtime/signing proof.

Run both:
  python3 Tests/Harness/test_ios_only_release_package.py
  python3 -O Tests/Harness/test_ios_only_release_package.py
All admission checks and unittest assertion methods stay active under -O.
The byte builders use Apple's public layouts, without mocking native tools.
"""

from dataclasses import replace
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

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/verify_ios_only_release.py'
SPEC = importlib.util.spec_from_file_location('ios_only_package', SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)
ARM64 = 0x0100000C
X86_64 = 0x01000007


def dylib_command(name, command=0xC, endian='<'):
    encoded = name.encode('utf-8') + b'\0'
    size = (24 + len(encoded) + 7) & ~7
    return struct.pack(endian + '6I', command, size, 24, 0, 0x10000, 0x10000) + encoded.ljust(size - 24, b'\0')


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


class IOSOnlyPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
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
                              dylib_command('/Developer/Library/Frameworks/XCTest.framework/XCTest')]}
        settings.update(changes)
        (self.test_bundle / 'QRCatcherTests').write_bytes(macho(**settings))

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
        with self.assertRaises(OSError):
            gate.verify_package(self.app, **dict(options, xctestrun=self.xctestrun.with_name('missing.xctestrun')))
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

    def test_hosted_test_bundles_outside_shipping_app_are_permitted(self):
        archive = self.archive()
        tests = archive / 'Products/Tests/Hosted.xctest'
        tests.mkdir(parents=True)
        (tests / 'Hosted').write_bytes(macho(markers=b'QRWatchPhoneService\0WatchConnectivity\0-ui-testing'))
        (archive / 'dSYMs').mkdir()
        (archive / 'dSYMs/other').write_bytes(b'QRWatchSessionGate')
        self.assertEqual(gate.verify_package(archive)['status'], 'pass')

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


if __name__ == '__main__':
    unittest.main()
