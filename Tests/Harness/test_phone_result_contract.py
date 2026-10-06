"""Portable source/evidence contracts; not UIKit compilation or native AX proof."""
import ast
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = (ROOT / 'QRCatcher/QRPhoneResultViewController.m').read_text()
HISTORY = (ROOT / 'QRCatcher/QRURLViewController.m').read_text()
UI = (ROOT / 'QRCatcherUITests/QRCatcherUITests.m').read_text()
IMPORT_UI = (ROOT / 'QRCatcherUITests/QRCatcherImageImportUITests.m').read_text()
HOSTED = (ROOT / 'QRCatcherTests/QRPhoneResultTests.m').read_text()
EXPORTER = (ROOT / 'scripts/export_ios_platform_screenshots.py').read_text()
TREE = ast.parse(EXPORTER)
DEFINITIONS = [node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == 'validate_import_audit_pair_receipts']
NAMESPACE = {'json': json}
exec(compile(ast.Module(body=DEFINITIONS, type_ignores=[]), '<exact-import-receipt-validator>', 'exec'), NAMESPACE)
validate = NAMESPACE['validate_import_audit_pair_receipts']


class PhoneResultContractTests(unittest.TestCase):
    def receipts(self, issues=0):
        return [dict(phase=phase, callback_issues=issues if index == 0 else 0,
                     registered_failure_delta=issues if index == 0 else 0,
                     api_returned_success=True, error='') for index, phase in
                enumerate(['app-owned-result', 'same-history-after-cancel'])]

    def test_valid_receipts_keep_raw_counts_even_when_api_returns_true(self):
        for issues in [0, 5]:
            rows = self.receipts(issues)
            self.assertEqual(validate(json.dumps(rows).encode()), rows)
            self.assertEqual(rows[0]['callback_issues'], issues)
            self.assertEqual(rows[0]['registered_failure_delta'], issues)

    def test_legacy_alert_reversed_missing_or_duplicate_phases_reject(self):
        rows = self.receipts()
        alternatives = [rows[:1], rows[::-1], [rows[0], rows[0]], self.receipts()]
        alternatives[-1][0]['phase'] = 'native-alert'
        for value in alternatives:
            with self.assertRaises(ValueError): validate(json.dumps(value).encode())

    def test_boolean_negative_string_or_missing_counts_reject(self):
        for key in ['callback_issues', 'registered_failure_delta']:
            for value in [True, -1, '0', None, 0.5]:
                rows = self.receipts(); rows[0][key] = value
                with self.assertRaises(ValueError): validate(json.dumps(rows).encode())
            rows = self.receipts(); del rows[0][key]
            with self.assertRaises(ValueError): validate(json.dumps(rows).encode())

    def test_unknown_qualification_fields_errors_and_oversized_data_reject(self):
        rows = self.receipts(); rows[0]['audit_passed'] = True
        with self.assertRaises(ValueError): validate(json.dumps(rows).encode())
        rows = self.receipts(); rows[0]['error'] = None
        with self.assertRaises(ValueError): validate(json.dumps(rows).encode())
        rows = self.receipts(); rows[0]['api_returned_success'] = 1
        with self.assertRaises(ValueError): validate(json.dumps(rows).encode())
        with self.assertRaises(ValueError): validate(b' ' * 4097)

    def test_public_owned_panes_exact_payload_and_uncapped_preferred_fonts(self):
        self.assertIn('_payload = [payload copy]', PRODUCT)
        self.assertIn('body.text = self.payload', PRODUCT)
        self.assertIn('body.numberOfLines = 0', PRODUCT)
        self.assertIn('body.lineBreakMode = NSLineBreakByCharWrapping', PRODUCT)
        self.assertIn('UIFontTextStyleTitle2', PRODUCT)
        self.assertIn('UIFontTextStyleBody', PRODUCT)
        self.assertIn('UIFontTextStyleHeadline', PRODUCT)
        self.assertEqual(PRODUCT.count('adjustsFontForContentSizeCategory = YES'), 3)
        for identifier in ['text-scroll', 'action-scroll', 'title', 'payload', 'copy', 'open', 'cancel']:
            self.assertIn('@"history.result.' + identifier + '"', PRODUCT)
        self.assertIn('contentLayoutGuide', PRODUCT); self.assertIn('frameLayoutGuide', PRODUCT)
        self.assertIn('multiplier:0.45', PRODUCT)
        for forbidden in ['UIAlertController *', 'valueForKey:', 'setValue:', 'subviews', 'fontWithSize:',
                          'systemFontOfSize:', 'minimumScaleFactor', 'setAccessibilityLabel:', 'substringToIndex:']:
            self.assertNotIn(forbidden, PRODUCT)

    def test_dismissal_guard_and_explicit_effects_use_complete_snapshot(self):
        finish = PRODUCT.split('- (void)finishWithAction:', 1)[1].split('- (void)copyResult', 1)[0]
        self.assertLess(finish.index('if (self.finishing) return'), finish.index('self.finishing = YES'))
        self.assertIn('dismissViewControllerAnimated:YES completion:action', finish)
        copy = PRODUCT.split('- (void)copyResult', 1)[1].split('- (void)openWebsite', 1)[0]
        self.assertIn('NSString *payload = self.payload', copy)
        self.assertIn('finishWithAction:^{ UIPasteboard.generalPasteboard.string = payload;', copy)
        opened = PRODUCT.split('- (void)openWebsite', 1)[1].split('- (void)cancel', 1)[0]
        self.assertIn('if (!self.websiteURL) return', opened)
        self.assertIn('finishWithAction:^{ open(URL); }', opened)
        self.assertIn('accessibilityPerformEscape { [self cancel]; return YES; }', PRODUCT)

    def test_ipad_callback_remains_before_phone_modal_and_opens_safely(self):
        selected = HISTORY.split('didSelectRowAtIndexPath:', 1)[1].split('- (void)showMessage:', 1)[0]
        self.assertLess(selected.index('self.selectedPayloadHandler(record.url); return'), selected.index('QRPhoneResultViewController *result'))
        self.assertIn('if (self.presentedViewController) return', selected)
        self.assertIn('initWithPayload:record.url ?: @""', selected)
        self.assertIn('openURL:URL options:@{} completionHandler:', selected)
        self.assertIn('if (!success) [self showMessage:', selected)
        self.assertNotIn('UIAlertController', selected)
        self.assertIn('[NSString HTTPURLFromString:_payload]', PRODUCT)
        for forbidden in ['deleteObject:', 'recordPayload:', 'save:', 'createDate =', 'openURL:']:
            self.assertNotIn(forbidden, PRODUCT)

    def test_strict_native_audits_and_actual_pre_presentation_rows_survive(self):
        audit = IMPORT_UI.split('- (NSDictionary *)auditCurrentResultPhase:', 1)[1].split('- (void)attachBoundedText:', 1)[0]
        self.assertIn('XCUIAccessibilityAuditTypeAll', audit)
        self.assertIn('return NO;', audit); self.assertNotIn('return YES;', audit)
        self.assertIn('XCTAssertEqual(callbackIssues, 0', audit)
        self.assertIn('@finally { self.continueAfterFailure = previousContinuation; }', audit)
        reopening = IMPORT_UI.split('- (void)assertImportedResultAndRelaunch', 1)[1].split('- (void)testRealPicker', 1)[0]
        self.assertLess(reopening.index('self.historyRowsBeforePresentation = [self importedHistoryRows]'), reopening.index('[table.cells.firstMatch tap]'))
        pair = IMPORT_UI.split('- (void)auditCurrentResult {', 1)[1].split('- (void)chooseSource:', 1)[0]
        self.assertIn('NSArray *before = self.historyRowsBeforePresentation', pair)
        self.assertIn('XCTAssertEqualObjects(after, before', pair)
        self.assertIn('result.buttons[@"history.result.cancel"]', pair)
        self.assertIn('canCancel', pair)
        self.assertEqual(UI.count('XCUIAccessibilityAuditTypeAll'), 4)

    def test_largest_text_asserts_both_real_endpoints_and_separate_actions(self):
        case = UI.split('- (void)testLargeTextLayoutKeepsControlsReachable', 1)[1].split('- (void)testAccessibilityOfResultAndHistory', 1)[0]
        for token in ['XCTAssertEqualObjects(body.label, expectedBody)', 'CGRectContainsRect(textViewport, beginning)',
                      'CGRectContainsRect(textViewport, ending)', 'CGRectContainsRect(actionViewport, cancel.frame)',
                      '[textScroll swipeUp]', '[actionScroll swipeUp]', 'phone-largest-history-result-top',
                      'phone-largest-history-result-end', 'XCUIAccessibilityAuditTypeAll', 'issueHandler:nil']:
            self.assertIn(token, case)
        self.assertNotIn('self.app.alerts', case)
        self.assertIn('[self assertChineseHistoryResultKeepsCompletePayloadAndRepeatedCancel]', UI)
        self.assertIn('- (void)assertChineseHistoryResultKeepsCompletePayloadAndRepeatedCancel', UI)
        self.assertEqual(UI.count('- (void)test'), 8, 'Keep the exact nine-case ordinary plus picker-warmup inventory')
        gate = (ROOT / 'scripts/ios_import_continuation.py').read_text()
        self.assertIn("('Failed', 9, 8, 1, 0, 0)", gate)

    def test_native_functional_tests_and_inventory_are_declared(self):
        for case in ['testCompleteUnicodeSnapshotCopiesOnceOnlyAfterDismissal',
                     'testCancelAndAccessibilityEscapeHaveNoCopyOrOpenSideEffects',
                     'testOnlySafeWebsitesOpenOnceAfterExplicitActionAndDismissal',
                     'testRepeatedDecodedImportsHistorySelectionAndIPadCallbackPreserveRows',
                     'testLargestDynamicTypeFullTextAndActionsInBoundedPublicScrollPanes',
                     'testChineseTranslationsCoverEveryResultActionWithoutChangingPayload',
                     'testRealUIKitDismissalCopyCancelEscapeAndReopen']:
            self.assertIn(case, HOSTED)
        self.assertNotIn('valueForKey:', HOSTED); self.assertNotIn('setValue:', HOSTED)
        project = (ROOT / 'QRCatcher.xcodeproj/project.pbxproj').read_text()
        for path in ['QRCatcher/QRPhoneResultViewController.h', 'QRCatcher/QRPhoneResultViewController.m', 'QRCatcherTests/QRPhoneResultTests.m']:
            self.assertEqual(project.count('"path" = "' + path + '"'), 1)
        ref = hashlib.sha1(b'file:QRCatcher/QRPhoneResultViewController.m').hexdigest()[:24].upper()
        build = hashlib.sha1(('build:' + ref).encode()).hexdigest()[:24].upper()
        phase = hashlib.sha1(b'appsources').hexdigest()[:24].upper()
        self.assertIn(build, project.split('"' + phase + '" = {', 1)[1].split('};', 1)[0])
        for other in ['mac', 'watch', 'tv', 'vision']:
            phase = hashlib.sha1((other + 'sources').encode()).hexdigest()[:24].upper()
            self.assertNotIn(build, project.split('"' + phase + '" = {', 1)[1].split('};', 1)[0])




