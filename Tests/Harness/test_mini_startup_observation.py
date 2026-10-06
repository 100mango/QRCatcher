"""Portable startup observation contracts, never Apple compilation/runtime proof."""
from pathlib import Path
import ctypes
import hashlib
import itertools
import json
import math
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = 'QRCatcher/AppDelegate.m'
PAD_PATH = 'QRCatcherUITests/QRCatcherPadUITests.m'
NATIVE_PATHS = ['QRCatcher/AppDelegate.h', APP_PATH, 'QRCatcher/main.m',
                'QRCatcher/QRCatchViewController.m', PAD_PATH]
PHASES = ['main_entry', 'store_enter', 'store_return', 'watch_enter', 'watch_return',
          'delegate_return', 'fixture_encode_enter', 'fixture_encode_return',
          'fixture_decode_enter', 'fixture_decode_return', 'fixture_handle_save_enter',
          'fixture_handle_save_return', 'main_queue_turn']


def preprocess(text, debug):
    # Exercise a real portable C preprocessor on the actual conditional source;
    # do not fake Apple headers or claim this checks Objective-C compilation.
    text = re.sub(r'^\s*#\s*(?:import|include)[^\n]*', '', text, flags=re.M)
    cc = shutil.which('cc')
    if not cc:
        raise RuntimeError('A standard portable C preprocessor is required')
    result = subprocess.run([cc, '-E', '-P', '-x', 'c', '-DDEBUG=' + str(debug), '-'],
                            input=text, capture_output=True, text=True, check=True)
    return result.stdout


def normalized_digest(text):
    return hashlib.sha256(re.sub(r'\s+', '', text).encode()).hexdigest()


def remove_observation(text, path):
    """Remove only the admitted diagnostic additions, leaving every original statement."""
    if path == APP_PATH:
        text = re.sub(r'\n#if DEBUG\n#import <CoreFoundation/CFDate.h>.*?\n#endif\n',
                      '\n', text, count=1, flags=re.S)
    if path == PAD_PATH:
        text = re.sub(r'#if DEBUG\nstatic int QRPadStartupLogAllowance.*?\n#endif\n',
                      '', text, count=1, flags=re.S)
        text = re.sub(r'#if DEBUG\n// These records use only.*?\n#endif\n',
                      '', text, count=1, flags=re.S)
        text = re.sub(r'^.*startupObservation(?:Slot|RequestID|ReadAttempted|LogBytes).*\n',
                      lambda m: '    [self.app launch];\n' if 'launchPadWithStartupSlot:' in m[0] else '',
                      text, flags=re.M)
        text = text.replace('[self launchPadWithStartupSlot:@"split-reopen"]', '[self.app launch]')
        text = re.sub(r'^.*if \(self.testRun.failureCount > 0\) \[self observeStartupValueOnce\];\n',
                      '', text, flags=re.M)
    text = re.sub(r'^.*QRStartupObservation(?:Begin|Mark|Attach|ScheduleMainQueueTurn)\([^\n]*\n',
                  '', text, flags=re.M)
    text = text.replace('NSString *cameraValue = [NSString stringWithFormat:',
                        'self.statusLabel.accessibilityValue = [NSString stringWithFormat:')
    text = re.sub(r'^.*QRStartupObservationMergeCameraValue\(cameraValue\);\n', '', text, flags=re.M)
    return text


def function_body(text, name):
    found = re.search(r'static int ' + name + r'\([^)]*\)\s*\{[^}]*\}', text, re.S)
    if not found:
        raise ValueError('Missing exact portable policy ' + name)
    return found[0].replace('static int ', 'int ', 1)


