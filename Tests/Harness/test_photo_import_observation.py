"""Closed diagnostic boundaries; these checks do not qualify native import."""
import ctypes
import hashlib
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'QRCatcher/QRCatchViewController.m'
QUEUE = ROOT / 'Shared/Image/QRImageImportQueue.m'
UI = ROOT / 'QRCatcherUITests/QRCatcherImageImportUITests.m'
BASE_RELEASE = {
    'QRCatcher/QRCatchViewController.m': '46b6c96ab0af83ed5a735dae52eeae2afacf1d804837d38d5de2436cfa8e59f7',
    'Shared/Image/QRImageImportQueue.m': '73f2e1f693fc8ec91fbf708313b1e6978914f585b6428d0279f9c9408330ad44',
}

def remove_hashed_region(text, start_marker, end_marker, expected, include_end=False):
    start = text.index(start_marker)
    end = text.index(end_marker, start) + (len(end_marker) if include_end else 0)
    part = text[start:end]
    if hashlib.sha256(part.encode()).hexdigest() != expected:
        raise ValueError('Changed admitted diagnostic region: ' + start_marker)
    return text[:start] + text[end:]

def replace_once(text, new, old=''):
    if text.count(new) != 1:
        raise ValueError('Changed admitted diagnostic call site')
    return text.replace(new, old, 1)

def restore_qrcatch_parent(text):
    expected = 'ae66e51d08ccd51400be47f384b3992dab7e8eb19472908010f8ff997415c5ca'
    if hashlib.sha256(text.encode()).hexdigest() == expected:
        return text
    text = remove_hashed_region(text, '#if DEBUG\n#import "QRPrivacyViewController.h"', '#endif\n',
        '9dc8944aad8dec4123afeae031d6f108024e326a3d68934109d0f2a9121a3fa0', True)
    text = remove_hashed_region(text, '@property (nonatomic, copy) NSString *photoObservationRequestID;', '@property (nonatomic) BOOL photoObservationUnknown;\n',
        '1b4ea2892632b0aa279f01b3013c14e48c4a42d23c1304a44558ea2319691054', True)
    text = remove_hashed_region(text, '- (void)beginPhotoObservationForGeneration:', '- (void)traceCamera:',
        'cef2a64e8d5204a9008ce31ffc9c5d27a438c315eef0aa50aa607fa5c73112df')
    text = replace_once(text, '    QRPrivacySystemOpenObservationAttach(self.statusLabel);\n')
    text = replace_once(text, '    self.statusLabel.accessibilityValue = QRPrivacySystemOpenObservationMergeCameraValue([self mergePhotoObservationCameraValue:QRStartupObservationMergeCameraValue(cameraValue)]);\n',
        '    self.statusLabel.accessibilityValue = QRStartupObservationMergeCameraValue(cameraValue);\n')
    for part in [
        '#if DEBUG\n    [self beginPhotoObservationForGeneration:generation];\n    [self recordPhotoObservation:@"provider_request" generation:generation];\n    [self publishPhotoObservation];\n#endif\n',
        '#if DEBUG\n        [weakSelf recordPhotoObservation:@"provider_callback" generation:generation];\n#endif\n',
        '#if DEBUG\n        [self publishPhotoObservation];\n#endif\n',
        '#if DEBUG\n            [weakSelf recordPhotoObservation:@"main_update_return" generation:generation];\n            [weakSelf publishPhotoObservation];\n#endif\n']:
        text = replace_once(text, part)
    text = replace_once(text,
        '#if DEBUG\n        } debugDecodeObserver:self.photoObservationRequestID ? ^{ [weakSelf recordPhotoObservation:@"decode_return" generation:generation]; } : nil completion:^(NSArray<NSString *> *values, NSError *error) {\n#else\n        } completion:^(NSArray<NSString *> *values, NSError *error) {\n#endif\n',
        '        } completion:^(NSArray<NSString *> *values, NSError *error) {\n')
    if hashlib.sha256(text.encode()).hexdigest() != expected:
        raise ValueError('Original QRCatch parent source changed')
    return text