class PhoneAssertionMacroTests(unittest.TestCase):
    """Actual C preprocessing plus source checks; not native XCTest runtime."""
    def preprocess(self,expression):
        import shutil,subprocess
        cc=shutil.which('cc')
        self.assertIsNotNone(cc,'The standard compiler preprocessor is required')
        fixture='#define ASSERT_EXPRESSION_ONLY(expression) expression\nASSERT_EXPRESSION_ONLY('+expression+')\n'
        return subprocess.run([cc,'-E','-P','-x','c','-'],input=fixture,capture_output=True,text=True,timeout=10)

    def test_actual_preprocessor_rejects_observed_array_comma_and_accepts_same_parenthesized_expression(self):
        original='[@[@"http", @"https"] containsObject:opened.scheme]'
        rejected=self.preprocess(original)
        self.assertNotEqual(rejected.returncode,0)
        fixed=self.preprocess('('+original+')')
        self.assertEqual(fixed.returncode,0,fixed.stderr)
        self.assertEqual(fixed.stdout.strip(),'('+original+')')
        self.assertNotEqual(self.preprocess('[@{@"http": @1, @"https": @2} objectForKey:opened.scheme]').returncode,0)

    def test_hosted_scheme_guard_preserves_both_schemes_boolean_and_failure_outcome(self):
        import re
        line=next(line.strip() for line in HOSTED.splitlines() if 'containsObject:opened.scheme' in line)
        self.assertEqual(line,'XCTAssertTrue(([@[@"http", @"https"] containsObject:opened.scheme]));')
        expression=line[len('XCTAssertTrue('):-2]
        result=self.preprocess(expression)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('containsObject:opened.scheme',result.stdout)
        self.assertEqual(HOSTED.count('- (void)test'),7)
        self.assertIn('XCTAssertEqual(opens, 1); XCTAssertNotNil(opened.host);',HOSTED)
        self.assertIn('XCTAssertNil([self ownedView:@"history.result.open" inView:result.view]);',HOSTED)

    def test_every_new_hosted_assertion_first_argument_survives_c_macro_grouping(self):
        import re
        count=0
        for match in re.finditer(r'\bXCT(?:Assert\w+|Fail)\s*\(',HOSTED):
            # The C preprocessor groups parentheses, not ObjC square brackets.
            # Read its actual first argument and require balanced ObjC brackets.
            depth=1;quote=None;escaped=False;square=brace=0
            for c in HOSTED[match.end():]:
                if quote:
                    if escaped:escaped=False
                    elif c=='\\':escaped=True
                    elif c==quote:quote=None
                    continue
                if c in {'"',"'"}:quote=c;continue
                if c=='(':depth+=1
                elif c==')':
                    depth-=1
                    if depth==0:break
                elif c==',' and depth==1:break
                if c=='[':square+=1
                elif c==']':square-=1
                elif c=='{':brace+=1
                elif c=='}':brace-=1
                self.assertGreaterEqual(square,0)
                self.assertGreaterEqual(brace,0)
            self.assertEqual(square,0,match.group(0))
            self.assertEqual(brace,0,match.group(0));self.assertIsNone(quote)
            count+=1
        self.assertGreater(count,40)


