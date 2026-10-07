"""Local graph/source tests only. No Xcode, simulator, signing or network calls."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_ios_only_project import parse_project, paths_in_phase, preprocess, references

ROOT = Path(__file__).resolve().parents[2]
PROJECT = 'QRCatcher-iOS-Watch.xcodeproj'
HELPERS = {'QRCatcher/QRWatchPhoneService.m', 'QRCatcher/QRWatchSessionGate.m'}
TARGETS = {'QRCatcher', 'QRCatcherTests', 'QRCatcherUITests',
           'QRCatcherWatch', 'QRCatcherWatchTests', 'QRCatcherWatchUITests'}


def inventory(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}


def target_map(project):
    return {node['name']: node for node in project['objects'].values()
            if node['isa'] == 'PBXNativeTarget'}


def closure(project, name):
    objects = project['objects']
    start = next(key for key, node in objects.items()
                 if node.get('isa') == 'PBXNativeTarget' and node.get('name') == name)
    seen = set()
    def visit(key):
        if key in seen or key == project['rootObject']:
            return
        seen.add(key)
        for ref in references(objects[key]):
            if ref in objects:
                visit(ref)
    visit(start)
    return {key: objects[key] for key in seen}


class IOSWatchProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        (cls.root / 'scripts').mkdir()
        shutil.copyfile(ROOT / 'scripts/generate_project.py', cls.root / 'scripts/generate_project.py')
        # Seed the two checked-in projects, including their nongenerated
        # workspace metadata. Re-generation must preserve those bytes too.
        for project in ('QRCatcher.xcodeproj', 'QRCatcher-iOS-Only.xcodeproj'):
            shutil.copytree(ROOT / project, cls.root / project)
        for name in ('Shared', 'QRCatcher', 'QRCatcherTests', 'QRCatcherUITests',
                     'QRCatcherMac', 'QRCatcherMacTests', 'QRCatcherMacUITests',
                     'QRCatcherVision', 'QRCatcherVisionTests', 'QRCatcherVisionUITests',
                     'QRCatcherTV', 'QRCatcherTVTests', 'QRCatcherTVUITests',
                     'QRCatcherWatch', 'QRCatcherWatchTests', 'QRCatcherWatchUITests',
                     'ThirdParty', 'Tests'):
            (cls.root / name).symlink_to(ROOT / name, target_is_directory=True)
        cls.command = [sys.executable, str(cls.root / 'scripts/generate_project.py')]
        for profile in ('all-platforms', 'ios-only', 'ios-watch'):
            subprocess.run(cls.command + ['--profile', profile], check=True, capture_output=True, timeout=30)
        cls.integrated = parse_project(cls.root / 'QRCatcher.xcodeproj/project.pbxproj')
        cls.original = parse_project(cls.root / 'QRCatcher-iOS-Only.xcodeproj/project.pbxproj')
        cls.watch = parse_project(cls.root / PROJECT / 'project.pbxproj')
        cls.targets = target_map(cls.watch)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_new_profile_exactly_replays_checked_in_project_and_two_schemes(self):
        self.assertEqual(inventory(self.root / PROJECT), inventory(ROOT / PROJECT))
        self.assertEqual(set(inventory(self.root / PROJECT)), {
            'project.pbxproj', 'xcshareddata/xcschemes/QRCatcher.xcscheme',
            'xcshareddata/xcschemes/QRCatcherWatch.xcscheme'})

    def test_profiles_do_not_overwrite_each_other_and_old_outputs_stay_byte_exact(self):
        projects = ('QRCatcher.xcodeproj', 'QRCatcher-iOS-Only.xcodeproj', PROJECT)
        before = {name: inventory(self.root / name) for name in projects}
        for profile in ('ios-watch', 'ios-only', 'all-platforms', 'ios-watch'):
            subprocess.run(self.command + ['--profile', profile], check=True, capture_output=True, timeout=30)
            self.assertEqual({name: inventory(self.root / name) for name in projects}, before)
        for name in projects[:2]:
            self.assertEqual(before[name], inventory(ROOT / name))

    def test_exact_six_targets_and_no_deferred_or_orphan_objects(self):
        self.assertEqual(set(self.targets), TARGETS)
        objects = self.watch['objects']
        seen = set()
        def visit(key):
            if key in seen:
                return
            seen.add(key)
            for ref in references(objects[key]):
                if ref in objects:
                    visit(ref)
        visit(self.watch['rootObject'])
        self.assertEqual(seen, set(objects))
        self.assertFalse(any('Mac' in node.get('name', '') or 'Vision' in node.get('name', '')
                             or node.get('name', '').startswith('QRCatcherTV')
                             for node in objects.values()))
        self.assertFalse(any(node['isa'] == 'PBXShellScriptBuildPhase' for node in objects.values()))

    def test_all_six_target_build_closures_equal_existing_c23_integrated_graph(self):
        # Product settings, inputs, frameworks, dependency edges, and tests all
        # come from the latest source's existing graph, not an older checkout.
        for name in TARGETS:
            self.assertEqual(closure(self.watch, name), closure(self.integrated, name), name)

    def test_phone_companion_has_exactly_one_shipping_owner_without_test_duplicate(self):
        objects = self.watch['objects']
        app = set(paths_in_phase(objects, self.targets['QRCatcher'], 'PBXSourcesBuildPhase'))
        tests = set(paths_in_phase(objects, self.targets['QRCatcherTests'], 'PBXSourcesBuildPhase'))
        old_targets = target_map(self.original)
        old_app = set(paths_in_phase(self.original['objects'], old_targets['QRCatcher'], 'PBXSourcesBuildPhase'))
        old_tests = set(paths_in_phase(self.original['objects'], old_targets['QRCatcherTests'], 'PBXSourcesBuildPhase'))
        self.assertEqual(app - old_app, HELPERS)
        self.assertEqual(old_app - app, set())
        self.assertEqual(old_tests - tests, HELPERS)
        self.assertEqual(tests - old_tests, set())
        self.assertEqual(app & HELPERS, HELPERS)
        self.assertEqual(tests & HELPERS, set())

    def test_exact_watch_copy_and_one_parent_dependency(self):
        objects = self.watch['objects']
        app = self.targets['QRCatcher']
        phases = [objects[key] for key in app['buildPhases']]
        copies = [node for node in phases if node['isa'] == 'PBXCopyFilesBuildPhase']
        self.assertEqual(len(copies), 1)
        copy = copies[0]
        self.assertEqual(copy['name'], 'Embed Watch Content')
        self.assertEqual(copy['dstPath'], '$(CONTENTS_FOLDER_PATH)/Watch')
        self.assertEqual(copy['dstSubfolderSpec'], 16)
        self.assertEqual(len(copy['files']), 1)
        file = objects[objects[copy['files'][0]]['fileRef']]
        self.assertEqual(file['path'], 'QRCatcherWatch.app')
        self.assertEqual(len(app['dependencies']), 1)
        dependency = objects[app['dependencies'][0]]
        self.assertEqual(objects[dependency['target']]['name'], 'QRCatcherWatch')
        self.assertEqual(objects[dependency['targetProxy']]['containerPortal'], self.watch['rootObject'])

    def test_latest_launch_source_only_reenables_existing_receiver_activation(self):
        source = (ROOT / 'QRCatcher/AppDelegate.m').read_text()
        for debug in (0, 1):
            integrated = preprocess(source, debug, None)
            explicit = preprocess(source, debug, 0)
            isolated = preprocess(source, debug, 1)
            self.assertEqual(integrated, explicit)
            self.assertEqual(integrated.count('[[QRWatchPhoneService shared] activate];'), 1)
            self.assertNotIn('[[QRWatchPhoneService shared] activate];', isolated)
            if not debug:
                self.assertEqual(integrated.replace('    [[QRWatchPhoneService shared] activate];\n', ''), isolated)
        for config_id in self.watch['objects'][self.targets['QRCatcher']['buildConfigurationList']]['buildConfigurations']:
            definitions = self.watch['objects'][config_id]['buildSettings'].get('GCC_PREPROCESSOR_DEFINITIONS', [])
            self.assertFalse(any('QRCATCHER_IOS_ONLY_RELEASE' in value for value in definitions))

    def test_existing_receiver_preserves_no_phone_history_semantics(self):
        receiver = (ROOT / 'QRCatcher/QRWatchPhoneService.m').read_text()
        for marker in ('QRHistoryStore', 'recordPayload:', 'managedObjectContext', 'presentViewController:'):
            self.assertNotIn(marker, receiver)
        self.assertIn('performIfCurrent:ticket', receiver)
        self.assertIn('decodedResponseForRequestData:', receiver)
        self.assertIn('transferFile:output', receiver)
        self.assertIn('session:(WCSession *)session didReceiveFile:', receiver)

    def test_schemes_bind_only_selected_project_and_release_archive_parent(self):
        for name, expected in [('QRCatcher', 'QRCatcher.app'), ('QRCatcherWatch', 'QRCatcherWatch.app')]:
            scheme = ET.parse(self.root / PROJECT / 'xcshareddata/xcschemes' / (name + '.xcscheme'))
            self.assertEqual(scheme.find('ArchiveAction').get('buildConfiguration'), 'Release')
            self.assertEqual(scheme.findall('.//ExecutionAction'), [])
            entries = scheme.findall('./BuildAction/BuildActionEntries/BuildActionEntry')
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].get('buildForArchiving'), 'YES')
            self.assertEqual(entries[0].find('BuildableReference').get('BuildableName'), expected)
            self.assertTrue(all(ref.get('ReferencedContainer') == 'container:' + PROJECT
                                for ref in scheme.findall('.//BuildableReference')))

    def test_unsigned_archive_plan_is_simulator_free_and_not_signing_authority(self):
        plan = json.loads((ROOT / 'docs/IOS_WATCH_UNSIGNED_ARCHIVE_PLAN.json').read_text())
        self.assertFalse(plan['native_execution_authorized'])
        self.assertFalse(plan['signing_authorized'])
        self.assertFalse(plan['upload_authorized'])
        command = plan['archive_command']
        self.assertEqual(command[command.index('-project') + 1], PROJECT)
        self.assertEqual(command[command.index('-scheme') + 1], 'QRCatcher')
        self.assertEqual(command[command.index('-destination') + 1], 'generic/platform=iOS')
        self.assertIn('CODE_SIGNING_ALLOWED=NO', command)
        self.assertIn('CODE_SIGNING_REQUIRED=NO', command)
        self.assertIn('ONLY_ACTIVE_ARCH=NO', command)
        self.assertNotIn('-quiet', command)
        self.assertFalse(any(value.startswith('ARCHS=') or 'simctl' in value or 'Simulator' in value
                             or 'allowProvisioning' in value for value in command))
        self.assertEqual(plan['current_source_version'], {'marketing': '1.1', 'build': '2', 'upload_eligible': False})

    def test_unknown_profile_fails_without_writes(self):
        before = {name: inventory(self.root / name) for name in
                  ('QRCatcher.xcodeproj', 'QRCatcher-iOS-Only.xcodeproj', PROJECT)}
        result = subprocess.run(self.command + ['--profile', 'ios-watch-sign'], capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, {name: inventory(self.root / name) for name in before})


if __name__ == '__main__':
    unittest.main()
