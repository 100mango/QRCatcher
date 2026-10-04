"""Exercise exact exporter endpoint functions without macOS command side effects."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TREE = ast.parse((ROOT / 'scripts/export_ios_platform_screenshots.py').read_text())
DEFINITIONS = [node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name in {'required_alert_endpoints', 'missing_alert_endpoints'}]
assert len(DEFINITIONS) == 2
NAMESPACE = {}
exec(compile(ast.Module(body=DEFINITIONS, type_ignores=[]), '<exact-alert-evidence-functions>', 'exec'), NAMESPACE)
required = NAMESPACE['required_alert_endpoints']
missing = NAMESPACE['missing_alert_endpoints']


class NativeAlertEvidenceTests(unittest.TestCase):
    def requirements(self, mode='scrolled', result='SE3'):
        return [{'result_label': result, 'mode': mode}]

    def images(self, *names, result='SE3'):
        return [{'result_label': result, 'checkpoint': 'phone-largest-history-alert' + name} for name in names]

    def test_scrolled_requires_both_endpoint_names(self):
        self.assertEqual(required('scrolled'), {'phone-largest-history-alert-top', 'phone-largest-history-alert-end'})

    def test_both_actual_result_endpoints_satisfy_contract(self):
        self.assertEqual(missing(self.requirements(), self.images('-top', '-end'), ['SE3']), [])

    def test_missing_end_fails_contract(self):
        result = missing(self.requirements(), self.images('-top'), ['SE3'])
        self.assertEqual(result[0]['missing'], ['phone-largest-history-alert-end'])

    def test_missing_both_fails_contract(self):
        result = missing(self.requirements(), [], ['SE3'])
        self.assertEqual(len(result[0]['missing']), 2)

    def test_other_result_cannot_supply_an_endpoint(self):
        result = missing(self.requirements(), self.images('-top') + self.images('-end', result='pro-max'), ['SE3'])
        self.assertEqual(result[0]['missing'], ['phone-largest-history-alert-end'])

    def test_unscrolled_requires_its_own_single_capture(self):
        self.assertEqual(missing(self.requirements('unscrolled'), self.images(''), ['SE3']), [])
        self.assertTrue(missing(self.requirements('unscrolled'), self.images('-top', '-end'), ['SE3']))

    def test_produced_phone_result_requires_mode_receipt(self):
        self.assertTrue(missing([], self.images('-top', '-end'), ['SE3']))

    def test_duplicate_receipt_fails_closed(self):
        with self.assertRaises(ValueError):
            missing(self.requirements() * 2, self.images('-top', '-end'), ['SE3'])

    def test_unknown_mode_or_result_fails_closed(self):
        for requirement in [self.requirements('unknown'), self.requirements(result='unrelated')]:
            with self.assertRaises(ValueError):
                missing(requirement, [], ['SE3'])


if __name__ == '__main__':
    unittest.main()
