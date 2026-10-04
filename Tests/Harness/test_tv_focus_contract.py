"""Observed-geometry/source contracts, not execution of the Swift remote helper."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'QRCatcherTVUITests/QRCatcherTVUITests.swift').read_text()


def overlap(a, b, axis):
    return min(a[axis] + a[axis + 2], b[axis] + b[axis + 2]) - max(a[axis], b[axis])


def bridge_candidates(origin, destination, peers):
    """Independent oracle for retained 7239 rectangles, not a Swift substitute."""
    center = lambda r: r[0] + r[2] / 2
    if overlap(origin, destination, 0) > 0:
        return []
    return [name for name, frame, enabled, hittable, focused in peers
            if enabled and hittable and not focused
            and overlap(frame, origin, 1) > 1
            and overlap(frame, destination, 0) > 1
            and (center(frame) - center(origin)) * (center(destination) - center(origin)) > 0]


class TVFocusContracts(unittest.TestCase):
    # Raw SDK27 hierarchy, run37214965788 job111474418507.
    photos = (590, 287.5, 225, 99)
    history = (846, 291.5, 221.5, 91)
    privacy = (1102.5, 291.5, 224, 91)
    export = (853.5, 849.5, 473, 91)

    def test_observed_diagonal_has_history_then_down_route(self):
        self.assertLess(overlap(self.photos, self.export, 0), 0)
        candidates = bridge_candidates(self.photos, self.export,
                                      [('history', self.history, True, True, False), ('privacy', self.privacy, True, True, False)])
        self.assertEqual(candidates, ['history', 'privacy'])
        self.assertLess(self.history[0], self.privacy[0])  # nearest right peer
        self.assertGreater(overlap(self.history, self.export, 0), 1)

    def test_aligned_origin_needs_no_horizontal_bridge(self):
        self.assertEqual(bridge_candidates(self.history, self.export,
                                          [('privacy', self.privacy, True, True, False)]), [])

    def test_hidden_disabled_or_wrong_row_cannot_be_bridge(self):
        peers = [('disabled', self.history, False, True, False), ('hidden', self.history, True, False, False),
                 ('focused', self.history, True, True, True), ('target-row', self.export, True, True, False)]
        self.assertEqual(bridge_candidates(self.photos, self.export, peers), [])

    def test_real_failed_press_is_required_before_bounded_bridge(self):
        for token in ['for attempt in 0..<30', 'previousIdentifier == focused.identifier && previousFrame == origin',
                      'previousDirection == direction', 'direction == .down || direction == .up',
                      'peer.exists, peer.isEnabled, peer.isHittable, !peer.hasFocus',
                      'scope.descendants(matching: .button)', 'XCUIRemote.shared.press(direction)']:
            self.assertIn(token, SOURCE)
        self.assertIn('let scope = root ?? app!', SOURCE)
        self.assertIn('XCTFail("Remote focus could not reach the actual control:', SOURCE)

    def test_no_coordinate_tap_or_direct_focus_assignment(self):
        helper = SOURCE.split('private func focusAndSelect(', 1)[1].split('private func respondToExactPhotosPermissionIfPresent', 1)[0]
        self.assertNotIn('.tap()', helper)
        self.assertNotIn('coordinate(', helper)
        self.assertNotIn('setValue(', helper)
        self.assertEqual(helper.count('XCUIRemote.shared.press(.select)'), 3)
        for proof in ['if target.hasFocus', 'focusedCell.buttons.count == 1',
                      'focusedCell.buttons[target.identifier].exists', 'focused.label == target.label']:
            self.assertIn(proof, helper)


if __name__ == '__main__':
    unittest.main()
