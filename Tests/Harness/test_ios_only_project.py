"""Real generated graph and portable conditional-source checks; no Apple build claim."""
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

ROOT = Path(__file__).resolve().parents[2]
HELPERS = {'QRCatcher/QRWatchPhoneService.m', 'QRCatcher/QRWatchSessionGate.m'}
DEFAULT_HASHES = {
    'project.pbxproj': 'b88dfe4e98ee99dbab780abe14872fcafbfd88b3dfc02becbb084dc7e243bca0',
    'xcshareddata/xcschemes/QRCatcher.xcscheme': 'f6b948861890a2e24b07a0c6b084413ea634f075d9d42209fdbe171de4b23c98',
    'xcshareddata/xcschemes/QRCatcherMac.xcscheme': '84b1f148d9581d1b5766bc0e684360eb3bbf9ba4b9d465491c3d37592ce9544e',
    'xcshareddata/xcschemes/QRCatcherMacSandbox.xcscheme': '0742284b07729e93fb68923d642a5a4d4f6b82be9b1dab226536a564657ee008',
    'xcshareddata/xcschemes/QRCatcherTV.xcscheme': 'af5ba7c0872055ab6a1775efa63e60175394182bd3b3d2980722f36bb6a4a3ec',
    'xcshareddata/xcschemes/QRCatcherVision.xcscheme': '8ed2793f9f09c3de5d61f512d3ee283753d2cc0d6c0c216ff7a8a9dd387dd42e',
    'xcshareddata/xcschemes/QRCatcherWatch.xcscheme': 'df9df2e65d8ae6768ce17a4b24013303bce9cacf21d44643796980863f6b6527'}


def parse_project(path):
    """Parse the generator's quoted OpenStep subset independently of its object builder."""
    source = path.read_text().split('\n', 1)[1]
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[{}();=,]|-?\d+', source)
    index = 0

    def take(expected=None):
        nonlocal index
        token = tokens[index]
        index += 1
        if expected is not None and token != expected:
            raise ValueError('Unexpected OpenStep token ' + token)
        return token

    def value():
        token = take()
        if token == '{':
            result = {}
            while tokens[index] != '}':
                key = json.loads(take())
                take('=')
                result[key] = value()
                take(';')
            take('}')
            return result
        if token == '(':
            result = []
            while tokens[index] != ')':
                result.append(value())
                if tokens[index] != ')':
                    take(',')
            take(')')
            return result
        return json.loads(token)

    result = value()
    if index != len(tokens):
        raise ValueError('Unconsumed OpenStep tokens')
    return result


def references(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)
    elif isinstance(value, str) and re.fullmatch('[A-F0-9]{24}', value):
        yield value


def paths_in_phase(objects, target, phase_kind):
    phases = [objects[key] for key in target['buildPhases'] if objects[key]['isa'] == phase_kind]
    files = [objects[objects[key]['fileRef']] for phase in phases for key in phase['files']]
    return [entry.get('path', 'localized:' + entry.get('name', '')) for entry in files]


def preprocess(source, debug, ios_only=None):
    cc = shutil.which('cc')
    if not cc:
        raise RuntimeError('A standard portable C preprocessor is required')
    source = re.sub(r'^\s*#\s*(?:import|include)[^\n]*', '', source, flags=re.M)
    command = [cc, '-E', '-P', '-x', 'c', '-undef', '-DDEBUG=' + str(debug)]
    if ios_only is not None:
        command += ['-DQRCATCHER_IOS_ONLY_RELEASE=' + str(ios_only)]
    return subprocess.run(command + ['-'], input=source, capture_output=True, text=True,
                          check=True, timeout=10).stdout


class IOSOnlyProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        (cls.root / 'scripts').mkdir()
        shutil.copyfile(ROOT / 'scripts/generate_project.py', cls.root / 'scripts/generate_project.py')
        for directory in ['Shared', 'QRCatcher', 'QRCatcherTests', 'QRCatcherUITests',
                          'QRCatcherMac', 'QRCatcherMacTests', 'QRCatcherMacUITests',
                          'QRCatcherVision', 'QRCatcherVisionTests', 'QRCatcherVisionUITests',
                          'QRCatcherTV', 'QRCatcherTVTests', 'QRCatcherTVUITests',
                          'QRCatcherWatch', 'QRCatcherWatchTests', 'QRCatcherWatchUITests',
                          'ThirdParty', 'Tests']:
            (cls.root / directory).symlink_to(ROOT / directory, target_is_directory=True)
        cls.command = [sys.executable, str(cls.root / 'scripts/generate_project.py')]
        subprocess.run(cls.command, check=True, capture_output=True, timeout=30)
        cls.default = parse_project(cls.root / 'QRCatcher.xcodeproj/project.pbxproj')
        subprocess.run(cls.command + ['--profile', 'ios-only'], check=True, capture_output=True, timeout=30)
        cls.ios = parse_project(cls.root / 'QRCatcher-iOS-Only.xcodeproj/project.pbxproj')
        cls.default_targets = {value['name']: value for value in cls.default['objects'].values()
                               if value['isa'] == 'PBXNativeTarget'}
        cls.targets = {value['name']: value for value in cls.ios['objects'].values()
                       if value['isa'] == 'PBXNativeTarget'}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_default_generation_preserves_every_frozen_project_and_scheme_byte(self):
        for name, expected in DEFAULT_HASHES.items():
            self.assertEqual(hashlib.sha256((self.root / 'QRCatcher.xcodeproj' / name).read_bytes()).hexdigest(), expected, name)

    def test_profiles_replay_independently_and_ios_output_is_checked_in_exactly(self):
        path = self.root / 'QRCatcher-iOS-Only.xcodeproj'
        before = {p.relative_to(path): p.read_bytes() for p in path.rglob('*') if p.is_file()}
        subprocess.run(self.command + ['--profile', 'ios-only'], check=True, capture_output=True, timeout=30)
        subprocess.run(self.command + ['--profile', 'all-platforms'], check=True, capture_output=True, timeout=30)
        after = {p.relative_to(path): p.read_bytes() for p in path.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(before, {p.relative_to(ROOT / path.name): p.read_bytes()
                                 for p in (ROOT / path.name).rglob('*') if p.is_file()})

    def test_closed_cli_rejects_unknown_abbreviated_and_extra_arguments(self):
        for args in [['--profile', 'iphone'], ['--prof', 'ios-only'], ['ios-only'], ['--output', 'x']]:
            result = subprocess.run(self.command + args, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2, args)

    def test_closed_ios_graph_has_only_three_targets_and_no_dangling_or_orphan_objects(self):
        self.assertEqual(set(self.targets), {'QRCatcher', 'QRCatcherTests', 'QRCatcherUITests'})
        objects = self.ios['objects']
        visited = set()

        def visit(key):
            self.assertIn(key, objects)
            if key in visited:
                return
            visited.add(key)
            for ref in references(objects[key]):
                visit(ref)

        visit(self.ios['rootObject'])
        self.assertEqual(visited, set(objects))
        emitted = json.dumps(objects)
        for marker in ['QRCatcherWatch', 'watchkitapp', 'Embed Watch Content', 'QRCatcherMac',
                       'QRCatcherVision', 'QRCatcherTV', 'ThirdParty/ZXingCpp']:
            self.assertNotIn(marker, emitted)
        # The original Shared header navigator may contain the portable decoder
        # declaration. Actual compiled consumers, not folder names, prove scope.
        for target in self.targets.values():
            for path in paths_in_phase(objects, target, 'PBXSourcesBuildPhase'):
                self.assertNotIn('Shared/PortableQR', path)

    def test_app_has_no_dependencies_or_copy_phases_and_tests_only_depend_on_host(self):
        objects = self.ios['objects']
        app = self.targets['QRCatcher']
        self.assertEqual(app['dependencies'], [])
        self.assertEqual([objects[key]['isa'] for key in app['buildPhases']],
                         ['PBXSourcesBuildPhase', 'PBXFrameworksBuildPhase', 'PBXResourcesBuildPhase'])
        app_id = next(key for key, value in objects.items() if value == app)
        for name in ['QRCatcherTests', 'QRCatcherUITests']:
            deps = [objects[key] for key in self.targets[name]['dependencies']]
            self.assertEqual(len(deps), 1)
            self.assertEqual(deps[0]['target'], app_id)
            self.assertEqual(objects[deps[0]['targetProxy']]['remoteGlobalIDString'], app_id)

    def test_helper_implementation_owners_move_from_default_app_to_hosted_test_only(self):
        for project, expected in [(self.default, 'QRCatcher'), (self.ios, 'QRCatcherTests')]:
            objects = project['objects']
            targets = [value for value in objects.values() if value['isa'] == 'PBXNativeTarget']
            for helper in HELPERS:
                consumers = [target['name'] for target in targets
                             if helper in paths_in_phase(objects, target, 'PBXSourcesBuildPhase')]
                self.assertEqual(consumers, [expected], helper)
                self.assertEqual(sum(paths_in_phase(objects, target, 'PBXSourcesBuildPhase').count(helper)
                                     for target in targets), 1, helper)

    def test_actual_app_local_header_import_closure_excludes_watch_helpers_and_framework(self):
        cc = shutil.which('cc')
        self.assertIsNotNone(cc)
        header_paths = [ROOT / 'QRCatcher', ROOT / 'Shared/Domain', ROOT / 'Shared/Image']
        pending = [ROOT / path for path in paths_in_phase(self.ios['objects'], self.targets['QRCatcher'], 'PBXSourcesBuildPhase') if path.endswith('.m')]
        visited = set()
        imports = set()
        while pending:
            path = pending.pop()
            if path in visited:
                continue
            visited.add(path)
            # Mark actual directives before preprocessing, preserving their
            # conditional position without fabricating Apple SDK headers.
            marked = re.sub(r'^\s*#\s*(?:import|include)\s+([<"])([^>"\n]+)[>"]',
                            lambda m: 'QR_IMPORT_' + ('LOCAL' if m[1] == '"' else 'SYSTEM') + ' ' + json.dumps(m[2]),
                            path.read_text(), flags=re.M)
            result = subprocess.run([cc, '-E', '-P', '-x', 'c', '-undef', '-DDEBUG=1',
                                     '-DQRCATCHER_IOS_ONLY_RELEASE=1', '-'], input=marked,
                                    capture_output=True, text=True, check=True, timeout=10)
            for kind, name in re.findall(r'QR_IMPORT_(LOCAL|SYSTEM)\s+"([^"]+)"', result.stdout):
                imports.add(name)
                if kind == 'LOCAL':
                    candidates = [base / name for base in [path.parent] + header_paths]
                    resolved = next((candidate for candidate in candidates if candidate.is_file()), None)
                    self.assertIsNotNone(resolved, (path, name))
                    pending.append(resolved)
        for forbidden in ['QRWatchPhoneService.h', 'QRWatchSessionGate.h', 'WatchConnectivity/WatchConnectivity.h']:
            self.assertNotIn(forbidden, imports)
        self.assertIn(ROOT / 'QRCatcher/AppDelegate.h', visited)
        self.assertIn('AVFoundation/AVFoundation.h', imports)
        self.assertIn('PhotosUI/PhotosUI.h', imports)
        self.assertIn('CoreData/CoreData.h', imports)

    def test_all_other_ios_sources_resources_settings_and_host_identity_are_preserved(self):
        for name, target in self.targets.items():
            old = self.default_targets[name]
            old_sources = paths_in_phase(self.default['objects'], old, 'PBXSourcesBuildPhase')
            new_sources = paths_in_phase(self.ios['objects'], target, 'PBXSourcesBuildPhase')
            if name == 'QRCatcher':
                self.assertEqual(new_sources, [path for path in old_sources if path not in HELPERS])
            elif name == 'QRCatcherTests':
                self.assertEqual(new_sources[:len(old_sources)], old_sources)
                self.assertEqual(set(new_sources[len(old_sources):]), HELPERS)
            else:
                self.assertEqual(new_sources, old_sources)
            self.assertEqual(paths_in_phase(self.ios['objects'], target, 'PBXResourcesBuildPhase'),
                             paths_in_phase(self.default['objects'], old, 'PBXResourcesBuildPhase'))
            old_configs = self.default['objects'][old['buildConfigurationList']]['buildConfigurations']
            for key in old_configs:
                original = self.default['objects'][key]['buildSettings']
                expected = dict(original)
                if name == 'QRCatcher':
                    expected['GCC_PREPROCESSOR_DEFINITIONS'] = original.get('GCC_PREPROCESSOR_DEFINITIONS', ['$(inherited)']) + ['QRCATCHER_IOS_ONLY_RELEASE=1']
                self.assertEqual(self.ios['objects'][key]['buildSettings'], expected)

    def test_only_ios_app_debug_and_release_configs_receive_flag(self):
        objects = self.ios['objects']
        flagged = [value for value in objects.values() if value['isa'] == 'XCBuildConfiguration'
                   and 'QRCATCHER_IOS_ONLY_RELEASE=1' in value['buildSettings'].get('GCC_PREPROCESSOR_DEFINITIONS', [])]
        self.assertEqual(sorted(value['name'] for value in flagged), ['Debug', 'Release'])
        for value in flagged:
            self.assertEqual(value['buildSettings']['PRODUCT_BUNDLE_IDENTIFIER'], '100mango.QRCatcher')
            self.assertEqual(value['buildSettings']['TARGETED_DEVICE_FAMILY'], '1,2')

    def test_ios_scheme_preserves_all_actions_testables_and_archive_identity(self):
        default = (self.root / 'QRCatcher.xcodeproj/xcshareddata/xcschemes/QRCatcher.xcscheme').read_text()
        ios = (self.root / 'QRCatcher-iOS-Only.xcodeproj/xcshareddata/xcschemes/QRCatcher.xcscheme').read_text()
        self.assertEqual(ios, default.replace('container:QRCatcher.xcodeproj', 'container:QRCatcher-iOS-Only.xcodeproj'))
        parsed = ET.fromstring(ios)
        self.assertEqual([r.attrib['BlueprintName'] for r in parsed.findall('./TestAction/Testables/TestableReference/BuildableReference')], ['QRCatcherTests', 'QRCatcherUITests'])
        self.assertEqual(parsed.find('./ArchiveAction').attrib['buildConfiguration'], 'Release')
        self.assertEqual(len(list((self.root / 'QRCatcher-iOS-Only.xcodeproj/xcshareddata/xcschemes').glob('*.xcscheme'))), 1)

    def test_native_unit_source_inventory_preserves_twelve_seven_seven_four_cases(self):
        expected = {
            'QRCatcherTests.m': (12, '9c48f6dac92deff8383127febef1e302f4b9315ea184c2b6adcdf80ab3f63612'),
            'QRBoundedImageImportTests.m': (7, '8d103b5fcdd05f2abe69a05a0c3ed54799933825f7a9825412be11a89de06dbe'),
            'QRPhoneResultTests.m': (7, '6150384ea1b9e5aa490481163bac895b47cd653735d11a426946c4f51dac0555'),
            'QRWatchPhoneServiceTests.m': (4, '010ce18be9d3991a142dbe1dca3fd167aaf10f371ad0417987895a71982c8c5f')}
        self.assertEqual({p.name for p in (ROOT / 'QRCatcherTests').glob('*.m')}, set(expected))
        for name, (count, digest) in expected.items():
            data = (ROOT / 'QRCatcherTests' / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
            self.assertEqual(len(re.findall(r'-\s*\(void\)\s*test\w+\s*\{', data.decode())), count)

    def test_negative_default_flag_preserves_frozen_debug_and_release_preprocessor_outputs(self):
        source = (ROOT / 'QRCatcher/AppDelegate.m').read_text()
        for debug, expected in [(0, '4c03c71acb8be78611c66b11e92b31522a56eaae40a988d8998c986e7732707e'),
                                (1, '78e5613dcd4648f3f9f2368729bb21fd3fc3f724a9fea8159a9a107f5dd72df5')]:
            default = preprocess(source, debug)
            self.assertEqual(default, preprocess(source, debug, 0))
            self.assertEqual(hashlib.sha256(re.sub(r'\s+', '', default).encode()).hexdigest(), expected)

    def test_ios_flag_removes_only_activation_and_its_two_observation_calls(self):
        source = (ROOT / 'QRCatcher/AppDelegate.m').read_text()
        for debug in [0, 1]:
            default = preprocess(source, debug, 0)
            ios = preprocess(source, debug, 1)
            expected = default.replace('[[QRWatchPhoneService shared] activate];', '')
            for token in ['QRStartupWatchEnter', 'QRStartupWatchReturn']:
                expected = expected.replace('QRStartupObservationMark(' + token + ');', '')
                self.assertNotIn('QRStartupObservationMark(' + token + ');', ios)
            self.assertNotIn('QRWatchPhoneService', ios)
            self.assertEqual(re.sub(r'\s+', '', ios), re.sub(r'\s+', '', expected))
            self.assertIn('self.historyStore = [[QRHistoryStore alloc] initWithURL:URL];', ios)
            if debug:
                for token in ['QRStartupStoreEnter', 'QRStartupStoreReturn', 'QRStartupDelegateReturn']:
                    self.assertIn('QRStartupObservationMark(' + token + ');', ios)
            else:
                for token in ['QRStartup', '-ui-testing', '-reset-history', 'mini_startup_v1']:
                    self.assertNotIn(token, ios)

    def test_actual_import_condition_skips_watch_header_in_ios_profile(self):
        source = (ROOT / 'QRCatcher/AppDelegate.m').read_text()
        source = source.replace('#import "QRWatchPhoneService.h"', '#error WATCH_HEADER_IMPORTED')
        source = re.sub(r'^\s*#\s*(?:import|include)[^\n]*', '', source, flags=re.M)
        cc = shutil.which('cc')
        self.assertIsNotNone(cc)
        for flag, expected in [(0, 1), (1, 0)]:
            result = subprocess.run([cc, '-E', '-P', '-x', 'c', '-undef', '-DDEBUG=0',
                                     '-DQRCATCHER_IOS_ONLY_RELEASE=' + str(flag), '-'],
                                    input=source, text=True, capture_output=True, timeout=10)
            self.assertEqual(int(result.returncode != 0), expected)


if __name__ == '__main__':
    unittest.main()
