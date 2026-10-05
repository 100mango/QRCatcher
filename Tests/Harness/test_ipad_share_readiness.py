"""Native share selector/geometry source contracts; Apple runtime still required."""
from pathlib import Path
import math
import ast,contextlib,copy,io,json,os,re,runpy,subprocess,sys,tempfile
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'QRCatcherUITests/QRCatcherPadUITests.m').read_text()
CASE = SOURCE.split('- (void)testSplitSelectionRotationAndAnchoredShare {', 1)[1].split('- (void)testRealPhotoImport', 1)[0]


class IPadShareReadinessTests(unittest.TestCase):
    def test_observed_native_context_and_cell_role_are_mandatory(self):
        for token in ['self.app.popovers containingType:XCUIElementTypeOther identifier:@"ActivityListView"',
                      'activity.otherElements[@"LP.CaptionBar.BottomCaption"]',
                      'activity.cells matchingIdentifier:@"actionGroupCell"', 'containingPredicate:',
                      'XCUIElementTypeStaticText, @"cellTitleLabel", @"Copy"', 'NSUInteger count = copyCells.count',
                      'NSUInteger count = popovers.count', '[value isEqualToString:@"Native iPad QR result 你好"]',
                      'return copy.exists;', 'return copy.enabled;', 'return copy.hittable;']:
            self.assertIn(token, CASE)
        self.assertNotIn('self.app.buttons[@"Copy"]', CASE)

    def test_both_retained_copy_cell_forms_use_the_same_owned_descendant(self):
        def matches(cell):
            return cell['activity'] == 'selected-ActivityListView' and cell['role'] == 'Cell' and cell['identifier'] == 'actionGroupCell' and any(
                child['role'] == 'StaticText' and child['identifier'] == 'cellTitleLabel' and child['label'] == 'Copy'
                for child in cell['descendants'])
        title = {'role': 'StaticText', 'identifier': 'cellTitleLabel', 'label': 'Copy'}
        for own_label in ['Copy', '']:
            cell = {'activity': 'selected-ActivityListView', 'role': 'Cell', 'identifier': 'actionGroupCell', 'label': own_label, 'descendants': [title]}
            self.assertTrue(matches(cell))
            for key, value in [('activity', 'unrelated-ActivityListView'), ('role', 'Button'), ('identifier', 'shareCell'), ('descendants', [])]:
                self.assertFalse(matches({**cell, key: value}))
            for key, value in [('role', 'Button'), ('identifier', 'unrelatedTitle'), ('label', 'Print')]:
                self.assertFalse(matches({**cell, 'descendants': [{**title, key: value}]}))
            self.assertFalse(len([item for item in [cell, cell] if matches(item)]) == 1)
        self.assertNotIn('identifier == %@ AND label == %@", @"actionGroupCell", @"Copy"', CASE)

    def test_copy_query_never_escapes_the_caption_bound_activity(self):
        query = CASE.split('XCUIElementQuery *copyCells =', 1)[1].split('NSPredicate *shareReady', 1)[0]
        self.assertIn('activity.cells matchingIdentifier:', query)
        self.assertNotIn('self.app.cells', query)
        self.assertNotIn('self.app.buttons', query)
        self.assertIn('elementType == %lu AND identifier == %@ AND label == %@', query)
        self.assertIn('NSUInteger count = copyCells.count; term[@"observed_count"] = @(count); return count == 1;', CASE)

    def test_one_passive_ten_second_wait_guards_capture_and_dismiss(self):
        predicate = CASE.split('NSPredicate *shareReady = ', 1)[1].split('// Start at the original point;', 1)[0]
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


ORDER=['popover_count','popover_exists','activity_exists','caption_exists','caption_matches','copy_count','copy_exists','copy_enabled','copy_hittable']
SCRIPT=ROOT/'scripts/export_ios_platform_screenshots.py'
defs=[node for node in ast.parse(SCRIPT.read_text()).body if isinstance(node,ast.FunctionDef) and node.name in {'validate_ipad_share_trace','is_ipad_share_trace'}]
ns={'json':json,'math':math,'re':re};exec(compile(ast.Module(body=defs,type_ignores=[]),'<exact-ipad-trace-functions>','exec'),ns)
validate=ns['validate_ipad_share_trace'];recognizes=ns['is_ipad_share_trace']


