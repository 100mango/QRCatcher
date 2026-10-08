"""Synthetic receipt and source-contract tests, never native UI evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import discover_native_settings as discovery


def row(label):
    return dict(role='button', label=label, identifier='', frame=[10, 40, 180, 30],
                value_empty=True, enabled=True, selected=False, adjustment_descendants=False)


def navigation_fixture(platform='watch'):
    route = discovery.ROUTES[platform]
    return dict(navigation_complete=True, last_observed_pane='Text Size', screenshot_pane='Text Size',
                navigation_steps=[dict(**{'from': a, 'to': b}, control=row(b), pane_frame=[0, 0, 220, 250],
                                       state='destination_verified',
                                       action='exact_element_tap' if platform == 'watch' else 'focused_remote_select')
                                  for a, b in zip(route, route[1:])], focus_steps=[], **({'scroll_steps': []} if platform == 'watch' else {}))


class NavigationReceiptTests(unittest.TestCase):
    def reject(self, receipt, platform='watch'):
        with self.assertRaises(discovery.DiscoveryStopped):
            discovery.validate_navigation_receipt(receipt, platform)

    def test_complete_synthetic_routes(self):
        for platform in ['watch', 'tv']:
            discovery.validate_navigation_receipt(navigation_fixture(platform), platform)

    def test_missing_or_forged_completion(self):
        for changes in [dict(navigation_complete=1), dict(navigation_complete=True, navigation_steps=[]),
                        dict(last_observed_pane='Display'), dict(navigation_steps=None), dict(focus_steps=None)]:
            self.reject(dict(navigation_fixture(), **changes))

    def test_partial_before_action_is_valid_but_never_complete(self):
        r=navigation_fixture(); r.update(navigation_complete=False, status='observation_stopped')
        r['navigation_steps']=r['navigation_steps'][:1];r['navigation_steps'][0]['state']='observed'
        discovery.validate_navigation_receipt(r, 'watch')
        r['status']='settings_screen_observed';self.reject(r)

    def test_cannot_continue_after_unverified_destination(self):
        for state in ['observed','activation_attempted','activation_returned']:
            r=navigation_fixture();r['navigation_steps'][0]['state']=state;self.reject(r)

    def test_route_role_value_and_action_fail_closed(self):
        for key,value in [('role','slider'),('label','Larger Text'),('value_empty',False),('enabled',False),
                          ('selected',True),('adjustment_descendants',True),('identifier',42)]:
            r=navigation_fixture();r['navigation_steps'][0]['control'][key]=value;self.reject(r)
        for key,value in [('from','Accessibility'),('to','Bold Text'),('action','press_left'),('state','passed')]:
            r=navigation_fixture();r['navigation_steps'][0][key]=value;self.reject(r)

    def test_finite_wholly_contained_geometry(self):
        for frame in [[0,0,0,1], [0,0,-1,1], [-1,0,10,10], [200,0,30,10], [0,230,10,30],
                      [float('nan'),0,10,10], [0,0,float('inf'),10], [False,0,10,10], [1,2,3], 'rect']:
            r=navigation_fixture();r['navigation_steps'][0]['control']['frame']=frame;self.reject(r)

    def test_finite_components_with_nonfinite_endpoints_are_rejected(self):
        # Every component is finite; adding origin and extent overflows a float.
        for frame in [[1e308, 0, 1e308, 10], [0, 1e308, 10, 1e308]]:
            self.assertFalse(discovery.valid_rectangle(frame))
            for field in ['control', 'pane_frame']:
                r=navigation_fixture()
                if field == 'control':r['navigation_steps'][0][field]['frame']=frame
                else:r['navigation_steps'][0][field]=frame
                self.reject(r)

    def test_huge_json_integers_fail_closed_without_overflow_exception(self):
        huge=json.loads('1' + '0' * 400)
        for frame in [[huge,0,10,10], [0,huge,10,10], [0,0,huge,10], [0,0,10,huge],
                      [huge,0,1.0,10], [10**308,0,10**308,10]]:
            self.assertFalse(discovery.valid_rectangle(frame))
            r=navigation_fixture();r['navigation_steps'][0]['control']['frame']=frame
            self.reject(r)
        self.assertTrue(discovery.valid_rectangle([0,0,220,250]))
        self.assertTrue(discovery.valid_rectangle([-100.5,-30,200,60]))

    def test_screen_success_requires_terminal_capture(self):
        r=dict(navigation_fixture(),status='settings_screen_observed',screenshot_attached=True)
        discovery.validate_navigation_receipt(r,'watch')
        r['screenshot_pane']='Settings';self.reject(r)

    def test_focus_is_vertical_bounded_and_from_safe_control(self):
        r=navigation_fixture('tv')
        move=dict(**{'from':row('General')},pane='Settings',toward='Accessibility',pane_frame=[0,0,220,250],
                  direction='down',state='movement_attempted')
        r['focus_steps']=[move];discovery.validate_navigation_receipt(r,'tv')
        for key,value in [('direction','left'),('state','verified'),('toward','Text Size'),('pane','Text Size')]:
            bad=copy.deepcopy(r);bad['focus_steps'][0][key]=value;self.reject(bad,'tv')
        r['focus_steps']=[move]*9;self.reject(r,'tv')
        r['focus_steps']=[move];self.reject(r,'watch')
        r['focus_steps'][0]['from']['role']='switch';self.reject(r,'tv')


class NavigationSourceTests(unittest.TestCase):
    def source(self,label):
        return (ROOT/f'QRCatcher{label}UITests/QRCatcher{label}UITests.swift').read_text().split(f'final class QRCatcher{label}SettingsDiscovery')[1]

    def test_no_setting_write_coordinate_reveal_or_deadline_extension(self):
        for label in ['Watch','TV']:
            s=self.source(label)
            inspected=s
            if label=='Watch':
                self.assertEqual(s.count('element.swipeUp(velocity: .slow)'),1)
                inspected=s.replace('element.swipeUp(velocity: .slow)','')
            for forbidden in ['adjust(toNormalizedSliderPosition','rotateDigitalCrown','coordinate(','.swipe',
                              'press(.left)','press(.right)','forDuration:','AppleLanguages','accessibility5']:
                self.assertNotIn(forbidden,inspected)
            for guard in ['< 45','nodes.count < 256','path.count <= 20','descendants.count <= 16',
                          'bounds.contains(frame)','values.allSatisfy','emptyValue(row.value)',
                          'row.isEnabled, !row.isSelected','matches.count == 1','query.count == 1',
                          'element.isHittable','try verifyPane(target, app, destination)',
                          'QRStopForUnexpectedInterruption','"system_propagation_qualified": false']:
                self.assertIn(guard,s)
            self.assertEqual(s.count('XCTAttachment(screenshot:'),1)
            self.assertNotIn('waitForExistence',s)

    def test_competing_title_absence_is_not_conflated_with_ambiguity(self):
        # Source contract regression only: native snapshots are not executed here.
        for label in ['Watch','TV']:
            s=self.source(label)
            candidates=s.split('private func titleCandidates',1)[1].split('private func observedTitle',1)[0]
            pane=s.split('private func verifyPane',1)[1].split('private func safeRow',1)[0]
            self.assertIn('-> [ObservedNode]',candidates)
            self.assertNotIn('try?',pane)
            self.assertIn('if !titleCandidates(other, observation).isEmpty {',pane)
            self.assertNotIn('observedTitle(other',pane)
            # Zero, one and duplicate candidates retain distinct presence. Neither
            # a uniqueness guard nor geometry filtering may erase competitors.
            self.assertNotIn('count == 1',candidates)
            self.assertNotIn('whollyVisible',candidates)
            self.assertNotIn('validFrame',candidates)

    def test_titles_actions_and_focus_require_every_ancestor_viewport(self):
        for label in ['Watch','TV']:
            s=self.source(label)
            visible=s.split('private func whollyVisible',1)[1].split('private func titleCandidates',1)[0]
            title=s.split('private func observedTitle',1)[1].split('private func liveElement',1)[0]
            row=s.split('private func safeRow',1)[1].split('private func navigationRow',1)[0]
            self.assertIn('validFrame(frame, inside: observation.appFrame)',visible)
            self.assertIn('$0.path.count < node.path.count && node.path.starts(with: $0.path)',visible)
            self.assertIn('[.scrollView, .table, .collectionView]',visible)
            self.assertIn('guard viewports.count <= 20',visible)
            self.assertIn('viewports.allSatisfy { validFrame(frame, inside: $0.snapshot.frame) }',visible)
            self.assertIn('whollyVisible(match, observation)',title)
            self.assertIn('whollyVisible(node, observation)',row)
            self.assertNotIn('validFrame(row.frame, inside: observation.appFrame)',row)
            if label == 'TV':self.assertIn('try safeRow(current, fresh)',s)

    def test_one_watch_exact_tap_no_remote(self):
        s=self.source('Watch');self.assertEqual(s.count('.tap()'),1);self.assertNotIn('XCUIRemote',s)
        a=s.index('private func activateNavigationRow')
        self.assertLess(s.index('try navigationRow(target, fresh)',a),s.index('element.tap()',a))
        self.assertLess(s.index('row.snapshot.frame == observed.snapshot.frame',a),s.index('element.tap()',a))

    def test_tv_fresh_focus_each_single_direction_and_select(self):
        s=self.source('TV');self.assertNotIn('.tap()',s)
        for x in ['focusMoves < 8','focused.count == 1','try safeRow(current, fresh)',
                  'guard currentElement.hasFocus','guard element.hasFocus','seen.insert(identity)',
                  'distance < lastDistance!','sameColumn','press(.select)','press(.down)','press(.up)']:
            self.assertIn(x,s)
        for x in ['press(.select)','press(.down)','press(.up)']:self.assertEqual(s.count(x),1)

    def test_protocol_is_explicit_and_old_contract_is_not_accepted(self):
        for label in ['Watch','TV']:
            protocol='bounded-settings-watch-root-scroll-v1' if label=='Watch' else 'bounded-settings-navigation-v1'
            self.assertIn('contract["discovery_protocol"] as? String == "'+protocol+'"',self.source(label))
        for path in ['scripts/settings_discovery_fence.py','scripts/discover_native_settings.py']:
            s=(ROOT/path).read_text();self.assertIn('bounded-settings-navigation-v1',s);self.assertNotIn('initial-screen-only-v1',s)

    def test_original_caps_and_owned_driver_integration(self):
        d=(ROOT/'scripts/discover_native_settings.py').read_text()
        for x in ['AGGREGATE_SECONDS = 180','UI_RECEIPT_LIMIT = 24 * 1024',"output,", "run('settings_ui', command, 90"]:
            if x != 'output,':self.assertIn(x,d)
        f=(ROOT/'scripts/settings_discovery_fence.py').read_text()
        self.assertIn("cap, limit = 90, 512 * 1024",f)
        self.assertNotIn('run_settings_discovery_fenced',(ROOT/'.github/workflows/apple-platforms.yml').read_text())
        self.assertIn('SETTINGS_DISCOVERY_FENCE_VERSION',(ROOT/'scripts/owned_process_barrier.py').read_text())

if __name__=='__main__':unittest.main()