class PhoneOnePixelScrollRequestTests(unittest.TestCase):
    """Execute the exact helper's C math, with public rectangle/scroll stubs.

    This proves request predicates and fail-closed calls, not UIKit scrolling.
    The 36 bounded geometry rows below contain no decoded payload content.
    """
    @classmethod
    def setUpClass(cls):
        import ctypes
        import shutil
        import subprocess
        import tempfile
        cls.ctypes = ctypes
        cls.helper = '// Keep strict containment of the original content target;' + HOSTED.split(
            '// Keep strict containment of the original content target;', 1)[1].split(
            '- (void)testLargestDynamicTypeFullTextAndActionsInBoundedPublicScrollPanes {', 1)[0]
        body = cls.helper.split('inScroll:(UIScrollView *)scroll {', 1)[1].rsplit('}', 1)[0]
        body = body.replace('scroll.traitCollection.displayScale', 'scroll->displayScale')
        body = body.replace('scroll.bounds', 'scroll->bounds').replace('scroll.contentSize', 'scroll->contentSize')
        body = body.replace('[scroll scrollRectToVisible:request animated:NO];',
                            'scrolls += 1; last_request = request;')
        program = '''#include <math.h>
typedef double CGFloat;
typedef int BOOL;
typedef struct { double x, y; } CGPoint;
typedef struct { double width, height; } CGSize;
typedef struct { CGPoint origin; CGSize size; } CGRect;
typedef struct { double displayScale; CGRect bounds; CGSize contentSize; } Scroll;
static int failures, scrolls;
static CGRect last_request;
static CGRect CGRectInset(CGRect r, double dx, double dy) {
    return (CGRect){{r.origin.x + dx, r.origin.y + dy},
                    {r.size.width - 2 * dx, r.size.height - 2 * dy}};
}
static double CGRectGetMinX(CGRect r) { return r.origin.x; }
static double CGRectGetMinY(CGRect r) { return r.origin.y; }
static double CGRectGetMaxX(CGRect r) { return r.origin.x + r.size.width; }
static double CGRectGetMaxY(CGRect r) { return r.origin.y + r.size.height; }
#define XCTAssertTrue(condition, ...) do { if (!(condition)) failures += 1; } while (0)
static void exact_helper(CGRect original, Scroll *scroll) {
''' + body + '''
}
int pixel_request(double x, double y, double w, double h,
                  double vw, double vh, double cw, double ch,
                  double scale, double *out) {
    Scroll scroll = {scale, {{0, 0}, {vw, vh}}, {cw, ch}};
    failures = 0; scrolls = 0; last_request = (CGRect){{0, 0}, {0, 0}};
    exact_helper((CGRect){{x, y}, {w, h}}, &scroll);
    out[0] = last_request.origin.x; out[1] = last_request.origin.y;
    out[2] = last_request.size.width; out[3] = last_request.size.height;
    out[4] = failures; return scrolls;
}
'''
        compiler = shutil.which('cc')
        if not compiler:
            raise RuntimeError('The standard C compiler is required for the exact request predicates')
        cls.folder = tempfile.TemporaryDirectory(prefix='phone-one-pixel-')
        cls.addClassCleanup(cls.folder.cleanup)
        library = Path(cls.folder.name) / 'one-pixel.so'
        result = subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                                 '-shared', '-fPIC', '-x', 'c', '-', '-o', str(library), '-lm'],
                                input=program, capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise RuntimeError('Exact helper predicate compilation failed: ' + result.stderr)
        cls.library = ctypes.CDLL(str(library))
        cls.request = cls.library.pixel_request
        cls.request.argtypes = [ctypes.c_double] * 9 + [ctypes.POINTER(ctypes.c_double)]
        cls.request.restype = ctypes.c_int

    def execute(self, target, viewport, content, scale):
        out = (self.ctypes.c_double * 5)()
        count = self.request(*target, *viewport, *content, scale, out)
        return count, list(out[:4]), int(out[4])

    def reject(self, target, viewport, content, scale):
        count, request, failures = self.execute(target, viewport, content, scale)
        self.assertEqual(count, 0, 'A rejected request must perform no scroll')
        self.assertEqual(failures, 1, 'A rejected request remains a failing XCTest assertion')
        self.assertEqual(request, [0, 0, 0, 0])

    def test_all36_retained_requests_execute_exact_one_pixel_predicates(self):
        rows = RECORDED_PHONE_SCROLL_REQUESTS
        self.assertEqual(len(rows), 36)
        self.assertEqual(hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest(),
                         '8ec9fc50621c0df387bbb946a913cbc1436fea7f441dd4e13eb39b0fae67d7f7')
        self.assertEqual({tuple(row[:3]) for row in rows},
                         {(kind, width, height) for kind in ['text', 'website']
                          for width, height in [(320, 568), (375, 667), (440, 956), (568, 320)]})
        for kind, width, height, stage, target, viewport, content, scale in rows:
            with self.subTest(kind=kind, size=(width, height), stage=stage):
                count, request, failures = self.execute(target, viewport, content, scale)
                self.assertEqual((count, failures), (1, 0))
                margin = 1 / scale
                self.assertEqual(request, [target[0], target[1] - margin,
                                           target[2], target[3] + 2 * margin])
                self.assertLess(request[1], target[1])
                self.assertGreater(request[1] + request[3], target[1] + target[3])

    def test_invalid_and_nonfinite_actual_display_scales_fail_without_scroll(self):
        for scale in [0, -1, 0.5, float('nan'), float('inf'), -float('inf')]:
            with self.subTest(scale=scale):
                self.reject([20, 100, 280, 80], [320, 256], [320, 396], scale)
        for scale in [1, 2, 3]:
            count, request, failures = self.execute([20, 100, 280, 80], [320, 256], [320, 396], scale)
            self.assertEqual((count, failures), (1, 0))
            self.assertEqual(request[3], 80 + 2 / scale)

    def test_oversized_and_margin_too_tall_requests_fail_without_scroll(self):
        for target in [[20, 100, 321, 80], [20, 100, 280, 256],
                       [20, 100, 280, 255.5], [20, 100, 0, 80]]:
            with self.subTest(target=target):
                self.reject(target, [320, 256], [400, 1000], 3)

    def test_missing_content_padding_is_not_clamped_or_retried(self):
        for target in [[20, 0, 280, 80], [20, 316, 280, 80],
                       [-0.000001, 100, 280, 80], [40.000001, 100, 280, 80]]:
            with self.subTest(target=target):
                self.reject(target, [320, 256], [320, 396], 3)

    def test_meaningful_original_target_overflow_and_nonfinite_geometry_stay_red(self):
        for target in [[20, -0.000001, 280, 80], [20, 316.000001, 280, 80],
                       [20, 100, 320.000001, 80], [20, 100, 280, 256.000001],
                       [float('nan'), 100, 280, 80], [20, float('inf'), 280, 80],
                       [20, 100, float('inf'), 80], [20, 100, 280, float('nan')]]:
            with self.subTest(target=target):
                self.reject(target, [320, 256], [320, 396], 3)

    def test_exact_native_helper_calls_and_all_original_assertions_are_preserved(self):
        self.assertEqual(hashlib.sha256(self.helper.encode()).hexdigest(),
                         '685f494417ac8d43ca8635cdf793264feb19fae9cd6fe3cd6a03e6a83b409745')
        self.assertEqual(HOSTED.count('#include <math.h>'), 1)
        restored = HOSTED.replace('#include <math.h>\n', '', 1).replace(self.helper, '', 1)
        calls = [('[self scrollOriginalRectWithOnePixelMargin:beginning inScroll:text];',
                  '[text scrollRectToVisible:beginning animated:NO];'),
                 ('[self scrollOriginalRectWithOnePixelMargin:ending inScroll:text];',
                  '[text scrollRectToVisible:ending animated:NO];'),
                 ('[self scrollOriginalRectWithOnePixelMargin:rect inScroll:actions];',
                  '[actions scrollRectToVisible:rect animated:NO];')]
        for replacement, original in calls:
            self.assertEqual(HOSTED.count(replacement), 1)
            restored = restored.replace(replacement, original, 1)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         'd0767447fc15c6b2ff534f03369c9109af933816cdea94cf003d1c0cb6246bee',
                         'Every original native assertion, target, payload, lifecycle and Copy/Open call stays exact')
        self.assertEqual(HOSTED.count('- (void)test'), 7)
        self.assertEqual(self.helper.count('[scroll scrollRectToVisible:request animated:NO];'), 1)
        for forbidden in ['CoreFoundation', 'stdio.h', 'QRDiagnostic', 'attachGeometry', 'XCTAttachment',
                          'printf(', 'NSLog(', 'nextafter', 'setContentOffset', 'continueAfterFailure =']:
            self.assertNotIn(forbidden, HOSTED)


