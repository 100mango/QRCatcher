"""Receipt adversaries and source contracts; no native gesture/reachability claim."""
import copy
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import discover_native_settings as discovery
from test_settings_navigation import navigation_fixture


def scroll(state='progress_verified'):
    value=dict(pane='Settings',toward='Display & Brightness',action='native_collection_swipe_up_slow',state=state,
               container_frame=[0,0,208,248],container_identifier='',container_label='',
               safe_navigation_rows_only=True,adjustment_controls_present=False)
    if state=='progress_verified':
        value.update(anchor_identifier='GENERAL_ID',anchor_label='General',before_frame=[2,242,204,56],after_frame=[2,102,204,56])
    return value


class WatchScrollReceiptTests(unittest.TestCase):
    def receipt(self):
        value=navigation_fixture('watch');value['scroll_steps']=[scroll()];return value

    def rejects(self,value,platform='watch'):
        with self.assertRaises(discovery.DiscoveryStopped):discovery.validate_navigation_receipt(value,platform)

    def test_completed_matching_upward_progress_including_clipped_initial_anchor(self):
        discovery.validate_navigation_receipt(self.receipt(),'watch')

    def test_two_is_absolute_bound_and_tv_has_no_scroll_permission(self):
        value=self.receipt();value['scroll_steps']*=3;self.rejects(value)
        value=navigation_fixture('tv');value['scroll_steps']=[scroll()];self.rejects(value,'tv')

    def test_wrong_pane_target_gesture_or_adjuster_stops(self):
        for key,item in [('pane','Display & Brightness'),('toward','Text Size'),('action','crown'),
                         ('safe_navigation_rows_only',False),('adjustment_controls_present',True),('state','accepted')]:
            value=self.receipt();value['scroll_steps'][0][key]=item;self.rejects(value)

    def test_partial_scroll_may_only_stop_without_navigation(self):
        value=navigation_fixture('watch');value.update(navigation_complete=False,navigation_steps=[],status='observation_stopped',scroll_steps=[scroll('scroll_attempted')])
        discovery.validate_navigation_receipt(value,'watch')
        value['navigation_steps']=navigation_fixture('watch')['navigation_steps'];self.rejects(value)

    def test_second_gesture_cannot_follow_unconfirmed_first(self):
        value=self.receipt();value['scroll_steps']=[scroll('scroll_returned'),scroll()];self.rejects(value)

    def test_same_list_and_repeated_anchor_must_preserve_continuity(self):
        value=self.receipt();second=scroll();second.update(before_frame=[2,102,204,56],after_frame=[2,2,204,56])
        value['scroll_steps'].append(second);discovery.validate_navigation_receipt(value,'watch')
        value['scroll_steps'][1]['container_label']='different';self.rejects(value)
        value['scroll_steps'][1]['container_label']='';value['scroll_steps'][1]['before_frame']=[2,242,204,56];self.rejects(value)

    def test_nonfinite_unseen_or_unmatched_anchor_stops(self):
        changes=[('before_frame',[2,400,204,56]),('after_frame',[2,243,204,56]),('after_frame',[5,102,204,56]),
                 ('after_frame',[2,102,190,56]),('after_frame',[2,float('nan'),204,56]),('anchor_identifier',''),
                 ('container_identifier','x'*129),('container_frame',[0,0,0,248])]
        for key,item in changes:
            value=self.receipt();value['scroll_steps'][0][key]=item;self.rejects(value)
        value=self.receipt();value['scroll_steps'][0]['before_frame'][0]=-1;value['scroll_steps'][0]['after_frame'][0]=-1
        self.rejects(value)

    def test_old_watch_protocol_is_not_silently_extended(self):
        self.assertEqual(discovery.PROTOCOL['watch'],'bounded-settings-watch-root-scroll-v1')
        self.assertEqual(discovery.PROTOCOL['tv'],'bounded-settings-navigation-v1')
        value=navigation_fixture('watch');value.pop('scroll_steps');self.rejects(value)


