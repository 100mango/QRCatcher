"""Closed offline privacy source/native contracts; no Apple runtime proof.

Default policy reads local approved copy. The exact legacy observer hashes
remain historical: only the independently pinned new privacy assertion block
is removed for those historical inputs, never arbitrary test behavior.
"""
from pathlib import Path
import hashlib
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
NATIVE_REFERENCE = {'QRCatcherTests/QRCatcherTests.m': {'all_case_names': ['testQRRoundTrip', 'testSharedCodecMatchesOriginalUIImageOracle', 'testPreviewRotationMappingAndSavedSelectionPreserveHistory', 'testSmallestHistoricalPhoneGeometryWithLargestText', 'testEmptyQR', 'testNonQRCodeImageDoesNotDecode', 'testSafeWebsiteClassification', 'testHistoryDeduplicatesAndDeletes', 'testLegacyStoreReopensWithoutLosingHistory', 'testUnreadableStoreIsNotDeleted', 'testCorruptHistoryShowsErrorAndStillAllowsCopy', 'testPrivacyHTTPFailuresAndWebProcessTerminationOfferRetry'], 'unchanged_method_sha256': {'testQRRoundTrip': '3fa24bf93bab6fe0061dd252f4f60080df94d12821c5659e0e1ffced5af4ca28', 'testSharedCodecMatchesOriginalUIImageOracle': '1c3829452b18626c95bae2783c01ffafc179002dc305e7be86603270746c54fc', 'testPreviewRotationMappingAndSavedSelectionPreserveHistory': 'de20fdbb3152a7fa199c65d3ba0a57dacb17f8ff38649f7cbb3341dadb77e58c', 'testSmallestHistoricalPhoneGeometryWithLargestText': '33f4ef52811a2a6b1b2c741523ac2cacb5fd6fd511e8454ad873083b5ce21997', 'testEmptyQR': '6b3136aa284a897ccce9079dabaa64b722be830bafad74798231f63bd5fa3546', 'testNonQRCodeImageDoesNotDecode': 'a1887e28c850a7f34d828f3462820a68051412e733137bb922a8a0c22ada1324', 'testSafeWebsiteClassification': 'ed9b9d2d200ec22e9f7f1ae4a5c7a6c90c5d10064a591d98fe9597dbfdd298da', 'testHistoryDeduplicatesAndDeletes': '5cea84fc2c4a2a2da1b071783c015186261fa3ab9d296e5207f7ad652ac3aca8', 'testLegacyStoreReopensWithoutLosingHistory': 'e57e6d9c1471978fc9f31f79e08ec54dd0a8aaa6aeb68c51c59006343866f260', 'testUnreadableStoreIsNotDeleted': '5c5360301d8989a1b4643e5595e692c91edf459b43e82c762ae37fcce8756cf2', 'testCorruptHistoryShowsErrorAndStillAllowsCopy': 'f6a181f20bd49ade5f9bb346543dab07af31ba2ce47c9c87eedb544f967268bb'}}, 'QRCatcherUITests/QRCatcherUITests.m': {'all_case_names': ['testProductionCameraAllowThenResetAndDeny', 'testProductionSceneLaunchWithoutCameraStub', 'testDeniedCameraAndEmptyHistory', 'testScannedTextPersistsAcrossRelaunchAndBackground', 'testUnreadableResultOffersRetryWithoutSaving', 'testWebsiteRequiresExplicitOpenAndCanScanAgain', 'testLargeTextLayoutKeepsControlsReachable', 'testAccessibilityOfResultAndHistory'], 'unchanged_method_sha256': {'testProductionCameraAllowThenResetAndDeny': 'c0945a6a3408d68e857ba2b575280be3a2ce997993af3d70d9a72366bf26d248', 'testProductionSceneLaunchWithoutCameraStub': 'ff12d14cf4a11dfaa4bd9b5085e0611a4a08d88cf15dd826d2221b23744aa3c7', 'testScannedTextPersistsAcrossRelaunchAndBackground': '119af95f22fd26f550cd001bd42d68d73470324e81e6055a13729c0f6c881c8e', 'testUnreadableResultOffersRetryWithoutSaving': '3c7581ab2ae350e792d6aae7442ad4ecdc9f8bc85127c55308ec28fb507d3048', 'testWebsiteRequiresExplicitOpenAndCanScanAgain': '273ff0287e6582595a91d14db8a4b68dbf7cbeebfe8f3beddb1d85bf4cb84ea6', 'testAccessibilityOfResultAndHistory': '15ebffb7fb426d093008604a3d711552d16b4ea10e2f9a7ec0460c02cbe91d44'}}, 'QRCatcherUITests/QRCatcherPadUITests.m': {'all_case_names': ['testSplitSelectionRotationAndAnchoredShare', 'testRealPhotoImportReplacesSelectionAndPreservesBothRecords', 'testLargeTextImportCancellationAndPrivacyReturn'], 'unchanged_method_sha256': {'testSplitSelectionRotationAndAnchoredShare': '0ccd8c9377397335c5331523e92e417a1ac2c66ee35ac3eec97139c494f91066', 'testRealPhotoImportReplacesSelectionAndPreservesBothRecords': '0342f1c950a5a0f780905fe189cecfd054b6968fa42211dfac792bc9d556ceb8'}}}
PAD_BLOCK_SHA256 = '4457c0e5d303b118c9fe2f18e993e7027169f1ff646b0183a355399fd38357b5'
PAD_BASE_SHA256 = 'ec3d7211c2b844af6d8320d081847990b960fe5f4af02a83db88bd552c562edf'

