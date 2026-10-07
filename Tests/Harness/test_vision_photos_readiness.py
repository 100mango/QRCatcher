"""Native-picker source contract; fixtures are not Apple runtime proof."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'QRCatcherVisionUITests/QRCatcherVisionUITests.swift').read_text()
HELPER = SOURCE.split('private func readyNativePhotoAsset()', 1)[1].split('func testRealPhotosImportCopyAndReopen()', 1)[0]
class VisionPhotosReadinessContracts(unittest.TestCase):
    def test_owned_picker_scroll_and_unique_typed_image_are_independent_queries(self):
        self.assertIn('app.navigationBars.matching(NSPredicate(format: "identifier == %@ OR identifier == %@", "Photos", "照片"))', HELPER)
        self.assertIn('pickers.firstMatch.waitForExistence(timeout: 30), pickers.count == 1', HELPER)
        self.assertIn('app.scrollViews.matching(identifier: "photosView_content_scroll_view")', HELPER)
        self.assertIn('grids.firstMatch.waitForExistence(timeout: 30), grids.count == 1', HELPER)
        self.assertIn('app.images.matching(identifier: "PXGGridLayout-Info")', HELPER)
        self.assertIn('asset.waitForExistence(timeout: 45), images.count == 1', HELPER)
        self.assertNotIn('grid.images', HELPER); self.assertNotIn('hittable ==', HELPER)
        self.assertEqual(HELPER.count('return nil'), 3)
        self.assertLess(HELPER.index('pickers.firstMatch'), HELPER.index('grids.firstMatch'))
        self.assertLess(HELPER.index('grids.firstMatch'), HELPER.index('app.images'))
    def test_no_input_or_capture_before_ready_and_actual_payload_after_tap(self):
        for action in ['.tap(', '.swipe', 'Thread.sleep', 'debugDescription', 'coordinate(', 'capture(']: self.assertNotIn(action, HELPER)
        for name in ['testRealPhotosImportCopyAndReopen', 'testChineseEmptyPhotosResultAndOfflinePolicy']:
            case = SOURCE.split('func ' + name + '()', 1)[1].split('\n    }', 1)[0]
            self.assertLess(case.index('guard let asset = await readyNativePhotoAsset() else { return }'), case.index('asset.tap()'))
            selected = case[case.index('app.buttons["vision.photos"].tap()'):case.index('asset.tap()')]
            self.assertNotIn('capture(', selected)
            self.assertIn('XCTAssertEqual(app.staticTexts["vision.payload"].label, "QRCatcher 你好 🌈 123")', case)
        case = SOURCE.split('func testRealPhotosImportCopyAndReopen()', 1)[1].split('\n    }', 1)[0]
        for value in ['vision.copy', 'app.terminate(); app.launch()', 'vision-reopened-history', 'vision-exported-qr', 'vision-exported-history', 'saveUsingSystemFileExporter']: self.assertIn(value, case)
    def test_flat_ax_image_positive_and_missing_or_ambiguous_context_fail(self):
        def ready(pickers, scrolls, images):
            return (len(pickers) == len(scrolls) == len(images) == 1 and pickers[0] in ('Photos', '照片') and scrolls[0] == 'photosView_content_scroll_view' and images[0] == 'PXGGridLayout-Info')
        fixture = (['Photos'], ['photosView_content_scroll_view'], ['PXGGridLayout-Info'])
        self.assertTrue(ready(*fixture)); self.assertTrue(ready(['照片'], *fixture[1:]))
        for index in range(3):
            for invalid in [[], ['wrong'], fixture[index] * 2]:
                changed = list(fixture); changed[index] = invalid; self.assertFalse(ready(*changed))
if __name__ == '__main__': unittest.main()