def source_contract(app, pad, view, main):
    required_app = ['QRStartupEventLimit = 16;', 'QRStartupByteLimit = 4096;',
                    'phase < 13 && count < 16 && !(seen & (1UL << phase))',
                    'uiCount == 1 && tokenCount == 1 && canonicalUUID && closedSlot && appPID > 0',
                    'QRStartupArgumentCount(args, @"-ui-testing")',
                    'QRStartupArgumentCount(args, @"-mini-startup-observation-v1")',
                    'if (uiCount != 1 || tokenCount != 1) return;',
                    'QRStartupArgumentCount(args, flag) != 1',
                    'index + 1 < args.count',
                    'request && [request.UUIDString isEqualToString:requestID]',
                    'slot && [@[@"largest-initial", @"split-initial", @"split-reopen"] containsObject:slot]',
                    'QRStartupLaunchID = NSUUID.UUID.UUIDString;',
                    '@"app_pid": @(NSProcessInfo.processInfo.processIdentifier)',
                    '@"clock": @"WALL_CF2001"', '@"interval_state": @"UNKNOWN"',
                    '[NSNumber numberWithBool:QRStartupClockUnknown]', '[NSNumber numberWithBool:NO]',
                    'isfinite(wall) ? (id)@(wall) : (id)NSNull.null',
                    'QRStartupClockUnknown = YES;',
                    '[combined lengthOfBytesUsingEncoding:NSUTF8StringEncoding] <= QRStartupByteLimit',
                    'if (!QRStartupEnabled) return cameraValue;',
                    'if (!QRStartupEnabled || QRStartupTurnScheduled) return;',
                    'QRStartupTurnScheduled = YES;']
    required_pad = ['self.startupObservationReadAttempted = YES;',
                    'self.app.staticTexts[@"scan.status"].value',
                    'if (!self.startupObservationRequestID || self.startupObservationReadAttempted) return;',
                    'QRPadStartupLogAllowance(self.startupObservationLogBytes, finalEvent)',
                    '[self logStartupEvent:@"launch_enter" observation:nil]',
                    '[self logStartupEvent:@"launch_return" observation:nil]',
                    '[self logStartupEvent:@"value_read_enter" observation:nil]',
                    '@"UNKNOWN_getter_exception"', '@"UNKNOWN_missing_invalid_or_wrong_launch"',
                    '[parsed[@"request_id"] isEqualToString:self.startupObservationRequestID]',
                    '[parsed[@"slot"] isEqualToString:self.startupObservationSlot]',
                    '[parsed[@"events"] count] <= 16',
                    'self.startupObservationRequestID = NSUUID.UUID.UUIDString;',
                    '@"-mini-startup-observation-v1", @"-mini-startup-launch-id", self.startupObservationRequestID',
                    '@"-mini-startup-slot", slot', '[NSNumber numberWithBool:NO]',
                    'remaining > 384 ? (int)(remaining - 384) : 0',
                    '@"UNKNOWN_log_cap"', '@"startup_record_omitted": [NSNumber numberWithBool:YES]',
                    'record[@"wall"] = NSNull.null;']
    for text, required in [(app, required_app), (pad, required_pad)]:
        for token in required:
            if token not in text:
                raise ValueError('Missing startup contract: ' + token)
    if pad.count('self.app.staticTexts[@"scan.status"].value') != 1:
        raise ValueError('More than one public value getter')
    if pad.index('self.startupObservationReadAttempted = YES;') > pad.index('self.app.staticTexts[@"scan.status"].value'):
        raise ValueError('Read attempt must be claimed before the public getter')
    if 'QRStartupObservationBegin(CFAbsoluteTimeGetCurrent());' not in main:
        raise ValueError('Missing app main-entry wall observation')
    if 'QRStartupObservationMergeCameraValue(cameraValue)' not in view:
        raise ValueError('Existing camera value must be merged')
    observation = app.split('#if DEBUG', 1)[1].split('#endif', 1)[0]
    helper = pad.split('// These records use only', 1)[1].split('#endif', 1)[0]
    for token in ['systemUptime', 'mach_absolute', 'mach_continuous', 'simctl', 'UIPasteboard',
                  'writeTo', 'NSTimer', 'sleep(', 'waitFor', 'performAccessibilityAudit',
                  'NSFileManager', 'environment', 'debugDescription', 'NSLog(']:
        if token in observation:
            raise ValueError('Unadmitted app observation mechanism: ' + token)
    for token in ['simctl', 'UIPasteboard', 'writeTo', 'NSTimer', 'sleep(', 'waitFor',
                  'XCTAssert', 'debugDescription', 'systemUptime', 'XCTAttachment']:
        if token in helper:
            raise ValueError('Unadmitted helper observation mechanism: ' + token)
    return True


class MiniStartupObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {path: (ROOT / path).read_text() for path in NATIVE_PATHS}
        cls.app = cls.sources[APP_PATH]
        cls.pad = cls.sources[PAD_PATH]
        cls.view = cls.sources['QRCatcher/QRCatchViewController.m']
        cls.main = cls.sources['QRCatcher/main.m']
        cls.folder = tempfile.TemporaryDirectory()
        cpath = Path(cls.folder.name) / 'actual-startup-policy.c'
        cpath.write_text('#include <math.h>\n' + '\n'.join(
            function_body(cls.app, name) for name in
            ['QRStartupWallComparable', 'QRStartupCanRecord', 'QRStartupLaunchGate']) + '\n' +
            function_body(cls.pad, 'QRPadStartupLogAllowance'))
        library = Path(cls.folder.name) / 'actual-startup-policy.so'
        subprocess.run(['cc', '-std=c11', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(cpath), '-o', str(library)], check=True, capture_output=True)
        cls.policy = ctypes.CDLL(str(library))
        cls.policy.QRStartupWallComparable.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_int]
        cls.policy.QRStartupCanRecord.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        cls.policy.QRStartupLaunchGate.argtypes = [ctypes.c_ulong, ctypes.c_ulong,
                                                  ctypes.c_int, ctypes.c_int, ctypes.c_int]
        cls.policy.QRPadStartupLogAllowance.argtypes = [ctypes.c_ulong, ctypes.c_int]

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_exact_source_contract(self):
        self.assertTrue(source_contract(self.app, self.pad, self.view, self.main))

    def test_actual_gate_rejects_missing_duplicate_token_nonce_slot_or_pid(self):
        for ui, token, nonce, slot, pid in itertools.product([0, 1, 2], [0, 1, 2],
                                                            [0, 1], [0, 1], [-1, 0, 42]):
            expected = ui == token == 1 and nonce == slot == 1 and pid > 0
            self.assertEqual(bool(self.policy.QRStartupLaunchGate(ui, token, nonce, slot, pid)), expected)

    def test_actual_finite_phase_count_and_duplicate_policy(self):
        for phase in range(18):
            for count in [0, 12, 15, 16, 17]:
                for seen in [0, 1 << phase]:
                    expected = phase < 13 and count < 16 and not (seen & (1 << phase))
                    self.assertEqual(bool(self.policy.QRStartupCanRecord(phase, count, seen)), expected)
        self.assertFalse(self.policy.QRStartupCanRecord(2**63, 0, 0))
        self.assertFalse(self.policy.QRStartupCanRecord(0, 2**63, 0))

    def test_actual_wall_policy_detects_nonfinite_backward_and_missing_previous(self):
        for wall, previous, had, expected in [(10, 9, 1, True), (9, 10, 1, False),
                (10, 10, 1, True), (10, math.nan, 1, False), (10, math.nan, 0, True),
                (math.nan, 9, 1, False), (math.inf, 9, 1, False), (-math.inf, 9, 0, False),
                (10**12, 9, 1, True)]:
            self.assertEqual(bool(self.policy.QRStartupWallComparable(wall, previous, had)), expected)
        # Forward jumps cannot be identified by wall alone. Every interval is
        # deliberately UNKNOWN, including finite apparently ordered snapshots.
        self.assertIn('@"interval_state": @"UNKNOWN"', self.app)
        self.assertIn('@"continuous_responsiveness": [NSNumber numberWithBool:NO]', self.app)

    def test_release_preprocessing_has_no_observer_symbols_and_preserves_original_source(self):
        # Frozen portable preprocessing digests of immutable v5, independent of
        # the candidate. Apple native compilation remains a separate gate.
        expected = {
            'QRCatcher/AppDelegate.h': 'f3c7637015dc7d5aacbf8c75c870a6cc286db3eeb2fd4c013888a3d6d1226cca',
            APP_PATH: '4c03c71acb8be78611c66b11e92b31522a56eaae40a988d8998c986e7732707e',
            'QRCatcher/main.m': '6a78cbe30f34ca31b8fab1b7bbd578b5f9d2dab7ff82fb2126c86d280c529239',
            'QRCatcher/QRCatchViewController.m': '3673123f5b8b0cd80f849a635a24ec2d656c19be3975f9e1ef594f019b4bf6a0',
            PAD_PATH: 'ebf9889c1edbd3f41854862bd0327e87e6b5051da78106610e08154ba9205249'}
        for path, text in self.sources.items():
            with self.subTest(path=path):
                release = preprocess(text, 0)
                for token in ['QRStartup', 'startupObservation', 'mini_startup_v1',
                              '-mini-startup', 'IPAD_MINI_STARTUP_OBSERVATION', 'CFAbsoluteTimeGetCurrent']:
                    self.assertNotIn(token, release)
                self.assertEqual(normalized_digest(release), expected[path])

    def test_debug_call_sites_existing_behavior_and_all_four_cases_remain(self):
        expected = DEBUG_PRESERVATION_DIGESTS
        for path in [APP_PATH, 'QRCatcher/main.m', 'QRCatcher/QRCatchViewController.m', PAD_PATH]:
            with self.subTest(path=path):
                text = preprocess(remove_observation(self.sources[path], path), 1)
                self.assertEqual(normalized_digest(text), expected[path])
        files = (ROOT / 'QRCatcherUITests/QRCatcherImageImportUITests.m').read_bytes()
        self.assertEqual(hashlib.sha256(files).hexdigest(),
                         'a549e2360cc1245166f8bdbe568a557b05afa09a44f0b9d406720074614d81d5')
        self.assertEqual(re.findall(r'- \(void\)(test\w+) \{', self.pad), [
            'testSplitSelectionRotationAndAnchoredShare',
            'testRealPhotoImportReplacesSelectionAndPreservesBothRecords',
            'testLargeTextImportCancellationAndPrivacyReturn'])
        self.assertIn('- (void)testRealFilesImportAndReopen', files.decode())

    def test_brackets_only_existing_sync_calls_and_one_turn(self):
        for source, enter, call, returned in [
                (self.app, 'QRStartupStoreEnter', 'self.historyStore = [[QRHistoryStore alloc] initWithURL:URL];', 'QRStartupStoreReturn'),
                (self.app, 'QRStartupWatchEnter', '[[QRWatchPhoneService shared] activate];', 'QRStartupWatchReturn'),
                (self.view, 'QRStartupFixtureEncodeEnter', 'UIImage *QR = [QRCodeCodec imageForPayload:args[index + 1]];', 'QRStartupFixtureEncodeReturn'),
                (self.view, 'QRStartupFixtureDecodeEnter', 'NSString *decoded = [[QRCodeCodec payloadsInImage:QR] firstObject];', 'QRStartupFixtureDecodeReturn'),
                (self.view, 'QRStartupFixtureHandleSaveEnter', '[self handlePayload:decoded];', 'QRStartupFixtureHandleSaveReturn')]:
            self.assertLess(source.index('QRStartupObservationMark(' + enter + ')'), source.index(call))
            self.assertLess(source.index(call), source.index('QRStartupObservationMark(' + returned + ')'))
        self.assertEqual(self.app.count('dispatch_async(dispatch_get_main_queue()'), 1)
        self.assertIn('QRStartupRecord(QRStartupMainEntry, entryWall);', self.app)
        self.assertIn('QRStartupObservationMark(QRStartupDelegateReturn);\n#endif\n    return YES;', self.app)
        names = self.app.split('static NSString *const names[] = {', 1)[1].split('};', 1)[0]
        self.assertEqual(re.findall(r'@"([a-z_]+)"', names), PHASES)

    def test_optional_read_is_single_and_failure_path_cannot_retry(self):
        read = self.pad.split('- (void)observeStartupValueOnce {', 1)[1].split('- (void)launchPadWithStartupSlot:', 1)[0]
        self.assertEqual(read.count('self.app.staticTexts[@"scan.status"].value'), 1)
        self.assertLess(read.index('self.startupObservationReadAttempted = YES;'), read.index('.value;'))
        for token in ['waitFor', 'sleep', 'XCTAssert', '.exists', '.hittable', '.label', 'for (', 'while (']:
            self.assertNotIn(token, read)
        teardown = self.pad.split('- (void)tearDown {', 1)[1].split('- (void)retainShareReadinessTrace', 1)[0]
        self.assertIn('if (self.testRun.failureCount > 0) [self observeStartupValueOnce];', teardown)
        launch = self.pad.split('- (void)launchPadWithStartupSlot:', 1)[1].split('#endif', 1)[0]
        self.assertEqual(launch.count('[self.app launch];'), 1)
        self.assertLess(launch.index('@"launch_enter"'), launch.index('[self.app launch];'))
        self.assertLess(launch.index('[self.app launch];'), launch.index('@"launch_return"'))
        self.assertLess(launch.index('@"launch_return"'), launch.index('[self observeStartupValueOnce]'))

    def test_selected_slots_and_original_persistence_relaunch_arguments(self):
        split = self.pad.split('- (void)testSplitSelectionRotationAndAnchoredShare {', 1)[1].split('- (void)testRealPhotoImport', 1)[0]
        reopen = split.split('self.app.launchArguments =', 1)[1]
        self.assertTrue(reopen.startswith(' @[@"-ui-testing", @"-AppleLanguages", @"(en)"];'))
        self.assertIn('[self launchPadWithStartupSlot:@"split-reopen"]', reopen)
        self.assertNotIn('-reset-history', reopen)
        self.assertNotIn('-fixture-payload', reopen)
        photo = self.pad.split('- (void)testRealPhotoImport', 1)[1].split('- (void)testLargeText', 1)[0]
        self.assertNotIn('startupObservation', photo)
        self.assertNotIn('launchPadWithStartupSlot', photo)
        self.assertIn('[self.app launch]', photo)

    def test_original_caps_source_device_fixture_audit_fences_and_decoders_are_unchanged(self):
        frozen = {
            'scripts/ipad_mini_setup.py': 'b761d51de1d8c0ce05e05a10415f97b18acc43dd54e7f6d108d0d4cdb697fcaf',
            'scripts/diagnostic_mini_managed_route.py': 'a9944fff240355c6d0b2b2346dc8f7b4cf7c8f34475ba7a6b94d2765421c5c4a',
            'scripts/ipad_mini_state_handoff.py': '32d9fb7e78abbd6b7b0ba6b9ced1b79e2e96faf71ebc8acf3e5d656955cea8d8',
            'scripts/run_ios_platform_ui.sh': '37e2ae553a0fb92954a436d32372a3780c9dc21054253f298537ec53ba1c10cd',
            '.github/workflows/mini-managed-full-row.yml': '78505deae347d7dfb00a211f88478e6cf3a5f8977d2d64b3af4012fda0ba6332',
            '.github/workflows/apple-platforms.yml': '1c3b0759c211b54ec30bd8d19cac9e7a4f03b77dea94ae81146910f10ff202d4',
            'QRCatcher/QRCodeCodec.m': '7f17ac2ac34c4daff264c80d2dd59aa7b1d95b606c01b198b4795714193ef37d',
            'Shared/Image/QRImageCodec.m': 'd7a42240835ea5ee7c83a583b8d696826c39b8bb372a6c2cff374c249f54468f',
            'QRCatcher/QRHistoryStore.m': '18b0f9d0927bfb5d9ee48d517027071e7fcd20e3a1ada348d214cff5b95274c1',
            'QRCatcher/QRWatchPhoneService.m': '562bd1992fc7882eb3f4ca1c9766b2a143d1018f8f26e3abd43561d0eab3f978',
            'QRCatcher/PrivacyInfo.xcprivacy': 'a82d1b5d9285a2b75f67ff6756ebc9f6a5565d3d4400cfd4fa8747a0b380ae58'}
        for path, expected in frozen.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected)
        self.assertIn('self.continueAfterFailure = NO;', self.pad)
        self.assertIn('performAccessibilityAuditWithAuditTypes:XCUIAccessibilityAuditTypeAll issueHandler:nil', self.pad)

    def test_assertion_wait_decoder_and_release_guard_mutations_fail_preservation(self):
        for before, after in [
                ('XCTAssertEqual(history.cells.count, 1);', 'XCTAssertEqual(history.cells.count, 0);'),
                ('waitForExistenceWithTimeout:15', 'waitForExistenceWithTimeout:150'),
                ('XCUIAccessibilityAuditTypeAll', 'XCUIAccessibilityAuditTypeContrast')]:
            changed = self.pad.replace(before, after, 1)
            self.assertNotEqual(changed, self.pad)
            digest = normalized_digest(preprocess(remove_observation(changed, PAD_PATH), 1))
            self.assertNotEqual(digest, DEBUG_PRESERVATION_DIGESTS[PAD_PATH])
        changed = self.view.replace('[[QRCodeCodec payloadsInImage:QR] firstObject]', '@"fake-decode"', 1)
        digest = normalized_digest(preprocess(remove_observation(changed, 'QRCatcher/QRCatchViewController.m'), 1))
        self.assertNotEqual(digest, DEBUG_PRESERVATION_DIGESTS['QRCatcher/QRCatchViewController.m'])
        changed = self.app.replace('#if DEBUG', '#if 1', 1)
        self.assertIn('QRStartupEnabled', preprocess(changed, 0))

    def test_serialization_caps_and_booleans_are_diagnostic_only(self):
        record = dict(version=1, request_id='A' * 36, launch_id='B' * 36, slot='largest-initial',
                      app_pid=2147483647, clock='WALL_CF2001', clock_discontinuity=False,
                      interval_state='UNKNOWN', continuous_responsiveness=False, event_limit=16,
                      events=[dict(phase=name, wall=1.7976931348623157e308) for name in PHASES])
        value = 'event=ui-test epoch=2147483647 authorization=3 scene=2 app=0 visible=1 ready=0 wants=0 mini_startup_v1=' + json.dumps(record)
        self.assertLess(len(value.encode()), 4096)
        self.assertIs(type(record['clock_discontinuity']), bool)
        self.assertIs(type(record['continuous_responsiveness']), bool)
        self.assertNotIn('@(QRStartupClockUnknown)', self.app)
        self.assertIn('self.startupObservationLogBytes += data.length;', self.pad)

    def test_actual_log_budget_reserves_explicit_return_at_saturation(self):
        def encoded(value):
            return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        nonce = 'ABCDEF12-3456-4789-ABCD-EF0123456789'
        def envelope(event, wall=None, observation=None):
            value = dict(version=1, event=event, request_id=nonce, slot='largest-initial',
                         wall=wall, clock='WALL_CF2001', interval_state='UNKNOWN',
                         observations_qualify_pass=False)
            if observation is not None:
                value['observation'] = observation
            return value
        # The fallback has only closed bounded strings and a null timestamp.
        fallback = encoded(envelope('value_read_return', observation=dict(
            retrieval='UNKNOWN_log_cap', startup_record_omitted=True)))
        self.assertLessEqual(len(fallback), 384)
        for used in range(4097):
            normal = self.policy.QRPadStartupLogAllowance(used, 0)
            final = self.policy.QRPadStartupLogAllowance(used, 1)
            self.assertEqual(final, 4096 - used)
            self.assertEqual(normal, max(0, 4096 - used - 384))
        self.assertEqual(self.policy.QRPadStartupLogAllowance(2**63, 0), 0)
        self.assertEqual(self.policy.QRPadStartupLogAllowance(2**63, 1), 0)
        # Saturate every byte permitted to nonfinal records. The decisive final
        # marker still fits; a larger returned app record becomes explicit UNKNOWN.
        used = self.policy.QRPadStartupLogAllowance(0, 0)
        remaining = self.policy.QRPadStartupLogAllowance(used, 1)
        self.assertEqual(used, 3712)
        self.assertEqual(remaining, 384)
        self.assertLessEqual(used + len(fallback), 4096)
        producer = dict(version=1, request_id=nonce, launch_id=nonce, slot='largest-initial',
                        app_pid=2147483647, clock='WALL_CF2001', clock_discontinuity=False,
                        interval_state='UNKNOWN', continuous_responsiveness=False, event_limit=16,
                        events=[dict(phase=name, wall=-1.7976931348623157e308) for name in PHASES])
        camera = 'event=ui-test epoch=2147483647 authorization=3 scene=2 app=0 visible=1 ready=0 wants=0'
        producer_bytes = encoded(producer)
        wrapped = encoded(envelope('value_read_return', wall=-1.7976931348623157e308,
                                   observation=dict(retrieval='returned_current_request_wall_only', startup=producer)))
        markers = [encoded(envelope(event, wall=-1.7976931348623157e308))
                   for event in ['launch_enter', 'launch_return', 'value_read_enter']]
        self.assertLess(len(camera.encode()) + len(b' mini_startup_v1=') + len(producer_bytes), 4096)
        self.assertLess(sum(map(len, markers)) + len(wrapped), 4096)
        # Even a producer admitted at its full independent 4KiB transport cap
        # cannot fit inside the helper envelope plus prior markers. No silent
        # final-record loss is allowed, regardless of serializer numeric width.
        self.assertGreater(4096 + len(wrapped) - len(producer_bytes) + sum(map(len, markers)), 4096)
        logger = self.pad.split('- (void)logStartupEvent:', 1)[1].split('- (void)observeStartupValueOnce', 1)[0]
        self.assertIn('if (!finalEvent) return;', logger)
        self.assertIn('record[@"wall"] = NSNull.null;', logger)
        self.assertIn('@"retrieval": @"UNKNOWN_log_cap"', logger)
        self.assertIn('@"startup_record_omitted": [NSNumber numberWithBool:YES]', logger)
        self.assertEqual(logger.count('NSLog('), 1)

    def test_actual_project_and_generator_consumers_remain_exact(self):
        project = (ROOT / 'QRCatcher.xcodeproj/project.pbxproj').read_text()
        self.assertEqual(hashlib.sha256(project.encode()).hexdigest(),
                         'b88dfe4e98ee99dbab780abe14872fcafbfd88b3dfc02becbb084dc7e243bca0')
        generator = (ROOT / 'scripts/generate_project.py').read_text()
        self.assertIn("(root/'QRCatcher').glob('*')", generator)
        self.assertIn("(root/name).glob('*.m')", generator)
        # Resolve actual PBX file/build/phase/target edges, rather than treating
        # folder membership as evidence of native target consumers.
        objects = {}
        for match in re.finditer(r'(?m)^"([A-F0-9]{24})" = \{\n(.*?)^\};', project, re.S):
            objects.setdefault(match[1], match[2])
        for path, expected_target in [(APP_PATH, 'QRCatcher'), ('QRCatcher/main.m', 'QRCatcher'),
                                      ('QRCatcher/QRCatchViewController.m', 'QRCatcher'), (PAD_PATH, 'QRCatcherUITests')]:
            file_ids = [key for key, value in objects.items() if '"path" = "' + path + '";' in value]
            self.assertEqual(len(file_ids), 1)
            builds = [key for key, value in objects.items() if '"fileRef" = "' + file_ids[0] + '";' in value]
            phases = [key for key, value in objects.items() if '"isa" = "PBXSourcesBuildPhase";' in value and any('"' + build + '"' in value for build in builds)]
            consumers = [value for value in objects.values() if '"isa" = "PBXNativeTarget";' in value and any('"' + phase + '"' in value for phase in phases)]
            self.assertEqual(len(consumers), 1, path)
            self.assertIn('"name" = "' + expected_target + '";', consumers[0])

    def test_tokens_bounds_clock_gates_reads_and_transports_mutations_are_rejected(self):
        mutations = [
            ('app', '-mini-startup-observation-v1', '-mini-startup-observation'),
            ('app', 'QRStartupByteLimit = 4096;', 'QRStartupByteLimit = 8192;'),
            ('app', 'phase < 13 && count < 16', 'phase < 13 || count < 16'),
            ('app', 'tokenCount == 1 && canonicalUUID', 'tokenCount == 1 || canonicalUUID'),
            ('app', 'request.UUIDString isEqualToString:requestID', 'request.UUIDString containsString:requestID'),
            ('app', '@"split-reopen"] containsObject:slot', '@"arbitrary"] containsObject:slot'),
            ('app', '@"interval_state": @"UNKNOWN"', '@"interval_state": @"COMPLETE"'),
            ('app', '[NSNumber numberWithBool:QRStartupClockUnknown]', '@(1)'),
            ('app', 'QRStartupTurnScheduled = YES;', 'QRStartupTurnScheduled = NO;'),
            ('pad', 'self.startupObservationReadAttempted = YES;', 'self.startupObservationReadAttempted = NO;'),
            ('pad', 'count] <= 16', 'count] <= 100'),
            ('pad', 'remaining > 384 ? (int)(remaining - 384) : 0', 'remaining > 0 ? (int)remaining : 0'),
            ('pad', '@"UNKNOWN_log_cap"', '@"COMPLETE"'),
            ('pad', '[self logStartupEvent:@"launch_return" observation:nil]', '[self logStartupEvent:@"unknown" observation:nil]')]
        for target, before, after in mutations:
            with self.subTest(target=target, mutation=before):
                app, pad = self.app, self.pad
                if target == 'app':
                    self.assertIn(before, app); app = app.replace(before, after, 1)
                else:
                    self.assertIn(before, pad); pad = pad.replace(before, after, 1)
                with self.assertRaises(ValueError):
                    source_contract(app, pad, self.view, self.main)
        for forbidden in ['simctl', 'UIPasteboard', 'writeToFile', 'NSTimer', 'systemUptime']:
            mutated = self.app.replace('static BOOL QRStartupEnabled;', 'static BOOL QRStartupEnabled; ' + forbidden)
            with self.subTest(transport=forbidden), self.assertRaises(ValueError):
                source_contract(mutated, self.pad, self.view, self.main)


# These are filled from the immutable v5 source, never from candidate output.
DEBUG_PRESERVATION_DIGESTS = {'QRCatcher/AppDelegate.m': '73d08f345953ba15095398f2d26c8916e40a501193337c4a858820d6bc3d6dd1', 'QRCatcher/main.m': '6a78cbe30f34ca31b8fab1b7bbd578b5f9d2dab7ff82fb2126c86d280c529239', 'QRCatcher/QRCatchViewController.m': '724f0a33235446b70a496236a29ed03300889250cfa1e52bda5d17dd49b539e2', 'QRCatcherUITests/QRCatcherPadUITests.m': 'ebf9889c1edbd3f41854862bd0327e87e6b5051da78106610e08154ba9205249'}

if __name__ == '__main__':
    unittest.main()
