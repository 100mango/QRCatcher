"""Exact exporter contracts and source checks, not native accessibility proof."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TREE = ast.parse((ROOT / 'scripts/export_ios_platform_screenshots.py').read_text())
FUNCTIONS = [node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == 'missing_import_audit_pairs']
NAMESPACE = {}
exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), '<exact-import-audit-export>', 'exec'), NAMESPACE)
missing = NAMESPACE['missing_import_audit_pairs']
SOURCE = (ROOT / 'QRCatcherUITests/QRCatcherImageImportUITests.m').read_text()


class ImportAuditPairTests(unittest.TestCase):
    def evidence(self, label='SE3-imports'):
        before = 'image-import-real-files' if label.endswith('-files') else 'image-import-real-photos'
        images = [{'result_label': label, 'checkpoint': name} for name in [before, 'image-import-history-after-cancel']]
        texts = [{'result_label': label, 'checkpoint': name} for name in
                 ['image-import-result-audit-tree', 'image-import-history-audit-tree', 'image-import-audit-pair-receipts']]
        return images, texts

    def test_both_case_scoped_frames_trees_and_receipts_required(self):
        for label in ['SE3-imports', 'SE3-files', 'pro-max-imports', 'pro-max-files']:
            images, texts = self.evidence(label)
            self.assertEqual(missing([label], images, texts, [label]), [])
            for index in range(len(images)):
                self.assertTrue(missing([label], images[:index] + images[index + 1:], texts, [label]))
            for index in range(len(texts)):
                self.assertTrue(missing([label], images, texts[:index] + texts[index + 1:], [label]))

    def test_other_import_result_cannot_supply_missing_after_frame(self):
        images, texts = self.evidence()
        images[1]['result_label'] = 'pro-max-imports'
        self.assertTrue(missing(['SE3-imports'], images, texts))

    def test_produced_result_requires_pair_receipt_even_when_no_pixels(self):
        self.assertTrue(missing([], [], [], ['SE3-imports']))

    def test_unknown_or_duplicate_requirement_fails(self):
        for labels in [['SE3-imports', 'SE3-imports'], ['ipad-mini']]:
            with self.assertRaises(ValueError):
                missing(labels, [], [])

    def test_only_audits_continue_and_raw_failure_counts_stay_separate(self):
        audit = SOURCE.split('- (NSDictionary *)auditCurrentResultPhase:', 1)[1].split('- (void)attachBoundedText:', 1)[0]
        self.assertIn('self.continueAfterFailure = YES', audit)
        self.assertIn('@finally { self.continueAfterFailure = previousContinuation; }', audit)
        self.assertIn('return NO;', audit)
        self.assertIn('XCTAssertTrue(apiReturnedSuccess', audit)
        for key in ['callback_issues', 'registered_failure_delta', 'api_returned_success']:
            self.assertIn('@"' + key + '"', audit)
        self.assertNotIn('return YES;', audit)

    def test_actual_cancel_ownership_and_unchanged_rows_precede_second_audit(self):
        pair = SOURCE.split('- (void)auditCurrentResult {', 1)[1].split('- (void)chooseSource:', 1)[0]
        self.assertIn('XCUIElement *cancel = result.buttons[@"history.result.cancel"]', pair)
        self.assertIn('cancel.exists && cancel.enabled && cancel.hittable', pair)
        self.assertLess(pair.index('if (!canCancel) return'), pair.index('[cancel tap]'))
        self.assertLess(pair.index('if (![after isEqual:before]) return'), pair.index('@"same-history-after-cancel"'))
        self.assertIn('XCTAssertEqualObjects(after, before', pair)
        self.assertIn('if (closeResult != XCTWaiterResultCompleted) return', pair)


if __name__ == '__main__':
    unittest.main()
