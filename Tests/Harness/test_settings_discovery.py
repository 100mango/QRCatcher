"""Control-flow fixtures only; no claim about installed Settings UI or Apple build."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import discover_native_settings as discovery
from test_settings_navigation import navigation_fixture

DEVICE = '11111111-2222-4333-8444-555555555555'
SOURCE = 'a' * 40
SETTINGS = 'com.apple.SyntheticSettingsFixture'
CATALOG = {SETTINGS: {'CFBundleIdentifier': SETTINGS, 'CFBundleDisplayName': 'Settings', 'CFBundleName': 'Fixture', 'ApplicationType': 'System'}}


class SettingsDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'build/WatchTests').mkdir(parents=True)
        (self.root / 'QRCatcher.xcodeproj').mkdir()
        self.env = {'GITHUB_REPOSITORY': '100mango/QRCatcher', 'GITHUB_SHA': SOURCE, 'GITHUB_WORKFLOW_SHA': SOURCE,
                    'EVIDENCE_SCOPE': 'watchos', 'WATCH_SIMULATOR_ID': DEVICE, 'GITHUB_WORKSPACE': str(self.root)}

    def test_requires_exact_source_scope_device_and_no_trait_override(self):
        self.assertEqual(discovery.validate_identity('watch', DEVICE, self.env, self.root)['device'], DEVICE)
        for key, value in [('GITHUB_SHA', 'invalid'), ('GITHUB_WORKFLOW_SHA', 'b' * 40), ('EVIDENCE_SCOPE', 'watchos_40'),
                           ('WATCH_SIMULATOR_ID', '99999999-2222-4333-8444-555555555555'), ('GITHUB_REPOSITORY', 'elsewhere/repo'),
                           ('GITHUB_WORKSPACE', ''), ('GITHUB_WORKSPACE', str(self.root / 'wrong')), ('TEST_RUNNER_QRCATCHER_WATCH_LAYOUT_STRESS', 'accessibility5')]:
            with self.subTest(key=key), self.assertRaises(discovery.DiscoveryStopped):
                discovery.validate_identity('watch', DEVICE, dict(self.env, **{key: value}), self.root)

    def test_settings_identity_is_observed_unique_native_metadata(self):
        item, _ = discovery.select_settings(CATALOG)
        self.assertEqual(item['CFBundleIdentifier'], SETTINGS)
        variants = [{}, {SETTINGS: dict(CATALOG[SETTINGS], ApplicationType='User')},
                    {SETTINGS: dict(CATALOG[SETTINGS], CFBundleDisplayName='Unknown', CFBundleName='Unknown')},
                    {SETTINGS: dict(CATALOG[SETTINGS], CFBundleIdentifier='com.apple.Wrong')},
                    dict(CATALOG, **{'com.apple.Other': dict(CATALOG[SETTINGS], CFBundleIdentifier='com.apple.Other')})]
        for catalog in variants:
            with self.subTest(catalog=catalog), self.assertRaises(discovery.DiscoveryStopped):
                discovery.select_settings(catalog)

    def test_device_must_be_exact_booted_available_correct_runtime(self):
        identity = discovery.validate_identity('watch', DEVICE, self.env, self.root)
        row = {'udid': DEVICE, 'state': 'Booted', 'isAvailable': True}
        runtime = 'com.apple.CoreSimulator.SimRuntime.watchOS-27-0'
        self.assertEqual(discovery.select_device({'devices': {runtime: [row]}}, identity), runtime)
        for data in [{'devices': {runtime: [dict(row, state='Shutdown')]}}, {'devices': {runtime: [row, row]}},
                     {'devices': {runtime: [dict(row, isAvailable=False)]}}, {'devices': {'wrong-runtime': [row]}}, {'devices': {runtime: [dict(row, udid=None)]}}]:
            with self.assertRaises(discovery.DiscoveryStopped): discovery.select_device(data, identity)

    def exercise(self, mode='ok'):
        calls = []
        def runner(args, seconds, **options):
            calls.append((args, seconds))
            self.assertLessEqual(seconds, 90)
            op = dict(command=args, cleanup_confirmed=True, exit=0, state='completed', elapsed_seconds=0.01)
            if args == ['git', 'rev-parse', 'HEAD']: text = SOURCE
            elif args == ['git', 'diff', '--quiet', 'HEAD', '--']: text = ''
            elif args == ['xcrun', 'simctl', 'help', 'listapps']:
                text = 'Usage: simctl listapps <device>\n' if mode != 'unknown_help' else 'Unrecognized command'
            elif args == ['xcrun', 'simctl', 'list', 'devices', '-j']:
                text = json.dumps({'devices': {'com.apple.CoreSimulator.SimRuntime.watchOS-27-0': [{'udid': DEVICE, 'state': 'Booted', 'isAvailable': True}]}})
            elif args == ['xcrun', 'simctl', 'listapps', DEVICE]:
                text = 'synthetic OpenStep plist; conversion is a tool double'
                if mode == 'cleanup_unknown': return 124, text, dict(op, cleanup_confirmed=False, exit=124)
            elif args[:3] == ['plutil', '-convert', 'json']:
                Path(args[4]).write_text(json.dumps(CATALOG if mode != 'missing_settings' else {})); text = ''
            elif args[0] == 'env':
                token = json.loads(args[1].split('=', 1)[1]); receipt = dict(token, status='settings_screen_observed', original_value_restorable=False, setting_write_authorized=False,
                    hierarchy='Synthetic control-flow fixture, not observed UI', controls=[{'type': 1, 'identifier': 'fixture', 'label': 'Settings', 'value': ''}], screenshot_attached=True)
                receipt.update(navigation_fixture('watch'))
                if mode == 'wrong_receipt': receipt['device'] = 'wrong'
                if mode == 'write_claim': receipt['setting_change_attempted'] = True
                if mode == 'restorable_claim': receipt['original_value_restorable'] = True
                if mode == 'write_authorized': receipt['setting_write_authorized'] = True
                if mode == 'missing_controls': receipt.pop('controls')
                if mode == 'missing_screenshot': receipt['screenshot_attached'] = False
                if mode == 'binary_claim': receipt['binary_source_binding_verified'] = True
                text = discovery.TOKEN_PREFIX + json.dumps(receipt)
                if mode == 'missing_receipt': text = 'no receipt'
                if mode == 'nonzero_ui': return 65, text, dict(op, exit=65)
            else: self.fail('Unexpected command: ' + repr(args))
            return 0, text, op
        old = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, self.env, clear=True), patch.object(discovery, 'blocked', return_value=False), patch.object(discovery, 'verify_build', return_value={'synthetic_fixture': True}), patch.object(discovery, 'mark_unconfirmed') as mark:
                report = discovery.discover('watch', DEVICE, runner=runner)
                self.assertEqual(mark.called, mode == 'cleanup_unknown')
        finally: os.chdir(old)
        self.assertFalse(report['setting_change_attempted'])
        self.assertFalse(report['system_propagation_qualified'])
        self.assertFalse(report['original_value_restorable'])
        self.assertFalse(report['setting_write_authorized'])
        return report, calls

    def test_readonly_discovery_never_sets_or_qualifies(self):
        report, calls = self.exercise()
        self.assertEqual(report['status'], 'read_only_discovery_complete_unqualified')
        self.assertEqual(len(calls), 7)
        self.assertEqual(len([c for c, _ in calls if c[0] == 'env']), 1)
        self.assertFalse(any('content_size' in c or 'defaults' in c or 'privacy' in c or 'install' in c for c, _ in calls))
        ui = calls[-1][0]
        self.assertIn('-only-testing:QRCatcherWatchUITests/QRCatcherWatchSettingsDiscovery/testReadOnlyTextSizeSettingsDiscovery', ui)
        self.assertIn('60', ui)

    def test_unrecognized_help_does_not_access_device_or_ui(self):
        report, calls = self.exercise('unknown_help')
        self.assertEqual(len(calls), 3); self.assertIn('stopped', report['status'])

    def test_missing_settings_identity_never_launches_guessed_app(self):
        report, calls = self.exercise('missing_settings')
        self.assertEqual(len(calls), 6); self.assertIn('stopped', report['status'])
        self.assertTrue((self.root / 'build/settings-discovery-watch/system-app-metadata.json').exists())

    def test_unknown_cleanup_prevents_all_later_commands(self):
        report, calls = self.exercise('cleanup_unknown')
        self.assertTrue(report['cleanup_unconfirmed']); self.assertEqual(len(calls), 5)

    def test_forged_or_missing_receipt_and_nonzero_ui_cannot_qualify(self):
        for mode in ['wrong_receipt', 'write_claim', 'missing_receipt', 'nonzero_ui', 'restorable_claim', 'write_authorized', 'missing_controls', 'missing_screenshot', 'binary_claim']:
            with self.subTest(mode=mode):
                # Each fixture is an independent disposable root, never a retry.
                prior = self.root
                self.root = prior / mode; (self.root / 'build/WatchTests').mkdir(parents=True); (self.root / 'QRCatcher.xcodeproj').mkdir()
                self.env['GITHUB_WORKSPACE'] = str(self.root)
                report, _ = self.exercise(mode); self.assertIn('stopped', report['status'])
                self.root = prior

    def test_standalone_entry_refuses_before_any_external_command(self):
        with self.assertRaisesRegex(discovery.DiscoveryStopped, 'Standalone'):
            discovery.discover('watch', DEVICE)

    def test_repeated_invocation_refuses_before_another_command(self):
        self.exercise()
        old = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, self.env, clear=True), self.assertRaises(discovery.DiscoveryStopped):
                discovery.discover('watch', DEVICE, runner=lambda *args, **kwargs: self.fail('No retry command permitted'))
        finally: os.chdir(old)

    def test_swift_diagnostic_has_no_size_setter_and_ordinary_watch_skips_it(self):
        for label in ['Watch', 'TV']:
            text = (ROOT / f'QRCatcher{label}UITests/QRCatcher{label}UITests.swift').read_text().split(f'final class QRCatcher{label}SettingsDiscovery')[1]
            for forbidden in ['adjust(toNormalizedSliderPosition', 'rotateDigitalCrown', 'press(.left)', 'press(.right)', 'QRCATCHER_WATCH_LAYOUT_STRESS=', '.swipeUp()']:
                self.assertNotIn(forbidden, text)
            self.assertIn('QRStopForUnexpectedInterruption', text)
            self.assertIn('"original_value_restorable": false', text)
        script = (ROOT / 'scripts/run_watch_platform_tests.py').read_text()
        self.assertIn('-skip-testing:QRCatcherWatchUITests/QRCatcherWatchSettingsDiscovery', script)
        workflow = (ROOT / '.github/workflows/apple-platforms.yml').read_text()
        self.assertNotIn('discover_native_settings.py', workflow)

if __name__ == '__main__': unittest.main()
