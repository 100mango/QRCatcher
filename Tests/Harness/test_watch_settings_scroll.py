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


if __name__=='__main__':unittest.main()
