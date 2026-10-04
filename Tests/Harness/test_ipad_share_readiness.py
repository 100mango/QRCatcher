"""Native share selector/geometry source contracts; Apple runtime still required."""
from pathlib import Path
import math
import unittest

SOURCE = (Path(__file__).resolve().parents[2] / 'QRCatcherUITests/QRCatcherPadUITests.m').read_text()
CASE = SOURCE.split('- (void)testSplitSelectionRotationAndAnchoredShare {', 1)[1].split('- (void)testRealPhotoImport', 1)[0]


class IPadShareReadinessTests(unittest.TestCase):
    def test_observed_native_context_and_cell_role_are_mandatory(self):
        for token in ['self.app.popovers containingType:XCUIElementTypeOther identifier:@"ActivityListView"',
                      'activity.otherElements[@"LP.CaptionBar.BottomCaption"]',
                      'activity.cells matchingPredicate:', '@"actionGroupCell", @"Copy"',
                      'popovers.count == 1', '[caption.label isEqualToString:@"Native iPad QR result 你好"]',
                      'copy.exists && copy.enabled && copy.hittable']:
            self.assertIn(token, CASE)
        self.assertNotIn('self.app.buttons[@"Copy"]', CASE)

    def test_one_passive_ten_second_wait_guards_capture_and_dismiss(self):
        predicate = CASE.split('NSPredicate *shareReady = ', 1)[1].split('NSTimeInterval readinessStarted', 1)[0]
        for token in [' tap]', 'swipe', 'sleep', 'debugDescription']: self.assertNotIn(token, predicate)
        self.assertIn('[XCTWaiter waitForExpectations:@[ready] timeout:10]', CASE)
        self.assertIn('if (readiness != XCTWaiterResultCompleted) return;', CASE)
        self.assertIn('if (!currentReady) return;', CASE)
        self.assertIn('if (!anchored) return;', CASE)
        self.assertLess(CASE.index('if (!anchored) return;'), CASE.index('[self capture:@"ipad-anchored-share"]'))
        self.assertIn('IPAD_NATIVE_SHARE_READINESS outcome=%ld elapsed=%.3f', CASE)

    def test_dismissal_and_original_payload_reopen_assertions_remain(self):
        self.assertIn('[history.cells.firstMatch tap];\n    XCTNSPredicateExpectation *dismissed', CASE)
        self.assertIn('[XCTWaiter waitForExpectations:@[dismissed] timeout:5]', CASE)
        self.assertIn('if (dismissal != XCTWaiterResultCompleted) return;', CASE)
        self.assertEqual(CASE.count('XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, @"Native iPad QR result 你好")'), 3)

    def test_observed_geometry_and_wrong_context_fixtures_fail_closed(self):
        def contains(outer, inner):
            x,y,w,h=outer;a,b,c,d=inner
            return w>0 and h>0 and c>0 and d>0 and x<=a and y<=b and a+c<=x+w and b+d<=y+h
        def qualifies(window, popover, anchor, copy, count=1, caption=True, role='Cell', enabled=True, hittable=True):
            if any(not all(math.isfinite(v) for v in rect) or rect[2]<=0 or rect[3]<=0 for rect in [window,popover,anchor,copy]):return False
            x,y,w,h=popover;a,b,c,d=anchor
            vertical=min(x+w,a+c)>max(x,a) and (y+h<=b or y>=b+d)
            horizontal=min(y+h,b+d)>max(y,b) and (x+w<=a or x>=a+c)
            return count==1 and caption and role=='Cell' and enabled and hittable and contains(window,popover) and contains(window,anchor) and contains(popover,copy) and (vertical or horizontal)
        observed=((0,0,1376,1032),(691,554,375,372),(396,926,964,44),(709,779.5,82,133.5))
        self.assertTrue(qualifies(*observed))
        for mutation in [{'count':0},{'count':2},{'caption':False},{'role':'Button'},{'enabled':False},{'hittable':False}]:
            self.assertFalse(qualifies(*observed,**mutation))
        self.assertFalse(qualifies(observed[0],(1200,554,375,372),observed[2],observed[3]))
        self.assertFalse(qualifies(observed[0],observed[1],(0,926,40,44),observed[3]))
        self.assertFalse(qualifies(observed[0],observed[1],observed[2],(709,900,82,133.5)))
        # Source-consistent alternate placements; not claims of observed UIKit
        # layouts for these synthetic rectangle fixtures.
        self.assertTrue(qualifies(observed[0],(691,130,375,372),(396,80,964,44),(709,355.5,82,133.5)))
        self.assertTrue(qualifies(observed[0],(500,300,375,372),(900,450,44,80),(518,525.5,82,133.5)))
        self.assertTrue(qualifies(observed[0],(960,300,375,372),(900,450,44,80),(978,525.5,82,133.5)))
        self.assertTrue(qualifies(observed[0],(100,300,375,372),(0,700,1000,44),(118,525.5,82,133.5)))
        for rect in [(float('nan'),554,375,372),(691,554,float('inf'),372),(691,554,0,372)]:
            self.assertFalse(qualifies(observed[0],rect,observed[2],observed[3]))
        self.assertIn('(verticalSide || horizontalSide)', CASE)
        self.assertNotIn('CGRectGetMidX(anchor)', CASE)
        self.assertNotIn('CGRectGetMidY(anchor)', CASE)
        self.assertIn('QRPadFiniteNonemptyRect(copyFrame)', CASE)


if __name__ == '__main__':
    unittest.main()