class WatchScrollSourceContracts(unittest.TestCase):
    def source(self):
        return (ROOT/'QRCatcherWatchUITests/QRCatcherWatchUITests.swift').read_text().split('final class QRCatcherWatchSettingsDiscovery')[1]

    def test_only_root_collection_with_two_slow_native_gestures(self):
        source=self.source()
        for token in ['scrollSteps.count < 2','pane == "Settings" && target == "Display & Brightness"',
                      'lists.count == 1','container.snapshot.elementType', 'try rootNavigationMenu(app, fresh)',
                      'row.snapshot.frame.minY >= menu.visibleTop','element.swipeUp(velocity: .slow)']:
            if token!='container.snapshot.elementType':self.assertIn(token,source)
        self.assertEqual(source.count('.swipeUp('),1)
        for token in ['.swipeDown(','.swipeLeft(','.swipeRight(','rotateDigitalCrown','coordinate(']:self.assertNotIn(token,source)

    def test_unknown_controls_and_ambiguous_rows_stop_before_gesture(self):
        source=self.source();guard=source.split('private func rootNavigationMenu',1)[1].split('private func revealRootDisplayRow',1)[0]
        self.assertIn('allowed.contains($0.snapshot.elementType)',guard)
        allowed=guard.split('let allowed:',1)[1].split('guard observation.nodes',1)[0]
        for forbidden in ['.slider','.switch','.picker','.button','.sheet','.dialog']:self.assertNotIn(forbidden,allowed)
        self.assertIn('identifiers.insert(row.identifier).inserted',guard)
        self.assertIn('labels.insert(row.label).inserted',guard)
        self.assertIn('emptyValue(row.value)',guard)

    def test_live_identity_progress_cycle_and_deadlines_remain_required(self):
        source=self.source()
        for token in ['menuSignature(current) == signature','!seen.contains(menuSignature(advanced))',
                      'No independently matched upward menu progress','try checkScreen(app); try checkTime()',
                      '(ProcessInfo.processInfo.systemUptime - began) < 45','nodes.count < 256','path.count <= 20']:
            self.assertIn(token,source)
        self.assertEqual(source.count('XCTAttachment(screenshot:'),1)
        self.assertIn('"system_propagation_qualified": false',source)