# Exact condensed36 public requests from run37362944625/source6156deb7.
# Numeric rectangles only; no diagnostic recorder, schema or payload data.
RECORDED_PHONE_SCROLL_REQUESTS = [
    ['text', 320, 568, 'beginning', [20, 103, 280, 63.248046875], [320, 290], [320, 20212.333333333332], 3],
    ['text', 320, 568, 'ending', [20, 20129.085286458332, 280, 63.248046875], [320, 290], [320, 20212.333333333332], 3],
    ['text', 320, 568, 'history.result.copy', [20, 8, 280, 142], [320, 246], [320, 246], 3],
    ['text', 320, 568, 'history.result.cancel', [20, 158, 280, 80], [320, 246], [320, 246], 3],
    ['text', 375, 667, 'beginning', [20, 103, 335, 63.248046875], [375, 451], [375, 20150.333333333332], 3],
    ['text', 375, 667, 'ending', [20, 20067.085286458332, 335, 63.248046875], [375, 451], [375, 20150.333333333332], 3],
    ['text', 375, 667, 'history.result.copy', [20, 8, 335, 80], [375, 184], [375, 184], 3],
    ['text', 375, 667, 'history.result.cancel', [20, 96, 335, 80], [375, 184], [375, 184], 3],
    ['text', 440, 956, 'beginning', [20, 103, 400, 63.248046875], [440, 740], [440, 15128.333333333334], 3],
    ['text', 440, 956, 'ending', [20, 15045.085286458334, 400, 63.248046875], [440, 740], [440, 15128.333333333334], 3],
    ['text', 440, 956, 'history.result.copy', [20, 8, 400, 80], [440, 184], [440, 184], 3],
    ['text', 440, 956, 'history.result.cancel', [20, 96, 400, 80], [440, 184], [440, 184], 3],
    ['text', 568, 320, 'beginning', [20, 103, 528, 63.248046875], [568, 144], [568, 10168.333333333334], 3],
    ['text', 568, 320, 'ending', [20, 10085.085286458334, 528, 63.248046875], [568, 144], [568, 10168.333333333334], 3],
    ['text', 568, 320, 'history.result.copy', [20, 8, 528, 80], [568, 144], [568, 184], 3],
    ['text', 568, 320, 'history.result.cancel', [20, 96, 528, 80], [568, 144], [568, 184], 3],
    ['website', 320, 568, 'beginning', [20, 103, 280, 63.248046875], [320, 280.3333333333333], [320, 12648.333333333334], 3],
    ['website', 320, 568, 'ending', [20, 12565.085286458334, 280, 63.248046875], [320, 280.3333333333333], [320, 12648.333333333334], 3],
    ['website', 320, 568, 'history.result.open', [20, 8, 280, 142], [320, 255.66666666666666], [320, 396], 3],
    ['website', 320, 568, 'history.result.copy', [20, 158, 280, 142], [320, 255.66666666666666], [320, 396], 3],
    ['website', 320, 568, 'history.result.cancel', [20, 308.00000000000006, 280, 80], [320, 255.66666666666666], [320, 396], 3],
    ['website', 375, 667, 'beginning', [20, 103, 335, 63.248046875], [375, 335], [375, 10168.333333333334], 3],
    ['website', 375, 667, 'ending', [20, 10085.085286458334, 335, 63.248046875], [375, 335], [375, 10168.333333333334], 3],
    ['website', 375, 667, 'history.result.open', [20, 8, 335, 142], [375, 300], [375, 334], 3],
    ['website', 375, 667, 'history.result.copy', [20, 158, 335, 80], [375, 300], [375, 334], 3],
    ['website', 375, 667, 'history.result.cancel', [20, 246, 335, 80], [375, 300], [375, 334], 3],
    ['website', 440, 956, 'beginning', [20, 103, 400, 63.248046875], [440, 652], [440, 8680.333333333334], 3],
    ['website', 440, 956, 'ending', [20, 8597.085286458334, 400, 63.248046875], [440, 652], [440, 8680.333333333334], 3],
    ['website', 440, 956, 'history.result.open', [20, 8, 400, 80], [440, 272], [440, 272], 3],
    ['website', 440, 956, 'history.result.copy', [20, 96, 400, 80], [440, 272], [440, 272], 3],
    ['website', 440, 956, 'history.result.cancel', [20, 184, 400, 80], [440, 272], [440, 272], 3],
    ['website', 568, 320, 'beginning', [20, 103, 528, 63.248046875], [568, 144], [568, 6572.333333333333], 3],
    ['website', 568, 320, 'ending', [20, 6489.085286458333, 528, 63.248046875], [568, 144], [568, 6572.333333333333], 3],
    ['website', 568, 320, 'history.result.open', [20, 8, 528, 80], [568, 144], [568, 272], 3],
    ['website', 568, 320, 'history.result.copy', [20, 96, 528, 80], [568, 144], [568, 272], 3],
    ['website', 568, 320, 'history.result.cancel', [20, 184, 528, 80], [568, 144], [568, 272], 3],
]


if __name__ == '__main__':
    unittest.main()
