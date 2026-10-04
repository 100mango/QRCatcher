"""Exact boolean/source contracts; native picker behavior still requires XCTest."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'QRCatcherUITests/QRCatcherImageImportUITests.m').read_text()
PREDICATE = SOURCE.split('NSPredicate *pickerReady =', 1)[1].split('}];', 1)[0]
EXPRESSION = re.search(r'return (.*);', PREDICATE).group(1)
TERMS = re.findall(r'(?:picker|bar|cancel)\.(?:exists|enabled|hittable)', EXPRESSION)
PYTHON_EXPRESSION = EXPRESSION.replace('&&', 'and')
for term in TERMS:
    PYTHON_EXPRESSION = PYTHON_EXPRESSION.replace(term, 'state[' + repr(term) + ']')
CODE = compile(PYTHON_EXPRESSION, '<exact-native-readiness-boolean>', 'eval')


def ready(state):
    return bool(eval(CODE, {'__builtins__': {}}, {'state': state}))


class PhoneFilesReadinessTests(unittest.TestCase):
    def test_complete_visible_enabled_context_satisfies_boolean(self):
        self.assertTrue(ready(dict.fromkeys(TERMS, True)))

    def test_absent_context_or_control_and_disabled_or_hidden_fail(self):
        self.assertEqual(TERMS, ['picker.exists', 'bar.exists', 'cancel.exists', 'cancel.enabled', 'cancel.hittable'])
        for absent in TERMS:
            with self.subTest(absent=absent):
                state = dict.fromkeys(TERMS, True)
                state[absent] = False
                self.assertFalse(ready(state))

    def test_cancel_is_scoped_to_exact_observed_picker_and_bar(self):
        self.assertIn('picker = app.otherElements[@"Browse View (Picker)"].firstMatch', PREDICATE)
        self.assertIn('bar = picker.navigationBars[@"FullDocumentManagerViewControllerNavigationBar"].firstMatch', PREDICATE)
        self.assertIn('cancel = bar.buttons[@"Cancel"].firstMatch', PREDICATE)
        # An available Cancel in some other UI context cannot satisfy the gate.
        self.assertFalse(ready({'picker.exists': False, 'bar.exists': False,
                                'cancel.exists': True, 'cancel.enabled': True, 'cancel.hittable': True}))

    def test_readiness_cannot_tap_and_has_same_twenty_second_bound(self):
        self.assertNotIn(' tap]', PREDICATE)
        self.assertNotIn('swipe', PREDICATE)
        self.assertIn('XCTWaiterResult outcome = [XCTWaiter waitForExpectations:@[ready] timeout:20]', SOURCE)
        self.assertIn('XCTAssertEqual(outcome, XCTWaiterResultCompleted', SOURCE)
        self.assertLess(SOURCE.index('if (outcome != XCTWaiterResultCompleted) return;'),
                        SOURCE.index('if (![self visibleItem:@"QRCatcher-Test-Imports"])'))
        self.assertIn('if (UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPhone)', SOURCE)
        self.assertNotIn('@"Close"', PREDICATE)


if __name__ == '__main__':
    unittest.main()
