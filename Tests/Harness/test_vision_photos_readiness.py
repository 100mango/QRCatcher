"""Selector/source contracts; only native XCTest can qualify picker readiness."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'QRCatcherVisionUITests/QRCatcherVisionUITests.swift').read_text()
HELPER = SOURCE.split('private func readyNativePhotoAsset()', 1)[1].split('func testRealPhotosImportCopyAndReopen()', 1)[0]


class VisionPhotosReadinessContracts(unittest.TestCase):
    def test_only_observed_native_viewport_and_nested_asset_are_queried(self):
        self.assertIn('app.scrollViews.matching(identifier: "photosView_content_scroll_view")', HELPER)
        self.assertIn('let asset = grid.images["PXGGridLayout-Info"].firstMatch', HELPER)
        self.assertNotIn('app.images["PXGGridLayout-Info"]', SOURCE)
        self.assertNotIn('navigationBars["Photos"]', HELPER)
        self.assertNotIn('navigationBars["照片"]', HELPER)

    def test_same_twenty_second_wait_is_passive_and_failure_stops_selection(self):
        self.assertIn('NSPredicate(format: "exists == true AND hittable == true"), object: asset', HELPER)
        self.assertIn('await XCTWaiter.fulfillment(of: [ready], timeout: 20)', HELPER)
        self.assertIn('guard outcome == .completed else {', HELPER)
        self.assertIn('guard grids.count == 1, grid.exists, asset.exists, asset.isHittable else {', HELPER)
        self.assertEqual(HELPER.count('return nil'), 2)
        for action in ['.tap(', '.swipe', 'Thread.sleep', 'debugDescription', 'coordinate(']: self.assertNotIn(action, HELPER)
        self.assertEqual(SOURCE.count('guard let asset = await readyNativePhotoAsset() else { return }'), 2)
        for name in ['testRealPhotosImportCopyAndReopen', 'testChineseEmptyPhotosResultAndOfflinePolicy']:
            case = SOURCE.split('func ' + name + '()', 1)[1].split('\n    }', 1)[0]
            self.assertLess(case.index('guard let asset = await readyNativePhotoAsset() else { return }'), case.index('asset.tap()'))

    def test_positive_and_wrong_context_fixture_matrix(self):
        # The model exercises the exact documented query scope, not UIKit/AX.
        def query(grids, unscoped_images=()):
            matches = [grid for grid in grids if grid['id'] == 'photosView_content_scroll_view']
            if len(matches) != 1 or not matches[0].get('exists', True): return False
            assets = [asset for asset in matches[0]['images'] if asset['id'] == 'PXGGridLayout-Info']
            return bool(assets and assets[0].get('exists') and assets[0].get('hittable'))
        asset = {'id': 'PXGGridLayout-Info', 'exists': True, 'hittable': True}
        good = {'id': 'photosView_content_scroll_view', 'images': [asset]}
        self.assertTrue(query([good]))
        self.assertFalse(query([], [asset]))
        self.assertFalse(query([{'id': 'unrelated_scroll', 'images': [asset]}]))
        self.assertFalse(query([{'id': good['id'], 'images': []}], [asset]))
        self.assertFalse(query([good, good]))
        self.assertFalse(query([{**good, 'exists': False}]))
        for mutation in [{'exists': False}, {'hittable': False}, {'id': 'other-image'}]:
            self.assertFalse(query([{**good, 'images': [{**asset, **mutation}]}]))


if __name__ == '__main__':
    unittest.main()
