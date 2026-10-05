"""Source and bounded-receipt contracts, not native SwiftUI rendering tests."""
import ast
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
tree=ast.parse((ROOT/'scripts/export_mac_screenshots.py').read_text())
definitions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'validate_supporting_layout_receipt','validate_payload_transition'}]
namespace={'json':json,'hashlib':hashlib}
exec(compile(ast.Module(body=definitions,type_ignores=[]),'<exact-receipt-validators>','exec'),namespace)
validate=namespace['validate_supporting_layout_receipt']
transition=namespace['validate_payload_transition']


class MacSupportingTextTests(unittest.TestCase):
    def receipt(self,locale='en',phase='full'):
        count=1 if phase=='full' else 2
        policy='Links open only when you choose Open in Browser.' if locale=='en' else '只有点击「在浏览器中打开」才会打开链接。'
        saved=f'{count} saved on this Mac' if locale=='en' else f'本机已保存 {count} 条记录'
        return dict(locale=locale,phase=phase,contrast_qualified=False,reference_font_is_resolved_element_font=False,
                    height_proxy_used_as_acceptance=False,
                    roles=[dict(role='link-policy',text=policy),dict(role='saved-count',text=saved)])

    def transition(self,locale='en',phase='prepared'):
        before='https://example.com/qrcatcher?source=golden' if locale=='en' else 'QRCatcher 你好 🌈 123'
        payload='Long result 完整内容';raw=payload.encode();digest=hashlib.sha256(raw).hexdigest()
        value=dict(locale=locale,phase=phase,wrapper_before=before,copy_before=before,
                   expected_payload_sha256=digest,expected_payload_utf8_bytes=len(raw),raster_width=210,raster_height=210,
                   clipboard_tiff_bytes=40000,clipboard_tiff_sha256='a'*64,fixture_control_exact=True,
                   full_equality_verified=False,wrapper_identity_refresh_scope='selectable Text only')
        if phase=='copy-observed':value.update(wrapper_after=payload,copy_after_sha256=digest,copy_after_utf8_bytes=len(raw),full_equality_verified=True)
        return value

    def test_english_and_chinese_full_and_minimum_receipts(self):
        for locale in ['en','zh-Hans']:
            for phase in ['full','minimum-long-content']:
                value=self.receipt(locale,phase);self.assertEqual(validate(json.dumps(value).encode()),value)

    def test_truncated_or_changed_strings_rejected(self):
        for index in [0,1]:
            value=self.receipt();value['roles'][index]['text']='truncated'
            with self.assertRaises(ValueError):validate(json.dumps(value).encode())

    def test_reference_measurement_never_qualifies_rendering(self):
        for key in ['contrast_qualified','reference_font_is_resolved_element_font','height_proxy_used_as_acceptance']:
            for bad in [True,None,0,'false']:
                value=self.receipt();value[key]=bad
                with self.assertRaises(ValueError):validate(json.dumps(value).encode())
        source=(ROOT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text()
        self.assertIn('Double(expected.height)',source)
        self.assertNotIn('ceil(expected.height)',source)
        self.assertNotIn('XCTAssertGreaterThanOrEqual(frame.height',source)

    def test_oversized_unknown_or_missing_roles_rejected(self):
        for value in [dict(self.receipt(),locale='unknown'),dict(self.receipt(),phase='unknown'),dict(self.receipt(),roles=[]),dict(self.receipt(),extra='x'*4096)]:
            with self.assertRaises(ValueError):validate(json.dumps(value).encode())

    def test_product_identity_refresh_only_on_selectable_payload(self):
        source=(ROOT/'QRCatcherMac/MacMainView.swift').read_text()
        self.assertIn('}.font(.body).foregroundStyle(.primary).padding()',source)
        self.assertIn('Text("Links open only when you choose Open in Browser.").font(.body).foregroundStyle(.primary)',source)
        self.assertEqual(source.count('.id(payload)'),1)
        self.assertIn('Text(payload).font(.title3).textSelection(.enabled).frame(maxWidth: 600).accessibilityIdentifier("mac.payload").id(payload)',source)

    def test_existing_native_cases_keep_exact_outer_wrapper_and_copy_gate(self):
        source=(ROOT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text()
        self.assertEqual(source.count('phase: "minimum-long-content"'),2)
        self.assertEqual(source.count('try pasteLongReadabilityPayload(longText, replacing:'),2)
        self.assertEqual(source.count('try verifyLongCopyAndCapture(longText, locale:'),2)
        self.assertIn('XCTAssertEqual(copiedBefore, previous)',source)
        self.assertIn('XCTAssertEqual(copied, payload)',source)
        helper=source.split('private func pasteLongReadabilityPayload')[1].split('private func resizeToMinimumReadabilityWindow')[0]
        self.assertNotIn('descendants(',helper)
        self.assertIn('guard matches.count == 1',helper)
        self.assertIn('XCTWaiter.wait(for: [exact], timeout: 15)',helper)
        self.assertIn('return ((value.value as? String) ?? value.label) == payload',helper)
        self.assertIn('XCTAssertFalse(app.buttons["mac.openWebsite"].exists)',helper)
        self.assertIn('window.frame.contains(frame)',source)
        self.assertIn('scroll.frame.contains(frame)',source)
        self.assertIn('scroll.frame.contains(value.frame)',source)
        self.assertIn('XCTAssertLessThanOrEqual(window.frame.width, 800)',source)
        self.assertIn('XCTAssertLessThanOrEqual(window.frame.height, 580)',source)

    def test_actual_clipboard_fixture_control_is_retained_before_decoder(self):
        source=(ROOT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text().split('private func pasteLongReadabilityPayload')[1].split('private func verifyLongCopyAndCapture')[0]
        self.assertIn('NSPasteboard.general.data(forType: .tiff)',source)
        self.assertIn('CIDetector(ofType: CIDetectorTypeQRCode',source)
        self.assertIn('"clipboard_tiff_sha256": hash(clipboard)',source)
        self.assertLess(source.index('try retainPayloadTransition'),source.index('XCTAssertEqual(control, [payload]'))
        self.assertLess(source.index('XCTAssertEqual(control, [payload]'),source.index('app.buttons["mac.paste"].click()'))

    def test_transition_receipts_preserve_prepared_and_observed_proof(self):
        for locale in ['en','zh-Hans']:
            for phase in ['prepared','copy-observed']:
                value=self.transition(locale,phase);self.assertEqual(transition(json.dumps(value).encode()),value)
        value=self.transition();value['fixture_control_exact']=False
        self.assertEqual(transition(json.dumps(value).encode()),value) # useful failed precondition, no product pass

    def test_transition_false_or_missing_equalities_cannot_qualify(self):
        mutations={'wrapper_after':'truncated','copy_after_sha256':'b'*64,'copy_after_utf8_bytes':1,
                   'expected_payload_utf8_bytes':1,'fixture_control_exact':False,'wrapper_before':'stale','copy_before':'stale'}
        for key,bad in mutations.items():
            value=self.transition(phase='copy-observed');value[key]=bad
            with self.assertRaises(ValueError,msg=key):transition(json.dumps(value).encode())
        value=self.transition();value['full_equality_verified']=True
        with self.assertRaises(ValueError):transition(json.dumps(value).encode())

    def test_transition_bounded_schema_rejects_invalid_evidence(self):
        mutations={'locale':'unknown','phase':'unknown','raster_width':0,'raster_height':True,'clipboard_tiff_bytes':-1,
                   'clipboard_tiff_sha256':'z'*64,'expected_payload_sha256':'a','full_equality_verified':'false',
                   'fixture_control_exact':1,'wrapper_identity_refresh_scope':'whole window','extra':'x'*4096}
        for key,bad in mutations.items():
            value=self.transition();value[key]=bad
            with self.assertRaises(ValueError,msg=key):transition(json.dumps(value).encode())

    def test_screenshots_audits_and_limits_remain_strict(self):
        ui=(ROOT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text()
        export=(ROOT/'scripts/export_mac_screenshots.py').read_text()
        self.assertIn('try app.performAccessibilityAudit(for: .all)',ui)
        self.assertIn('XCTFail("Accessibility audit [',ui)
        self.assertIn('image_limit=16',export)
        self.assertIn('Duplicate supporting text checkpoint',export)
        self.assertIn('Duplicate or excessive payload transition receipts',export)
        self.assertEqual(ui.count('\n    func test'),7)
        self.assertIn('try capturePixels("mac-minimum-long-text-" + locale)',ui)


class MacRenderedPayloadTests(unittest.TestCase):
    """Source-bound synthetic public-node predicates, not native Swift/XCUI proof."""
    def accepted(self, wrapper, children, window, scroll, payload):
        import math
        def valid(frame):
            if not isinstance(frame,list) or len(frame)!=4 or any(type(x) not in {int,float} for x in frame):return False
            try:return all(math.isfinite(x) for x in frame+[frame[0]+frame[2],frame[1]+frame[3]]) and frame[2]>0 and frame[3]>0
            except OverflowError:return False
        def contains(outer,inner,rounding=0):
            if not valid(outer) or not valid(inner):return False
            return (outer[0]-rounding<=inner[0] and outer[1]-rounding<=inner[1] and
                    inner[0]+inner[2]<=outer[0]+outer[2]+rounding and inner[1]+inner[3]<=outer[1]+outer[3]+rounding)
        if (wrapper.get('role')!='staticText' or wrapper.get('identifier')!='mac.payload' or
                wrapper.get('value')!=payload or len(children)!=1):return False
        child=children[0]
        return (child.get('role')=='staticText' and child.get('identifier')=='' and child.get('value')==payload and
                contains(window,wrapper['frame']) and contains(scroll,wrapper['frame']) and
                contains(window,child['frame']) and contains(scroll,child['frame']) and
                contains(wrapper['frame'],child['frame'],1))

    def fixture(self):
        payload='Keep the full QR result readable alongside its safety instruction and saved-history count. '*4
        wrapper=dict(role='staticText',identifier='mac.payload',value=payload,frame=[318,306,388,139],enabled=False,hittable=False)
        child=dict(role='staticText',identifier='',value=payload,frame=[317.5,306,388,139])
        return wrapper,[child],[0,31,760,572],[280,83,480,520],payload

    def test_observed_noninteractive_wrapper_and_direct_rendered_child(self):
        self.assertTrue(self.accepted(*self.fixture()))
        wrapper,children,window,scroll,payload=self.fixture()
        wrapper['frame']=[318,286,387,159];children[0]['frame']=[318,286,387,159]
        wrapper['value']=payload='完整保留二维码内容，支持中文和 English。'*7;children[0]['value']=payload
        self.assertTrue(self.accepted(wrapper,children,window,scroll,payload))

    def test_wrong_duplicate_or_unowned_child_never_qualifies(self):
        import copy
        original=self.fixture()
        for mutate in [lambda w,c: c.clear(),lambda w,c:c.append(copy.deepcopy(c[0])),
                       lambda w,c:c[0].update(role='button'),lambda w,c:c[0].update(identifier='elsewhere.payload'),
                       lambda w,c:c[0].update(value='truncated'),lambda w,c:w.update(value='stale'),
                       lambda w,c:w.update(identifier='wrong.payload'),lambda w,c:c[0].update(frame=[300,306,388,139])]:
            w,c,window,scroll,payload=copy.deepcopy(original);mutate(w,c)
            self.assertFalse(self.accepted(w,c,window,scroll,payload))

    def test_clipped_nonfinite_or_invalid_rendered_frames_never_qualify(self):
        import copy
        for frame in [[318,20,388,139],[318,550,388,139],[318,306,0,139],
                      [318,306,388,float('nan')],[float('inf'),306,388,139],
                      [318,306,True,139],[1e308,306,1e308,139],[10**400,306,388,139]]:
            w,c,window,scroll,payload=copy.deepcopy(self.fixture());c[0]['frame']=frame
            self.assertFalse(self.accepted(w,c,window,scroll,payload))

    def test_exact_public_node_scope_visibility_and_real_copy_remain_required(self):
        source=(ROOT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text()
        helper=source.split('private func verifyLongCopyAndCapture')[1].split('private func resizeToMinimumReadabilityWindow')[0]
        for required in ['matching(identifier: "mac.payload")','guard matches.count == 1',
                         'value.children(matching: .any)','value.children(matching: .staticText)',
                         'guard children.count == 1, text.count == 1','XCTAssertEqual(rendered.identifier, "")',
                         'XCTAssertEqual((rendered.value as? String) ?? rendered.label, payload)',
                         'frame.maxX, frame.maxY','XCTAssertGreaterThan(frame.width, 0)',
                         'XCTAssertGreaterThan(frame.height, 0)','window.frame.contains(frame)',
                         'scroll.frame.contains(frame)','value.frame.insetBy(dx: -1, dy: -1).contains(frame)',
                         '"wrapper_hittable": value.isHittable','"observations_qualify_pass": false',
                         'XCTAssertTrue(copy.isHittable)','XCTAssertTrue(copy.isEnabled)',
                         'window.frame.contains(copy.frame)','scroll.frame.contains(copy.frame)',
                         'copy.click()','NSPasteboard.general.string(forType: .string)','XCTAssertEqual(copied, payload)',
                         'try capturePixels("mac-minimum-long-text-" + locale)']:
            self.assertIn(required,helper)
        self.assertNotIn('descendants(',helper)
        self.assertNotIn('XCTAssertTrue(value.isHittable)',helper)
        self.assertNotIn('click()',helper.split('XCTAssertTrue(copy.isHittable)')[0])
        self.assertIn('try app.performAccessibilityAudit(for: .all)',source)
        self.assertIn('XCTFail("Accessibility audit [',source)


class MacResizeBaselineTests(unittest.TestCase):
    """Source-bound geometry adversaries, never native XCUI proof."""
    def plan(self,original,display,visible,windows=1,screens=1,sheets=0,dialogs=0):
        import math
        def valid(f):
            return (len(f)==4 and all(type(x) in {int,float} and math.isfinite(x) for x in f)
                    and f[2]>0 and f[3]>0 and all(math.isfinite(x) for x in [f[0]+f[2],f[1]+f[3]]))
        def inside(a,b):return a[0]<=b[0] and a[1]<=b[1] and b[0]+b[2]<=a[0]+a[2] and b[1]+b[3]<=a[1]+a[3]
        if windows!=1 or screens!=1 or sheets or dialogs or not all(map(valid,[original,display,visible])) or display[:2]!=[0,0]:return None
        target=[*original[:2],min(1000,visible[0]+visible[2]-original[0]),min(660,visible[1]+visible[3]-original[1])]
        if not valid(target) or not inside(display,original) or not inside(display,visible) or not inside(visible,target) or target[2]<=860 or target[3]<=632:return None
        points=[]
        if abs(original[2]-target[2])>2:
            points.extend([[original[0]+original[2]-1,original[1]+original[3]/2],[original[0]+target[2]-1,original[1]+original[3]/2]])
        if abs(original[3]-target[3])>2:
            points.extend([[original[0]+target[2]/2,original[1]+original[3]-1],[original[0]+target[2]/2,original[1]+target[3]-1]])
        if any(not(visible[0]<=x<visible[0]+visible[2] and visible[1]<=y<visible[1]+visible[3]) for x,y in points):return None
        return target,len(points)//2

    def test_retained_minimum_and_full_frames_need_verified_baseline(self):
        for initial,gestures in [([0,31,760,572],2),([0,31,1024,674],2),([0,31,1000,660],0)]:
            self.assertEqual(self.plan(initial,[0,0,1024,768],[0,31,1024,674]),([0,31,1000,660],gestures))
        self.assertLess(760,1000-100);self.assertLess(572,660-60)
        self.assertFalse(760<760-100)

    def test_unknown_modal_nonfinite_small_or_offscreen_setup_cannot_plan_gesture(self):
        original=[0,31,760,572];display=[0,0,1024,768];visible=[0,31,1024,674]
        for c in [dict(windows=0),dict(windows=2),dict(screens=2),dict(sheets=1),dict(dialogs=1)]:
            self.assertIsNone(self.plan(original,display,visible,**c))
        for f in [[0,31,0,572],[0,31,float('nan'),572],[0,31,True,572],[-1,31,760,572],[0,31,760,float('inf')],[0,31,1025,572],[900,31,760,572]]:
            self.assertIsNone(self.plan(f,display,visible))
        for f in [[0,31,860,674],[0,31,1024,632],[0,31,1024,600],[0,40,1024,665],[0,31,1024,float('nan')],[-1,31,1024,674]]:
            self.assertIsNone(self.plan(original,display,f))
        self.assertIsNone(self.plan(original,[1,0,1024,768],visible))
        self.assertIsNone(self.plan([0,31,760,705],display,visible))

    def test_public_setup_cap_readback_and_exact_original_case_preserved(self):
        source=(ROOT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text()
        helper=source.split('private func establishReadabilityResizeBaseline() throws {')[1].split('private func resizeToMinimumReadabilityWindow')[0]
        for token in ['matching(identifier: "main")','matches.count == 1','NSScreen.screens.count == 1','screen.frame.origin == .zero',
                      'app.sheets.count == 0','app.dialogs.count == 0','screen.frame.maxY - screen.visibleFrame.maxY',
                      'display.contains(original)','visible.contains(target)','target.width > 860','target.height > 632',
                      'visible.contains(right.screenPoint)','visible.contains(end.screenPoint)','visible.contains(bottom.screenPoint)',
                      'XCTAssertLessThanOrEqual(gestures, 2)','XCTAssertEqual(observed.width, target.width, accuracy: 2)',
                      'XCTAssertEqual(observed.height, target.height, accuracy: 2)','XCTAssertGreaterThan(observed.width, 860)',
                      'XCTAssertGreaterThan(observed.height, 632)','XCTAssertTrue(visible.contains(observed))']:
            self.assertIn(token,helper)
        self.assertEqual(helper.count('click(forDuration: 0.3, thenDragTo: end)'),2)
        for forbidden in ['while ','for _','sleep(','UserDefaults','setFrame','AXUIElement','performAccessibilityAudit']:
            self.assertNotIn(forbidden,helper)
        signature='    func testNativeWindowResizeKeepsFullActionTitles() throws {'
        case=signature+source.split(signature,1)[1].split('\n    func test',1)[0]
        self.assertEqual(case.count('        try establishReadabilityResizeBaseline()\n'),1)
        case=case.replace('        try establishReadabilityResizeBaseline()\n','')
        self.assertEqual(hashlib.sha256(case.encode()).hexdigest(),'dc46dabdddfb526a53b6151797629c19fbce1c98c7b43c096c5251b620174677')
        self.assertIn('.frame(minWidth: 760, minHeight: 520)',(ROOT/'QRCatcherMac/QRCatcherMacApp.swift').read_text())
        self.assertEqual(source.count('\n    func test'),7)


if __name__=='__main__':unittest.main()