class WatchRootIdentityPredicateTests(unittest.TestCase):
    """Execute a restricted translation of source predicates against synthetic AX.

    This does not compile Swift or execute XCTest, Settings, a gesture, or a device.
    Unknown syntax is rejected rather than guessed. Native qualification is separate.
    """
    def setUp(self):
        import re
        self.re = re
        self.source = WatchScrollSourceContracts().source()
        candidates = self.source.split('private func titleCandidates', 1)[1].split('private func observedTitle', 1)[0]
        self.bars = re.search(r'let bars = observation.nodes.filter \{(.*?)\n        \}', candidates, re.S).group(1)
        self.fallback = re.search(r'return bars.isEmpty \? observation.nodes.filter \{(.*?)\n        \} : bars', candidates, re.S).group(1)
        live = self.source.split('private func liveElement', 1)[1].split('private func verifyPane', 1)[0]
        self.identity_condition = re.search(r'if (.*?) \{', live).group(1)
        queries = re.findall(r'query = app.descendants\(matching: (.*?)\)\.matching\(NSPredicate\(format: "(identifier|label) == %@", (.*?)\)\)', live)
        self.assertEqual(queries, [('.navigationBar', 'identifier', '"Settings"'), ('captured.elementType', 'label', 'captured.label')])
        self.live_guard = re.search(r'guard element.exists,(.*?) else \{', live, re.S).group(1)
        self.assertIn('guard query.count == 1 else', live)
        self.assertIn('matches.count == 1', self.source)
        self.assertIn('whollyVisible(match, observation)', self.source)
        self.assertIn('if !titleCandidates(other, observation).isEmpty', self.source)
        root = self.source.split('private func rootNavigationMenu', 1)[1].split('private func revealRootDisplayRow', 1)[0]
        self.assertIn('header.snapshot.elementType == .navigationBar', root)

    def node(self, role='navigationBar', identifier='Settings', label='', **changes):
        from types import SimpleNamespace
        return SimpleNamespace(**dict(dict(elementType=role, identifier=identifier, label=label,
            frame=(0, 0, 208, 62), inControl=False, visible=True, exists=True, isHittable=True), **changes))

    def predicate(self, source, **values):
        import ast
        text = source.strip().replace('$0.snapshot.', 'node.').replace('$0.inControl', 'node.inControl')
        text = self.re.sub(r'(node|captured)\.label\.isEmpty', r'\1.label == ""', text)
        text = text.replace('.navigationBar', '"navigationBar"').replace('.staticText', '"staticText"')
        text = text.replace('&&', ' and ').replace('||', ' or ').replace(',', ' and ')
        text = self.re.sub(r'!(?!=)', 'not ', text)
        tree = ast.parse('(' + text + ')', mode='eval')
        allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
                   ast.Compare, ast.Eq, ast.NotEq, ast.Name, ast.Load, ast.Attribute, ast.Constant)
        self.assertTrue(all(isinstance(item, allowed) for item in ast.walk(tree)), text)
        self.assertTrue(all(item.id in values for item in ast.walk(tree) if isinstance(item, ast.Name)), text)
        return eval(compile(tree, '<source-bound-Swift-predicate>', 'eval'), {'__builtins__': {}}, values)

    def candidates(self, title, nodes):
        bars = [node for node in nodes if self.predicate(self.bars, node=node, title=title)]
        return bars or [node for node in nodes if self.predicate(self.fallback, node=node, title=title)]

    def verify(self, title, nodes, live=None, root=False):
        candidates = self.candidates(title, nodes)
        if len(candidates) != 1 or not candidates[0].visible:
            raise discovery.DiscoveryStopped('synthetic missing, duplicate or clipped title')
        captured = candidates[0]
        special = self.predicate(self.identity_condition, captured=captured)
        field, wanted = ('identifier', 'Settings') if special else ('label', captured.label)
        matches = [item for item in (nodes if live is None else live)
                   if item.elementType == captured.elementType and getattr(item, field) == wanted]
        if len(matches) != 1:
            raise discovery.DiscoveryStopped('synthetic live query ambiguity')
        element = matches[0]
        if not element.exists or not self.predicate(self.live_guard, element=element, captured=captured):
            raise discovery.DiscoveryStopped('synthetic live identity changed')
        for other in ['Settings', 'Display & Brightness', 'Text Size']:
            if other != title and self.candidates(other, nodes):
                raise discovery.DiscoveryStopped('synthetic competing pane')
        if root and captured.elementType != 'navigationBar':
            raise discovery.DiscoveryStopped('synthetic root requires native navigation bar')
        return captured

    def rejects(self, title, nodes, **options):
        with self.assertRaises(discovery.DiscoveryStopped):
            self.verify(title, nodes, **options)

    def test_retained_identifier_only_root_bar_is_admitted(self):
        bar = self.node()
        static = self.node('staticText', '', 'Settings')
        self.assertIs(self.verify('Settings', [bar, static], root=True), bar)

    def test_wrong_missing_or_nonempty_label_root_identity_stops(self):
        for identifier, label in [('Other', ''), ('', ''), ('settings', ''), ('Settings ', ''),
                                  ('Other', 'Settings'), ('Settings', 'Settings')]:
            self.rejects('Settings', [self.node(identifier=identifier, label=label)], root=True)

    def test_duplicate_bar_is_not_erased_by_clipping(self):
        for visible in [True, False]:
            self.rejects('Settings', [self.node(), self.node(visible=visible)], root=True)

    def test_duplicate_live_identifier_even_with_other_label_stops(self):
        self.rejects('Settings', [self.node()], live=[self.node(), self.node(label='Other')], root=True)

    def test_other_pane_identifier_is_not_a_title(self):
        for title in ['Display & Brightness', 'Text Size']:
            self.rejects(title, [self.node(identifier=title)])
            labelled = self.node(identifier='unrelated', label=title)
            self.assertIs(self.verify(title, [labelled]), labelled)

    def test_settings_identifier_outside_current_root_pane_stops(self):
        self.rejects('Display & Brightness', [self.node(), self.node(identifier='display', label='Display & Brightness')])

    def test_identifier_exception_does_not_extend_to_other_roles(self):
        for role in ['staticText', 'button', 'cell', 'collectionView']:
            self.rejects('Settings', [self.node(role)], root=True)

    def test_static_fallback_cannot_authorize_root_scroll(self):
        self.rejects('Settings', [self.node('staticText', '', 'Settings')], root=True)

    def test_competing_route_title_and_nested_row_static_label_stay_distinct(self):
        self.rejects('Settings', [self.node(), self.node('staticText', '', 'Text Size')], root=True)
        bar = self.node()
        self.assertIs(self.verify('Settings', [bar, self.node('staticText', '', 'Text Size', inControl=True)], root=True), bar)

    def test_live_role_identifier_label_frame_and_hittability_remain_exact(self):
        for changes in [dict(elementType='staticText'), dict(identifier='Other'), dict(label='Other'),
                        dict(frame=(0, 0, 208, 61)), dict(isHittable=False), dict(exists=False)]:
            self.rejects('Settings', [self.node()], live=[self.node(**changes)], root=True)

    def test_wrong_root_bar_cannot_be_rescued_by_static_title(self):
        self.rejects('Settings', [self.node(identifier='Other'), self.node('staticText', '', 'Settings')], root=True)


if __name__=='__main__':unittest.main()