class IPadShareDiagnosticTests(unittest.TestCase):
    def fixture(self,false_at=None,pending_at=None,index=1):
        terms={name:{'state':'not_evaluated'} for name in ORDER};active=None
        for n,name in enumerate(ORDER):
            if pending_at==n:
                terms[name]={'state':'entered','started':n/10};active=name;break
            term={'state':'completed','started':n/10,'finished':n/10+.05,'result':n!=false_at}
            if name in {'popover_count','copy_count'}:term['observed_count']=0 if n==false_at else 1
            if name=='caption_matches':term['caption_utf8_bytes']=31
            terms[name]=term
            if n==false_at:break
        attempt={'index':index,'terms':terms,'active_term':active,'predicate_returned':pending_at is None,'ready':None if pending_at is not None else false_at is None}
        return {'version':1,'timeout_seconds':10,'observations_qualify_pass':False,'retained_attempt_limit':2,'attempt_count':index,
                'term_order':ORDER,'attempts':[attempt],'waiter_result':None if pending_at is not None else 2 if false_at is not None else 1,'wait_elapsed':None if pending_at is not None else 10.260}

    def encoded(self,value):return json.dumps(value,separators=(',',':')).encode()

    def test_every_first_false_leaves_later_conditions_unknown(self):
        for index in range(9):
            value=self.fixture(false_at=index);self.assertEqual(validate(self.encoded(value)),value)
            for later in ORDER[index+1:]:self.assertEqual(value['attempts'][0]['terms'][later],{'state':'not_evaluated'})

    def test_each_inflight_getter_retains_unknown_truth(self):
        for index in range(9):
            value=self.fixture(pending_at=index);self.assertEqual(validate(self.encoded(value)),value)
            self.assertIsNone(value['attempts'][0]['ready'])

    def test_success_late_completion_and_two_retained_attempts_are_diagnostic_only(self):
        value=self.fixture();self.assertEqual(validate(self.encoded(value)),value)
        # A native waiter timeout may coexist with a later true predicate;
        # observations never rewrite the native wait result into a pass.
        value['waiter_result']=2;value['wait_elapsed']=12.4
        self.assertEqual(validate(self.encoded(value)),value)
        value=self.fixture(index=8);value['attempts']=[self.fixture(false_at=0,index=7)['attempts'][0],value['attempts'][0]]
        self.assertLess(len(self.encoded(value)),4096);self.assertEqual(validate(self.encoded(value)),value)

    def test_unknown_or_pending_cannot_be_misreported_as_false_or_pass(self):
        for index in range(9):
            value=self.fixture(pending_at=index);value['attempts'][0]['terms'][ORDER[index]]['result']=False
            with self.assertRaises(ValueError):validate(self.encoded(value))
        value=self.fixture(false_at=1);value['attempts'][0]['terms']['copy_hittable']['result']=False
        with self.assertRaises(ValueError):validate(self.encoded(value))
        value=self.fixture(pending_at=0);value['attempts'][0].update(predicate_returned=True,ready=False,active_term=None);value['attempts'][0]['terms']['popover_count']={'state':'not_evaluated'}
        with self.assertRaises(ValueError):validate(self.encoded(value))
        value=self.fixture();value['observations_qualify_pass']=True
        with self.assertRaises(ValueError):validate(self.encoded(value))

    def test_wrong_count_order_timing_duplicates_and_budget_fail_closed(self):
        values=[]
        value=self.fixture();value['attempts'][0]['terms']['copy_count']['observed_count']=2;values.append(value)
        value=self.fixture();value['attempts'][0]['terms']['copy_exists']['finished']=-1;values.append(value)
        value=self.fixture(false_at=0);value['attempts'][0]['terms']['copy_hittable']={'state':'completed','result':True,'started':1,'finished':2};values.append(value)
        value=self.fixture();value['attempts']*=2;value['attempt_count']=2;values.append(value)
        value=self.fixture();value['attempts']*=3;values.append(value)
        value=self.fixture();value['wait_elapsed']=float('nan');values.append(value)
        value=self.fixture();value['extra']='x'*4096;values.append(value)
        for value in values:
            with self.assertRaises(ValueError):validate(self.encoded(value))

    def test_source_keeps_exact_getter_count_order_and_original_wait_recheck(self):
        predicate=CASE.split('NSPredicate *shareReady =',1)[1].split('// Start at the original point;',1)[0]
        calls=re.findall(r'QRPadObserveShareTerm\(attempt, @"([a-z_]+)"',predicate)
        self.assertEqual(calls,ORDER)
        for getter in ['popovers.count','popover.exists','activity.exists','caption.exists','caption.label','copyCells.count','copy.exists','copy.enabled','copy.hittable']:
            self.assertEqual(predicate.count(getter),1,getter)
        for token in ['debugDescription','snapshot',' tap]','swipe','sleep']:
            self.assertNotIn(token,predicate)
        self.assertEqual(predicate.count('}) &&'),8)
        self.assertIn('[XCTWaiter waitForExpectations:@[ready] timeout:10]',CASE)
        self.assertIn('BOOL currentReady = [shareReady evaluateWithObject:nil]',CASE)
        self.assertLess(CASE.index('observeReadiness = NO;'),CASE.index('BOOL currentReady'))
        self.assertIn('attempts.count > 2',CASE)
        self.assertIn('data.length > 4096',SOURCE)
        self.assertIn('if (!attempt) return read(nil);',SOURCE)
        self.assertIn('if (readiness != XCTWaiterResultCompleted) return;',CASE)
        self.assertIn('if (!currentReady) return;',CASE)
        self.assertIn('if (!anchored) return;',CASE)

    def export(self,scope='ipad_pro',*,duplicate=False,escape=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'scripts').mkdir();(root/'scripts/evidence-allocation.json').write_text(json.dumps({'scope_limits_bytes':{scope:2000000}}))
            result='MiniUIResults-layout.xcresult' if scope=='ipad_mini' else 'PadUIResults-layout.xcresult'
            (root/result).mkdir();(root/result/'Info.plist').write_text('fixture')
            payload=self.encoded(self.fixture(pending_at=7));calls=[]
            def run(args,**kwargs):
                calls.append(args)
                if args[1:5]==['xcresulttool','get','test-results','summary']:return subprocess.CompletedProcess(args,0,json.dumps({'result':'Failed','failedTests':1}),'')
                if args[1:4]==['xcresulttool','export','attachments']:
                    destination=Path(args[-1]);destination.mkdir(parents=True,exist_ok=True)
                    (destination/'trace.json').write_bytes(payload)
                    row={'exportedFileName':'../../escape.json' if escape else 'trace.json',
                         'suggestedHumanReadableName':'ipad-share-readiness-trace_0_C17CB4FC-D16E-4FA8-9551-EDA6E400A4D2.json'}
                    (destination/'manifest.json').write_text(json.dumps([row]*(2 if duplicate else 1)))
                    return subprocess.CompletedProcess(args,0,'','')
                raise AssertionError(args)
            old=Path.cwd();sys.path.insert(0,str(ROOT/'scripts'))
            try:
                os.chdir(root)
                with patch.dict(os.environ,{'EVIDENCE_SCOPE':scope},clear=True),patch('subprocess.check_output',return_value='a'*40+'\n'),patch('subprocess.run',side_effect=run),contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(str(SCRIPT),run_name='__main__')
                summary=json.loads((root/'build/ios-platform-evidence/manifest.json').read_text());rows=summary['ipad_share_traces'];self.assertEqual(len(rows),1)
                self.assertEqual((root/'build/ios-platform-evidence'/rows[0]['name']).read_bytes(),payload)
                self.assertFalse(rows[0]['observations_qualify_pass']);self.assertEqual(len(calls),2)
            finally:os.chdir(old);sys.path.remove(str(ROOT/'scripts'))

    def test_exact_native_metadata_shape_is_retained_for_both_ipad_rows(self):
        for scope in ['ipad_pro','ipad_mini']:self.export(scope)

    def test_duplicate_wrong_scope_and_escaped_diagnostic_are_rejected(self):
        for options in [dict(duplicate=True),dict(scope='iphone_pro'),dict(escape=True)]:
            with self.assertRaises(ValueError):self.export(**options)

    def test_only_exact_or_observed_decorated_attachment_name_is_recognized(self):
        self.assertTrue(recognizes({'name':'ipad-share-readiness-trace'}))
        self.assertTrue(recognizes({'suggestedHumanReadableName':'ipad-share-readiness-trace_0_C17CB4FC-D16E-4FA8-9551-EDA6E400A4D2.json'}))
        for value in ['prefixipad-share-readiness-trace','ipad-share-readiness-trace-extra','ipad-share-readiness-trace_0_bad.json']:
            self.assertFalse(recognizes({'name':value}))


if __name__ == '__main__':unittest.main()
