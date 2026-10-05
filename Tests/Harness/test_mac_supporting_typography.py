"""Source and bounded-receipt contracts, not native SwiftUI rendering tests."""
import ast
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
tree=ast.parse((ROOT/'scripts/export_mac_screenshots.py').read_text())
definition=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate_supporting_layout_receipt')
namespace={'json':json}
exec(compile(ast.Module(body=[definition],type_ignores=[]),'<exact-supporting-receipt-validator>','exec'),namespace)
validate=namespace['validate_supporting_layout_receipt']


class MacSupportingTextTests(unittest.TestCase):
    def receipt(self,locale='en',phase='full'):
        count=1 if phase=='full' else 2
        policy='Links open only when you choose Open in Browser.' if locale=='en' else '只有点击「在浏览器中打开」才会打开链接。'
        saved=f'{count} saved on this Mac' if locale=='en' else f'本机已保存 {count} 条记录'
        return dict(locale=locale,phase=phase,contrast_qualified=False,reference_font_is_resolved_element_font=False,
                    roles=[dict(role='link-policy',text=policy),dict(role='saved-count',text=saved)])

    def test_english_and_chinese_full_and_minimum_receipts(self):
        for locale in ['en','zh-Hans']:
            for phase in ['full','minimum-long-content']:
                value=self.receipt(locale,phase);self.assertEqual(validate(json.dumps(value).encode()),value)

    def test_truncated_or_changed_strings_rejected(self):
        for index in [0,1]:
            value=self.receipt();value['roles'][index]['text']='truncated'
            with self.assertRaises(ValueError):validate(json.dumps(value).encode())

    def test_no_contrast_or_resolved_font_claim_from_reference_measurement(self):
        for key in ['contrast_qualified','reference_font_is_resolved_element_font']:
            value=self.receipt();value[key]=True
            with self.assertRaises(ValueError):validate(json.dumps(value).encode())

    def test_oversized_unknown_or_missing_roles_rejected(self):
        for value in [dict(self.receipt(),locale='unknown'),dict(self.receipt(),phase='unknown'),dict(self.receipt(),roles=[]),dict(self.receipt(),extra='x'*4096)]:
            with self.assertRaises(ValueError):validate(json.dumps(value).encode())

    def test_two_app_owned_roles_use_body_and_original_primary_color(self):
        source=(ROOT/'QRCatcherMac/MacMainView.swift').read_text()
        self.assertIn('}.font(.body).foregroundStyle(.primary).padding()',source)
        self.assertIn('Text("Links open only when you choose Open in Browser.").font(.body).foregroundStyle(.primary)',source)
        self.assertIn('Text(payload).font(.title3).textSelection(.enabled).frame(maxWidth: 600).accessibilityIdentifier("mac.payload")',source)

    def test_existing_native_cases_extend_both_locales_with_actual_long_decode(self):
        source=(ROOT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text()
        self.assertEqual(source.count('phase: "minimum-long-content"'),2)
        self.assertEqual(source.count('try pasteLongReadabilityPayload(longText)'),2)
        self.assertIn('CIFilter(name: "CIQRCodeGenerator")',source)
        self.assertIn('XCTAssertEqual(NSPasteboard.general.string(forType: .string), longText)',source)
        self.assertIn('for _ in 0..<3 where !footer.isHittable',source)
        self.assertIn('window.frame.contains(frame)',source)
        self.assertIn('scroll.frame.contains(frame)',source)
        self.assertIn('ceil(expected.height)',source)
        self.assertIn('XCTAssertLessThanOrEqual(window.frame.width, 800)',source)
        self.assertIn('XCTAssertLessThanOrEqual(window.frame.height, 580)',source)

    def test_screenshots_audits_and_export_limits_remain_strict(self):
        ui=(ROOT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text()
        export=(ROOT/'scripts/export_mac_screenshots.py').read_text()
        self.assertIn('try app.performAccessibilityAudit(for: .all)',ui)
        self.assertIn('XCTFail("Accessibility audit [',ui)
        self.assertIn('len(screenshots)>=14',export)
        self.assertIn('Duplicate supporting text checkpoint',export)
        self.assertEqual(ui.count('\n    func test'),7)


if __name__=='__main__':unittest.main()