def restore_image_import_parent(text):
    expected = 'a549e2360cc1245166f8bdbe568a557b05afa09a44f0b9d406720074614d81d5'
    if hashlib.sha256(text.encode()).hexdigest() == expected:
        return text
    text = remove_hashed_region(text, '#import <math.h>\n', 'static BOOL QRPhoneFilesPresentationSnapshotReady',
        '3149de7624168528c5188514f8d5e3735962f3057a05d9d0ebbc2afcd25c1bca')
    text = replace_once(text, '#import "QRFilesPickerSnapshot.h"\nstatic BOOL', '#import "QRFilesPickerSnapshot.h"\n\nstatic BOOL')
    text = remove_hashed_region(text, '@property (nonatomic, copy) NSString *photoObservationRequestID;', '@property (nonatomic) BOOL photoObservationUncertain;\n',
        'ebd7de8e1a1881aaf2d16cc5261f1669d2c301a42ebfb2f92636b9c6247dcd9f', True)
    text = remove_hashed_region(text, '- (void)readPhotoObservationOnce', '- (void)capture:',
        'd202a85b5738a6f41bc628a93afacc259523508763f765fbd257c1667c7f3086')
    text = replace_once(text,
        '    if ([self.name isEqualToString:@"-[QRCatcherImageImportUITests testRealPhotosImportAndReopen]"]) {\n        self.photoObservationCaseStarted = NSProcessInfo.processInfo.systemUptime;\n        self.photoObservationRequestID = NSUUID.UUID.UUIDString;\n        self.app.launchArguments = [self.app.launchArguments arrayByAddingObjectsFromArray:@[@"-photo-import-observation-v1", @"-photo-import-observation-request-id", self.photoObservationRequestID]];\n    }\n')
    text = replace_once(text,
        '    if (self.photoObservationUncertain) {\n        NSLog(@"PHOTO_IMPORT_OBSERVATION_V1:UNKNOWN late owned-value read; no further authored device/AX actions");\n        [super tearDown];\n        [self removeUIInterruptionMonitor:self.interruptionGuard];\n        return;\n    }\n    if (self.testRun.failureCount && self.photoObservationWaitReturned) [self readPhotoObservationOnce];\n    if (self.photoObservationUncertain) {\n        [super tearDown];\n        [self removeUIInterruptionMonitor:self.interruptionGuard];\n        return;\n    }\n')
    start = text.index('    [self expectationForPredicate:decoded evaluatedWithObject:')
    end = text.index('    XCTAssertFalse(self.app.buttons[@"scan.open"].exists);', start)
    # The original predicate and 20-second wait remain independently checked.
    part = text[start:end]
    if hashlib.sha256(part.encode()).hexdigest() != 'f1c64f5f2e04b44ea219a3e8cef9f6551bbafcb14a9ce97fcdc1bfc09c2f9a7c':
        raise ValueError('Changed admitted import wait observation')
    required = '[self expectationForPredicate:decoded evaluatedWithObject:self.app.staticTexts[@"scan.result"] handler:nil];'
    if part.count(required) != 1 or part.count('[self waitForExpectationsWithTimeout:20 handler:nil]') != 1:
        raise ValueError('Original import predicate/wait changed')
    text = text[:start] + '    ' + required + ' [self waitForExpectationsWithTimeout:20 handler:nil];\n' + text[end:]
    if hashlib.sha256(text.encode()).hexdigest() != expected:
        raise ValueError('Original image import parent source changed')
    return text

def restore_launcher_parent(text):
    expected = '966f8993caf06f32e36a36251e98ba9fbff95cf2f893c2d561df4e683db89a58'
    if hashlib.sha256(text.encode()).hexdigest() == expected:
        return text
    text = remove_hashed_region(text,
        'if [ "$SUPPLEMENT_ONLY" = true ] && [ "${PHONE_COMPLETION_ONLY:-}" = true ]; then',
        'python3 scripts/owned_process_barrier.py --check',
        '3f4fdfa7df22265631ff766c4c88e4b620fb32bbe8a1dca187030e42580df3c8')
    start = text.index('    if qualify_supplement_result "$OUTPUT" "$CAP" "$TEST_EXIT"; then\n')
    end = text.index('\n  fi\n}', start)
    part = text[start:end]
    if hashlib.sha256(part.encode()).hexdigest() != 'cc8807c70ec46c4bab1200655d38801984a7ce45b59df3cac02bc5ce31293c5e':
        raise ValueError('Changed admitted early evidence dispatch')
    text = text[:start] + '    if qualify_supplement_result "$OUTPUT" "$CAP" "$TEST_EXIT"; then :; else SUPPLEMENT_GATE_EXIT=$?; fi' + text[end:]
    if hashlib.sha256(text.encode()).hexdigest() != expected:
        raise ValueError('Original launcher parent source changed')
    return text