PAD_START = '    XCUIElement *policyBody = self.app.staticTexts[@"privacy.body"];'
PAD_END = '    [self.app.navigationBars.buttons[@"privacy.close"] tap];'


def restore_pad_for_historical_observer(text):
    if PAD_START not in text:
        return text
    if text.count(PAD_START) != 1:
        raise ValueError('Ambiguous offline privacy assertion block')
    start = text.index(PAD_START)
    end = text.index(PAD_END, start)
    block = text[start:end]
    if hashlib.sha256(block.encode()).hexdigest() != PAD_BLOCK_SHA256:
        raise ValueError('Changed admitted offline privacy assertion block')
    return text[:start] + text[end:]


def test_methods(text):
    result = {}
    for match in re.finditer(r'^- \(void\)(test\w+) \{', text, re.M):
        following = re.search(r'^- \([^\n]+\)|^@end', text[match.end():], re.M)
        end = match.end() + following.start() if following else len(text)
        result[match[1]] = text[match.start():end]
    return result


def method(text, selector):
    match = re.search(r'^- \([^\n]+\)' + re.escape(selector) + r'[^\n]*\{', text, re.M)
    if not match:
        raise ValueError('Missing owned method: ' + selector)
    following = re.search(r'^- \([^\n]+\)|^@end', text[match.end():], re.M)
    end = match.end() + following.start() if following else len(text)
    return text[match.start():end]


def default_contract(source):
    for token in ('WKWebView', 'loadRequest:', 'NSURLSession', 'NSURLConnection', 'SFSafariViewController'):
        if token in source:
            raise ValueError('Unexpected in-app network surface: ' + token)
    loaded = method(source, 'viewDidLoad')
    if 'openExternalURL:' in loaded or '[self openPolicyInBrowser]' in loaded:
        raise ValueError('Default privacy presentation opens a website')
    opened = method(source, 'openPolicyInBrowser')
    for required in ('if (self.closing || self.opening) return;', 'self.opening = YES;',
                     '[self openExternalURL:URL completion:',
                     'https://100mango.github.io/app-privacy/',
                     'if (!strongSelf || strongSelf.closing) return;'):
        if required not in opened:
            raise ValueError('Missing closed explicit opening gate')
    actual = method(source, 'openExternalURL:')
    if actual.count('[UIApplication.sharedApplication openURL:URL options:@{} completionHandler:completion]') != 1:
        raise ValueError('Owned explicit action must use the existing public browser API')
    if source.count('https://100mango.github.io/app-privacy/') != 1:
        raise ValueError('Fixed policy URL must have a unique action-owned use')


class OfflinePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT/'QRCatcher/QRPrivacyViewController.m').read_text()
        self.unit = (ROOT/'QRCatcherTests/QRCatcherTests.m').read_text()
        self.phone = (ROOT/'QRCatcherUITests/QRCatcherUITests.m').read_text()
        self.pad = (ROOT/'QRCatcherUITests/QRCatcherPadUITests.m').read_text()

    def test_approved_english_chinese_core_copy_is_exact_not_a_new_promise(self):
        shared = (ROOT/'Shared/Services/QRPrivacyText.swift').read_text()
        english = re.search(r'static let english = "([^"\n]*)"', shared)[1]
        chinese = re.search(r'static let simplifiedChinese = "([^"\n]*)"', shared)[1]
        self.assertIn('[self label:@"'+english+'" identifier:@"privacy.body"', self.source)
        localized = (ROOT/'QRCatcher/zh-Hans.lproj/Localizable.strings').read_text()
        self.assertIn('"'+english+'" = "'+chinese+'";', localized)
        self.assertIn('GitHub Pages records visitor IP addresses for security.', self.source)
        self.assertIn('System backups, file providers, the clipboard', self.source)

    def test_default_offline_and_explicit_public_browser_boundary(self):
        default_contract(self.source)
        self.assertIn('@selector(openPolicyInBrowser)', method(self.source, 'viewDidLoad'))
        for mutation in ('[self openPolicyInBrowser];', 'WKWebView *unexpected;', 'NSURLSession *unexpected;'):
            changed = self.source.replace('[super viewDidLoad];', '[super viewDidLoad]; '+mutation, 1)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                default_contract(changed)
        for before, after in [('if (self.closing || self.opening) return;', 'if (self.closing) return;'),
                              ('https://100mango.github.io/app-privacy/', 'https://example.com/'),
                              ('if (!strongSelf || strongSelf.closing) return;', 'if (!strongSelf) return;')]:
            with self.subTest(mutation=before), self.assertRaises(ValueError):
                default_contract(self.source.replace(before, after, 1))

    def test_dynamic_type_scroll_ownership_and_unchanged_close_transition_contract(self):
        for token in ('label.numberOfLines = 0;', 'label.adjustsFontForContentSizeCategory = YES;',
                      'UIColor.labelColor', 'UIFontTextStyleBody', 'UIFontTextStyleFootnote',
                      '[QRActionButton buttonWithType:UIButtonTypeSystem]', 'UIFontTextStyleHeadline',
                      'content.contentLayoutGuide', 'content.frameLayoutGuide',
                      'actionScroll.contentLayoutGuide', 'actionScroll.frameLayoutGuide'):
            self.assertIn(token, self.source)
        closing = method(self.source, 'close')
        for token in ('if (self.closing) return;', 'self.closing = YES;', 'if (cleanup) cleanup();',
                      'dismissViewControllerAnimated:YES completion:cleanup', 'presentation.transitionCoordinator'):
            self.assertIn(token, closing)
        self.assertNotIn('stopLoading', closing)

    def test_same_native_case_inventory_and_unrelated_method_bodies_remain_exact(self):
        for path, reference in NATIVE_REFERENCE.items():
            actual = test_methods((ROOT/path).read_text())
            expected = set(reference['all_case_names'])
            if path.endswith('QRCatcherTests.m'):
                expected.remove('testPrivacyHTTPFailuresAndWebProcessTerminationOfferRetry')
                expected.add('testPrivacyOfflineBodyAndExplicitBrowserActionKeepCloseIdempotent')
            self.assertEqual(set(actual), expected, path)
            for name, digest in reference['unchanged_method_sha256'].items():
                self.assertEqual(hashlib.sha256(actual[name].encode()).hexdigest(), digest, path+':'+name)
        for name, count in [('QRCatcherTests.m', 12), ('QRBoundedImageImportTests.m', 7),
                            ('QRPhoneResultTests.m', 7), ('QRWatchPhoneServiceTests.m', 4)]:
            self.assertEqual(len(test_methods((ROOT/'QRCatcherTests'/name).read_text())), count)

    def test_real_unit_action_default_no_open_pending_failure_success_and_late_close(self):
        case = test_methods(self.unit)['testPrivacyOfflineBodyAndExplicitBrowserActionKeepCloseIdempotent']
        for token in ('privacy.openedURLs.count, 0', '[open sendActionsForControlEvents:UIControlEventTouchUpInside]',
                      'privacy.openedURLs.count, 1', 'privacy.pendingCompletion(NO)', 'privacy.pendingCompletion(YES)',
                      'privacy.openedURLs.count, 3', '[privacy close]; [privacy close];', 'reopened.openedURLs.count, 0'):
            self.assertIn(token, case)
        self.assertLess(case.index('privacy.openedURLs.count, 0'), case.index('[open sendActionsForControlEvents:'))
        self.assertIn('- (void)openExternalURL:(NSURL *)URL completion:(void (^)(BOOL))completion', self.unit)
        self.assertNotIn('WKNavigationResponse', self.unit)

    def test_phone_real_external_browser_return_and_both_languages_keep_all_audits(self):
        case = test_methods(self.phone)['testDeniedCameraAndEmptyHistory']
        for token in ('[self.app.buttons[@"privacy.externalPolicy"] tap]', 'com.apple.mobilesafari',
                      'XCUIApplicationStateRunningBackgroundSuspended', '[self.app activate]',
                      '[self assertOfflinePrivacyForChinese:NO]', '[done tap]'):
            self.assertIn(token, case)
        self.assertIn('[self assertOfflinePrivacyForChinese:YES]', self.phone)
        self.assertIn('Offline privacy accessibility audit:', self.phone)
        self.assertIn('CGRectContainsRect(actions.frame, external.frame)', self.phone)
        self.assertIn('iPad largest-text offline privacy accessibility audit:', self.pad)
        self.assertIn('issueHandler:nil', self.phone)
        self.assertIn('issueHandler:nil', self.pad)
        self.assertEqual(self.pad.count(PAD_START), 1)

    def test_historical_pad_input_is_exact_and_new_privacy_block_cannot_hide_other_changes(self):
        restored = restore_pad_for_historical_observer(self.pad)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), PAD_BASE_SHA256)
        for before, after in [('issueHandler:nil error:&policyError', 'issueHandler:nil error:NULL'),
                              ('policyBeginning));', 'CGRectZero));')]:
            with self.subTest(mutation=before), self.assertRaises(ValueError):
                restore_pad_for_historical_observer(self.pad.replace(before, after, 1))
        with self.assertRaises(ValueError):
            restore_pad_for_historical_observer(self.pad+self.pad[self.pad.index(PAD_START):])
        outside = self.pad.replace('self.app.tables[@"history.table"].cells.count, 1',
                                   'self.app.tables[@"history.table"].cells.count, 0', 1)
        self.assertNotEqual(hashlib.sha256(restore_pad_for_historical_observer(outside).encode()).hexdigest(), PAD_BASE_SHA256)


if __name__ == '__main__':
    unittest.main()
