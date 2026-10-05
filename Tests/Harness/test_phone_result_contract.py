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


if __name__ == '__main__':
    unittest.main()