def function(source, name):
    start = source.index('static int ' + name + '(')
    opened = source.index('{', start)
    level = 1
    end = opened + 1
    while level:
        level += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end].replace('static int ', 'int ', 1)

def preprocess(text, debug):
    compiler = shutil.which('cc') or shutil.which('gcc')
    if not compiler:
        raise RuntimeError('An existing standard C preprocessor is required')
    # Framework imports are unavailable on the portable host; only imports
    # are removed. This is preprocessor identity, not an Apple SDK build.
    data = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#import')) + '\n'
    result = subprocess.run([compiler, '-E', '-P', '-x', 'c', '-undef', '-DDEBUG=' + str(debug), '-'],
                            input=data.encode(), capture_output=True, timeout=30, check=True)
    return result.stdout

class PhotoObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix='qrphotoobs-')
        source = Path(cls.folder.name) / 'clock.c'
        library = Path(cls.folder.name) / 'clock.so'
        names = ['QRPhotoObservationCanRead', 'QRPhotoObservationReadReturned', 'QRPhotoObservationWaitReturned']
        source.write_text('#include <math.h>\n' + '\n'.join(function(UI.read_text(), n) for n in names))
        compiler = shutil.which('cc') or shutil.which('gcc')
        if not compiler:
            raise RuntimeError('Existing C compiler required for actual decision functions')
        subprocess.run([compiler, '-shared', '-fPIC', str(source), '-o', str(library), '-lm'],
                       capture_output=True, timeout=30, check=True)
        cls.native = ctypes.CDLL(str(library))
        for name, count in zip(names, (2, 3, 2)):
            value = getattr(cls.native, name)
            value.argtypes = [ctypes.c_double] * count
            value.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_actual_owned_read_requires_full_original_reserve(self):
        f = self.native.QRPhotoObservationCanRead
        self.assertEqual(f(1000, 1148), 1)
        self.assertEqual(f(1000, math.nextafter(1148, math.inf)), 0)
        self.assertEqual(f(1000, 1000), 1)
        for args in ((1000, 999), (-1, 0), (math.nan, 0), (0, math.inf), (0, 180)):
            self.assertEqual(f(*args), 0)

    def test_actual_read_return_cannot_borrow_teardown_or_time(self):
        f = self.native.QRPhotoObservationReadReturned
        self.assertEqual(f(1000, 1148, 1160), 1)
        self.assertEqual(f(1000, 1148, math.nextafter(1160, math.inf)), 0)
        self.assertEqual(f(1000, 1000, 1012), 1)
        for args in ((1000, 1000, 1013), (1000, 1000, 999), (1000, 1150, 1151), (0, 0, math.nan)):
            self.assertEqual(f(*args), 0)

    def test_actual_wait_return_observation_does_not_change20(self):
        f = self.native.QRPhotoObservationWaitReturned
        self.assertEqual(f(1000, 1022), 1)
        self.assertEqual(f(1000, math.nextafter(1022, math.inf)), 0)
        self.assertEqual(f(1000, 999), 0)
        self.assertEqual(f(math.nan, 0), 0)
        self.assertIn('[self waitForExpectationsWithTimeout:20 handler:nil]', UI.read_text())

    def test_release_preprocessor_identity_for_both_algorithm_consumers(self):
        for name, expected in BASE_RELEASE.items():
            data = preprocess((ROOT / name).read_text(), 0)
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected, name)
            for marker in (b'photoObservation', b'photo-import-observation', b'debugDecodeObserver', b'QRPrivacySystemOpenObservation'):
                self.assertNotIn(marker, data)

    def test_one_decoder_algorithm_and_original_public_queue_interface(self):
        text = QUEUE.read_text()
        self.assertEqual(text.count('[QRImageCodec decodeImageData:data error:&error]'), 1)
        self.assertIn('return [self readWithLoader:loader debugDecodeObserver:nil completion:completion];', text)
        self.assertLess(text.index('NSArray *values = data ?'), text.index('if (observer) observer();'))
        self.assertLess(text.index('if (observer) observer();'), text.index('dispatch_async(dispatch_get_main_queue()'))
        self.assertEqual(text.count('[self.queue addOperation:operation]'), 1)
        self.assertEqual(text.count('completion(values, error)'), 1)
        self.assertIn('if (!current || current.cancelled) return;', text)
        self.assertIn('if (!current.cancelled) completion(values, error)', text)

    def test_four_exact_real_boundaries_no_extra_queue_or_data(self):
        text = APP.read_text()
        photo = text[text.index('- (void)readPhotoProvider:'):text.index('- (void)finishImportedValues:')]
        self.assertEqual(photo.count('dispatch_async('), 1)
        self.assertEqual(photo.count('loadFileRepresentationForTypeIdentifier:type'), 1)
        self.assertEqual(photo.count('readWithLoader:'), 1)
        self.assertLess(photo.index('recordPhotoObservation:@"provider_request"'), photo.index('loadFileRepresentationForTypeIdentifier:type'))
        self.assertLess(photo.index('recordPhotoObservation:@"provider_callback"'), photo.index('[QRBoundedImageFileReader readURL:URL'))
        self.assertIn('debugDecodeObserver:self.photoObservationRequestID ? ^{ [weakSelf recordPhotoObservation:@"decode_return"', photo)
        self.assertLess(photo.index('[weakSelf finishImportedValues:'), photo.index('recordPhotoObservation:@"main_update_return"'))
        self.assertIn('if (generation != self.importGeneration) return;', photo)

    def test_synthetic_token_is_exact_mutually_exclusive_and_bounded(self):
        text = APP.read_text()
        gate = text[text.index('- (void)beginPhotoObservationForGeneration:'):text.index('- (void)recordPhotoObservation:')]
        for flag in ('-ui-testing', '-reset-history', '-photo-import-observation-v1', '-photo-import-observation-request-id', '-fixture-payload'):
            self.assertIn('@"' + flag + '"', gate)
        self.assertIn('if (count != 1) return;', gate)
        self.assertIn('args.count > 64', gate)
        self.assertIn('Previous selected result', gate)
        self.assertIn('canonical.UUIDString isEqualToString:requestID', gate)
        self.assertIn('processIdentifier <= 0', gate)
        self.assertIn('-privacy-system-open-v1', gate)
        self.assertIn('-mini-startup-observation-v1', gate)
        self.assertIn('self.photoObservationTimes.count >= 4', text)
        self.assertIn('data.length > 1024', text)
        self.assertIn('<= 4096 ? value : cameraValue', text)

    def test_background_only_records_existing_main_paths_publish(self):
        text = APP.read_text()
        record = text[text.index('- (void)recordPhotoObservation:'):text.index('- (NSString *)mergePhotoObservationCameraValue:')]
        self.assertIn('@synchronized (self)', record)
        self.assertNotIn('statusLabel', record)
        self.assertNotIn('dispatch_', record)
        self.assertIn('generation != self.importGeneration', record)
        publisher = text[text.index('- (void)publishPhotoObservation'):text.index('- (void)traceCamera:')]
        self.assertIn('!NSThread.isMainThread', publisher)
        self.assertNotIn('dispatch_', publisher)
        self.assertIn('QRPrivacySystemOpenObservationMergeCameraValue', publisher)

    def test_closed_receipt_contains_no_photo_content_or_paths(self):
        text = APP.read_text()
        merge = text[text.index('- (NSString *)mergePhotoObservationCameraValue:'):text.index('- (void)publishPhotoObservation')]
        for word in ('URL', 'payload', 'photoProgress', 'NSData *data = URL', 'fileSystemRepresentation'):
            self.assertNotIn(word, merge)
        self.assertIn('NSJSONWritingSortedKeys', merge)
        self.assertIn('@"observations_qualify_pass": @NO', merge)
        self.assertIn('[NSNumber numberWithBool:self.photoObservationUnknown]', merge)

    def test_consumer_one_owned_read_and_late_fence(self):
        text = UI.read_text()
        read = text[text.index('- (void)readPhotoObservationOnce'):text.index('- (void)capture:')]
        self.assertEqual(read.count('self.app.staticTexts[@"scan.status"].value'), 1)
        self.assertIn('self.photoObservationReadAttempted = YES', read)
        self.assertIn('QRPhotoObservationCanRead(self.photoObservationCaseStarted, started)', read)
        self.assertIn('QRPhotoObservationReadReturned(self.photoObservationCaseStarted, started, returned)', read)
        self.assertIn('self.photoObservationUncertain = YES', read)
        teardown = text[text.index('- (void)tearDown'):text.index('- (void)readPhotoObservationOnce')]
        self.assertLess(teardown.index('if (self.photoObservationUncertain)'), teardown.index('self.app.debugDescription'))
        self.assertIn('!self.photoObservationWaitReturned', read)

    def test_original_functional_assertions20_payload_history_and_all_retained(self):
        text = UI.read_text()
        self.assertIn('@"label == %@",@"QRCatcher 你好 🌈 123"', text)
        self.assertIn('XCTAssertEqual(table.cells.count,2)', text)
        self.assertIn('XCUIAccessibilityAuditTypeAll', text)
        self.assertIn('return NO;', text[text.index('issueHandler:'):text.index('error:&error]')])
        self.assertIn('testRealPhotosImportAndReopen', text)
        self.assertIn('testRealFilesImportAndReopen', text)
        self.assertIn('testRealPickerWarmupAndCancelPreservesPreviousSelection', text)

    def test_schema_validation_rejects_duplicates_booleans_and_stale_identity(self):
        text = UI.read_text()
        self.assertIn('[canonical isEqualToData:data]', text)
        self.assertIn('record.allKeys] isEqualToSet:keys', text)
        self.assertIn('record[@"request_id"] isEqual:self.photoObservationRequestID', text)
        self.assertIn('CFBooleanGetTypeID()', text)
        self.assertIn('number.doubleValue == floor(number.doubleValue)', text)
        self.assertIn('if (!QRPhotoDiagnosticNumber(stamp)) { owned = NO; continue; }', text)
        self.assertIn('times.allKeys] isEqualToSet:[NSSet setWithArray:phases]', text)

    def test_container_type_rejection_precedes_every_keyed_access(self):
        text = UI.read_text()
        read = text[text.index('- (void)readPhotoObservationOnce'):text.index('- (void)capture:')]
        root_guard = read.index('if (![parsed isKindOfClass:NSDictionary.class])')
        first_key = read.index('record[@"times"]')
        times_guard = read.index('if (![parsedTimes isKindOfClass:NSDictionary.class])')
        key_set = read.index('times.allKeys')
        self.assertLess(root_guard, first_key)
        self.assertLess(times_guard, key_set)
        self.assertIn('UNKNOWN JSON root is not a dictionary', read)
        self.assertIn('UNKNOWN times is not a dictionary', read)
        # NSArray/null/string root and times cannot reach NSDictionary-only
        # subscripting/key-set operations. Apple execution remains separate.
        for bad in ('[]', 'null', '"text"', '{"times":[]}'):
            import json
            parsed = json.loads(bad)
            self.assertFalse(isinstance(parsed, dict) and isinstance(parsed.get('times'), dict))

    def test_parser_exception_keeps_uncertainty_until_validated_receipt(self):
        text = UI.read_text()
        read = text[text.index('- (void)readPhotoObservationOnce'):text.index('- (void)capture:')]
        self.assertEqual(read.count('self.photoObservationUncertain = NO'), 1)
        self.assertLess(read.index('if (!owned)'), read.index('self.photoObservationUncertain = NO'))
        self.assertGreaterEqual(read.count('@catch (NSException *exception)'), 2)
        self.assertIn('UNKNOWN receipt parser exception; no further authored AX actions', read)

    def test_exact_parent_restoration_rejects_business_and_observer_changes(self):
        self.assertEqual(hashlib.sha256(restore_qrcatch_parent(APP.read_text()).encode()).hexdigest(),
                         'ae66e51d08ccd51400be47f384b3992dab7e8eb19472908010f8ff997415c5ca')
        self.assertEqual(hashlib.sha256(restore_image_import_parent(UI.read_text()).encode()).hexdigest(),
                         'a549e2360cc1245166f8bdbe568a557b05afa09a44f0b9d406720074614d81d5')
        for source, restore, before, after in [
            (APP.read_text(), restore_qrcatch_parent, 'values.firstObject', '@"fake-value"'),
            (APP.read_text(), restore_qrcatch_parent, 'self.photoObservationTimes.count >= 4', 'self.photoObservationTimes.count >= 40'),
            (UI.read_text(), restore_image_import_parent, 'waitForExpectationsWithTimeout:20', 'waitForExpectationsWithTimeout:200'),
            (UI.read_text(), restore_image_import_parent, 'XCUIAccessibilityAuditTypeAll', 'XCUIAccessibilityAuditTypeContrast')]:
            self.assertIn(before, source)
            with self.assertRaises(ValueError):
                restore(source.replace(before, after, 1))

if __name__ == '__main__':
    unittest.main()
