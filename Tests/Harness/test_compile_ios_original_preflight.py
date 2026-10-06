"""Real synthetic package gates plus closed command/budget/identity admission.

Compiler operations are simulated; these tests claim no Apple compilation,
runtime, signature, Store, or external qualification result.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'Tests/Harness'))
import compile_ios_original_preflight as preflight
import ios_original_release_route as route
import verify_ios_only_release as gate
import test_ios_only_release_package as package_fixtures

IDENTITY = {'job': 'preflight', 'scope': '', 'project': 'QRCatcher-iOS-Only.xcodeproj',
            'scheme': 'QRCatcher', 'source_sha': 'a' * 40, 'workflow_sha': 'a' * 40}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class OriginalIOSPreflightTests(unittest.TestCase):
    def setUp(self):
        isolation = patch.dict(os.environ)
        isolation.start()
        self.addCleanup(isolation.stop)
        for key in ('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED', 'QRCATCHER_OWNED_PROCESS_BARRIER',
                    'GITHUB_ENV', 'GITHUB_WORKSPACE'):
            os.environ.pop(key, None)
        self.temp = package_fixtures.owned_temporary_directory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(strict=True)
        self.old = Path.cwd()
        os.chdir(self.base)
        self.addCleanup(os.chdir, self.old)
        os.environ['GITHUB_WORKSPACE'] = str(Path.cwd())
        os.environ['QRCATCHER_OWNED_PROCESS_BARRIER'] = str(Path.cwd() / 'build/owned-process-cleanup.json')
        os.environ['GITHUB_ENV'] = str(Path.cwd() / 'job-env')
        self.clock = Clock()
        self.calls = []

    def test_actual_temporary_alias_preserves_success_and_fault_barriers(self):
        alias = self.base / 'temporary-alias'
        alias.symlink_to(self.base, target_is_directory=True)
        with patch.object(tempfile, 'tempdir', str(alias)), patch.dict(os.environ, TMPDIR=str(alias)):
            for method in ('test_complete_schedule_fixed_original_project_and_hosted_ui_test_scheme',
                           'test_late_unclean_unknown_or_foreign_completion_latches_and_stops',
                           'test_unknown_return_and_execution_exception_cannot_launch_following_command'):
                with self.subTest(method=method):
                    fixture = OriginalIOSPreflightTests(method)
                    try:
                        fixture.setUp()
                        self.assertNotEqual(Path(fixture.temp.name), fixture.base)
                        self.assertEqual(Path(fixture.temp.name).parent, alias)
                        self.assertEqual(Path.cwd(), fixture.base)
                        getattr(fixture, method)()
                    finally:
                        fixture.doCleanups()

    def debug_products(self):
        fixture = package_fixtures.IOSOnlyPackageTests()
        fixture.setUp()
        try:
            fixture.hosted(ui_target=True)
            shutil.copytree(fixture.base / 'Build', Path('build/iOS/Build'))
        finally:
            fixture.doCleanups()

    def release_archive(self):
        fixture = package_fixtures.IOSOnlyPackageTests()
        fixture.setUp()
        try:
            shutil.copytree(fixture.archive(), preflight.ARCHIVE)
        finally:
            fixture.doCleanups()

    def execute(self, command, seconds, **options):
        index = len(self.calls)
        self.calls.append((list(command), seconds, options))
        self.assertEqual((command, seconds), (preflight.PHASES[index][2], preflight.PHASES[index][1]))
        self.assertEqual(options, {'output_limit': 16 * 1024 * 1024, 'tail_limit': 16 * 1024})
        label = preflight.PHASES[index][0]
        code = 0
        if label == 'debug-build':
            self.debug_products()
        elif label == 'release-archive':
            self.release_archive()
        else:
            try:
                # Exercise the real read-only parsers against actual bound bytes.
                if label == 'debug-package':
                    code = route.debug_package()
                else:
                    code = gate.main(command[2:])
            except (OSError, ValueError):
                code = 1
        self.clock.now += 1
        return code, 'synthetic compilation; real bounded package inspection', {
            'command': list(command), 'timeout_seconds': seconds, 'exit': code,
            'state': 'completed', 'cleanup_confirmed': True, 'elapsed_seconds': 1.0, 'output_bytes': 64}

    def run_preflight(self, execute=None, identity=IDENTITY):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(preflight.time, 'monotonic', self.clock))
            stack.enter_context(patch.object(preflight, 'execute', side_effect=execute or self.execute))
            if identity is not None:
                stack.enter_context(patch.object(route, 'current_identity', return_value=identity))
            stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('Package gate must remain pure')))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            code = preflight.main()
        report = json.loads((preflight.ROOT / 'summary.json').read_text())
        return code, report

    def real_source(self):
        canonical = ROOT / route.CANONICAL
        destination = Path(route.CANONICAL)
        destination.parent.mkdir(parents=True)
        shutil.copyfile(canonical, destination)
        Path(route.WORKFLOW).write_text(route.render_workflow(destination.read_text()))
        os.environ.update(GITHUB_REPOSITORY=route.REPOSITORY, GITHUB_REF=route.REF,
                          GITHUB_WORKFLOW_REF=route.WORKFLOW_REF, GITHUB_SHA='a' * 40,
                          GITHUB_WORKFLOW_SHA='a' * 40, GITHUB_EVENT_NAME='push',
                          IOS_FIRST_RELEASE_CANDIDATE_ONLY='true', RUNNER_OS='macOS', RUNNER_ARCH='ARM64',
                          GITHUB_JOB='preflight', GITHUB_RUN_ID='42', GITHUB_RUN_ATTEMPT='1')
        os.environ.pop('EVIDENCE_SCOPE', None)

    def test_complete_schedule_fixed_original_project_and_hosted_ui_test_scheme(self):
        self.assertEqual(preflight.ADMISSION_SECONDS + preflight.required_seconds(0), 900)
        self.assertEqual([cap for _, cap, _ in preflight.PHASES], [390, 20, 390, 20])
        code, report = self.run_preflight()
        self.assertEqual(code, 0)
        self.assertTrue(report['passed'])
        self.assertFalse(report['release_qualification'])
        self.assertEqual(report['runtime_tests_executed'], 0)
        self.assertEqual([entry[0][1] for entry in self.calls],
                         ['build-for-testing', 'scripts/ios_original_release_route.py', 'archive', 'scripts/verify_ios_only_release.py'])
        for command, _, _ in self.calls:
            self.assertNotIn('-allowProvisioningUpdates', command)
            self.assertNotIn('test-without-building', command)
            if command[0] == 'xcodebuild':
                self.assertIn('CODE_SIGNING_ALLOWED=NO', command)
                self.assertEqual(command[command.index('-project') + 1], 'QRCatcher-iOS-Only.xcodeproj')
                self.assertEqual(command[command.index('-scheme') + 1], 'QRCatcher')
        scheme = ET.fromstring((ROOT / 'QRCatcher-iOS-Only.xcodeproj/xcshareddata/xcschemes/QRCatcher.xcscheme').read_text())
        self.assertEqual({item.get('BlueprintName') for item in scheme.findall('./TestAction/Testables/TestableReference/BuildableReference')},
                         {'QRCatcherTests', 'QRCatcherUITests'})

    def test_real_debug_shipping_scope_and_release_zero_xctest_reports(self):
        code, report = self.run_preflight()
        self.assertEqual(code, 0)
        debug = json.loads(Path(preflight.PACKAGE_REPORTS['debug-package']).read_text())
        release = json.loads(Path(preflight.PACKAGE_REPORTS['release-package']).read_text())
        self.assertEqual([image['path'] for image in debug['mach_o']], ['QRCatcher'])
        self.assertEqual(debug['hosted_tests']['xctestrun']['binding']['host'], str(Path(preflight.DEBUG_APP).absolute()))
        self.assertEqual(debug['hosted_tests']['xctestrun']['binding']['bundle'],
                         str((Path(preflight.DEBUG_APP) / 'PlugIns/QRCatcherTests.xctest').absolute()))
        self.assertTrue(any('WatchConnectivity' in item['marker'] for item in debug['hosted_tests']['permitted_test_only_markers']))
        self.assertIsNone(release['hosted_tests'])
        self.assertEqual(release['scope'], 'ios-only-shipping-package')
        self.assertEqual([image['path'] for image in release['mach_o']], ['QRCatcher'])
        for label, receipt in report['package_reports'].items():
            self.assertEqual(receipt['sha256'], hashlib.sha256(Path(receipt['path']).read_bytes()).hexdigest())
        self.assertLessEqual((preflight.ROOT / 'summary.json').stat().st_size, 64 * 1024)
        self.assertEqual({p.name for p in preflight.ROOT.iterdir()},
                         {'summary.json', 'debug-build.log', 'debug-package.log', 'release-archive.log', 'release-package.log'})

    def test_shipping_helper_cannot_use_hosted_exception_and_archive_never_runs(self):
        def command(args, seconds, **options):
            result = self.execute(args, seconds, **options)
            if len(self.calls) == 1:
                Path(preflight.DEBUG_APP, 'QRCatcher').write_bytes(package_fixtures.macho(platform=7, markers=b'QRWatchPhoneService\0'))
            return result
        code, report = self.run_preflight(command)
        self.assertEqual(code, 1)
        self.assertFalse(report['passed'])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(json.loads(Path(preflight.PACKAGE_REPORTS['debug-package']).read_text())['reason'], 'watch_presence')
        self.assertFalse(Path(preflight.ARCHIVE).exists())

    def test_release_xctest_marker_is_rejected_after_archive(self):
        def command(args, seconds, **options):
            result = self.execute(args, seconds, **options)
            if len(self.calls) == 3:
                app = Path(preflight.ARCHIVE) / 'Products/Applications/QRCatcher.app'
                (app / 'QRCatcher').write_bytes(package_fixtures.macho(markers=b'XCTestCase\0'))
            return result
        code, report = self.run_preflight(command)
        self.assertEqual(code, 1)
        self.assertEqual(len(self.calls), 4)
        self.assertFalse(report['passed'])
        self.assertEqual(json.loads(Path(preflight.PACKAGE_REPORTS['release-package']).read_text())['reason'], 'release_diagnostics')

    def test_missing_actual_xctestrun_stops_before_archive(self):
        def command(args, seconds, **options):
            result = self.execute(args, seconds, **options)
            if len(self.calls) == 1:
                for path in Path('build/iOS/Build/Products').glob('*.xctestrun'):
                    path.unlink()
            return result
        code, report = self.run_preflight(command)
        self.assertEqual(code, 1)
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(report['passed'])
        self.assertFalse(Path(preflight.ARCHIVE).exists())

    def test_actual_xctestrun_owner_binding_cannot_be_substituted(self):
        def command(args, seconds, **options):
            result = self.execute(args, seconds, **options)
            if len(self.calls) == 1:
                xctestrun = next(Path('build/iOS/Build/Products').glob('*.xctestrun'))
                info = plistlib.loads(xctestrun.read_bytes())
                info['QRCatcherTests']['TestHostBundleIdentifier'] = 'example.Other'
                xctestrun.write_bytes(plistlib.dumps(info))
            return result
        code, report = self.run_preflight(command)
        self.assertEqual(code, 1)
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(report['passed'])
        self.assertEqual(json.loads(Path(preflight.PACKAGE_REPORTS['debug-package']).read_text())['reason'], 'test_host_binding')

    def test_success_exit_without_complete_package_report_stops_before_archive(self):
        def command(args, seconds, **options):
            result = self.execute(args, seconds, **options)
            if len(self.calls) == 2:
                Path(preflight.PACKAGE_REPORTS['debug-package']).unlink()
            return result
        code, report = self.run_preflight(command)
        self.assertEqual(code, 1)
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(report['passed'])

    def test_nonzero_completed_compiler_stops_without_a_following_command(self):
        def command(args, seconds, **options):
            _, tail, operation = self.execute(args, seconds, **options)
            operation['exit'] = 65
            return 65, tail, operation
        code, report = self.run_preflight(command)
        self.assertEqual(code, 65)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(report['passed'])
        self.assertNotIn('cleanup_unconfirmed', report)

    def test_late_unclean_unknown_or_foreign_completion_latches_and_stops(self):
        defects = [dict(cleanup_confirmed=False), dict(cleanup_confirmed=None), dict(state='unknown'),
                   dict(state='timed_out'), dict(elapsed_seconds=392), dict(elapsed_seconds=393), dict(elapsed_seconds=float('inf')),
                   dict(elapsed_seconds=float('nan')), dict(elapsed_seconds=True), dict(elapsed_seconds=-1),
                   dict(command=['xcodebuild', 'other']),
                   dict(timeout_seconds=391), dict(exit=1), dict(exit=False)]
        for defect in defects:
            with self.subTest(defect=defect), package_fixtures.owned_temporary_directory() as nested:
                nested = Path(nested).resolve(strict=True)
                os.chdir(nested)
                os.environ.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED', None)
                os.environ['GITHUB_WORKSPACE'] = str(nested)
                os.environ['GITHUB_ENV'] = str(Path(nested) / 'job-env')
                os.environ['QRCATCHER_OWNED_PROCESS_BARRIER'] = str(Path(nested) / 'build/owned-process-cleanup.json')
                self.calls.clear()
                self.clock.now = 0
                def command(args, seconds, **options):
                    code, tail, operation = self.execute(args, seconds, **options)
                    operation.update(defect)
                    # Nonfinite metadata cannot be copied into JSON evidence.
                    return code, tail, operation
                code, report = self.run_preflight(command)
                self.assertEqual(code, 126)
                self.assertEqual(len(self.calls), 1)
                self.assertTrue(report['cleanup_unconfirmed'])
                self.assertEqual(os.environ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED'], 'true')
                self.assertTrue(Path('build/owned-process-cleanup.json').is_file())
                self.assertIn('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED=true', Path('job-env').read_text())
                os.chdir(self.base)

    def test_late_wall_clock_return_cannot_be_hidden_by_timely_metadata(self):
        def command(args, seconds, **options):
            result = self.execute(args, seconds, **options)
            self.clock.now = seconds + 2
            return result
        code, report = self.run_preflight(command)
        self.assertEqual(code, 126)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(report['cleanup_unconfirmed'])

    def test_complete_remaining_schedule_is_required_before_first_command(self):
        calls = 0
        def identity():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.clock.now = 20.001
            return IDENTITY
        with patch.object(route, 'current_identity', side_effect=identity):
            code, report = self.run_preflight(identity=None)
        self.assertEqual(code, 124)
        self.assertEqual(self.calls, [])
        self.assertEqual(report['operations'][0]['required_seconds'], 880)
        self.assertEqual(report['operations'][0]['state'], 'not_run_total_preflight_schedule')

    def test_insufficient_remaining_schedule_never_starts_the_following_gate(self):
        identities = 0
        def identity():
            nonlocal identities
            identities += 1
            if identities == 3:
                self.clock.now += 30
            return IDENTITY
        def command(args, seconds, **options):
            code, tail, operation = self.execute(args, seconds, **options)
            self.clock.now = 391.999
            operation['elapsed_seconds'] = 391.999
            return code, tail, operation
        with patch.object(route, 'current_identity', side_effect=identity):
            code, report = self.run_preflight(command, identity=None)
        self.assertEqual(code, 124)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(report['operations'][-1]['label'], 'debug-package')
        self.assertEqual(report['operations'][-1]['state'], 'not_run_total_preflight_schedule')

    def test_unknown_return_and_execution_exception_cannot_launch_following_command(self):
        for failure in ('malformed', 'exception'):
            with self.subTest(failure=failure), package_fixtures.owned_temporary_directory() as nested:
                nested = Path(nested).resolve(strict=True)
                os.chdir(nested)
                os.environ.pop('QRCATCHER_OWNED_CLEANUP_UNCONFIRMED', None)
                os.environ['GITHUB_WORKSPACE'] = str(nested)
                os.environ['GITHUB_ENV'] = str(Path(nested) / 'job-env')
                os.environ['QRCATCHER_OWNED_PROCESS_BARRIER'] = str(Path(nested) / 'build/owned-process-cleanup.json')
                self.calls.clear()
                def command(args, seconds, **options):
                    self.calls.append(args)
                    if failure == 'exception':
                        raise OSError('Synthetic unknown compiler completion')
                    return 0, 'synthetic', None
                code, report = self.run_preflight(command)
                self.assertEqual(code, 126)
                self.assertEqual(len(self.calls), 1)
                self.assertTrue(report['cleanup_unconfirmed'])
                os.chdir(self.base)

    def test_identity_rejects_platform_job_before_compilation(self):
        code, report = self.run_preflight(identity=dict(IDENTITY, job='platform', scope='ipad_mini'))
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])
        self.assertIn('preflight job', report['failure'])

    def test_preexisting_products_cannot_satisfy_a_new_preflight(self):
        Path('build/iOS').mkdir(parents=True)
        code, report = self.run_preflight()
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])
        self.assertIn('output already exists', report['failure'])

    def test_unknown_initial_clock_latches_without_starting_a_command(self):
        self.clock.now = float('nan')
        code, report = self.run_preflight()
        self.assertEqual(code, 126)
        self.assertEqual(self.calls, [])
        self.assertTrue(report['cleanup_unconfirmed'])
        self.assertEqual(report['operations'][0]['state'], 'unknown_preflight_clock')

    def test_preexisting_uncertainty_barrier_blocks_all_commands(self):
        Path('build').mkdir()
        Path('build/owned-process-cleanup.json').write_text('{"blocked": true}\n')
        code, report = self.run_preflight()
        self.assertEqual(code, 126)
        self.assertEqual(self.calls, [])
        self.assertTrue(report['cleanup_unconfirmed'])

    def test_utf8_log_tail_remains_at_most_16_kib(self):
        def command(args, seconds, **options):
            code, _, operation = self.execute(args, seconds, **options)
            return code, '\U0001f60a' * (16 * 1024), operation
        code, _ = self.run_preflight(command)
        self.assertEqual(code, 0)
        for path in preflight.ROOT.glob('*.log'):
            self.assertLessEqual(path.stat().st_size, 16 * 1024)
            path.read_text(encoding='utf-8')

    def test_actual_source_workflow_ref_and_sha_binding(self):
        self.real_source()
        identity = route.current_identity()
        self.assertEqual(identity['job'], 'preflight')
        for key, bad in [('GITHUB_REF', 'refs/heads/codex/apple-platforms'),
                         ('GITHUB_WORKFLOW_REF', route.REPOSITORY + '/.github/workflows/apple-platforms.yml@' + route.REF),
                         ('GITHUB_WORKFLOW_SHA', 'b' * 40), ('GITHUB_REPOSITORY', 'elsewhere/QRCatcher'),
                         ('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('EVIDENCE_SCOPE', 'ipad_mini')]:
            with self.subTest(key=key), patch.dict(os.environ, {key: bad}):
                with self.assertRaises(ValueError):
                    route.current_identity()
        code, report = self.run_preflight(identity=None)
        self.assertEqual(code, 0)
        self.assertEqual(report['identity']['source_sha'], 'a' * 40)
        self.assertEqual(report['identity']['workflow_sha256'], hashlib.sha256(Path(route.WORKFLOW).read_bytes()).hexdigest())

    def test_actual_changed_workflow_blocks_next_command_without_rebinding(self):
        self.real_source()
        def command(args, seconds, **options):
            result = self.execute(args, seconds, **options)
            with Path(route.WORKFLOW).open('a') as output:
                output.write('# changed selected source\n')
            return result
        code, report = self.run_preflight(command, identity=None)
        self.assertEqual(code, 1)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(report['passed'])
        self.assertIn('workflow differs', report['failure'])


if __name__ == '__main__':
    unittest.main()
