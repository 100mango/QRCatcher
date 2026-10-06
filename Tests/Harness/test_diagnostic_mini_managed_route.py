#!/usr/bin/env python3
"""Closed one-row route, pure real-marker source receipt and uncertainty tests."""
import contextlib
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import diagnostic_mini_managed_route as route

SHA = 'a' * 40
TREE = 'b' * 40


class MiniManagedRouteTests(unittest.TestCase):
    def setUp(self):
        self.canonical = (ROOT / route.CANONICAL).read_text()
        self.workflow = route.render_workflow(self.canonical)
        self.env = {'GITHUB_REPOSITORY': route.REPOSITORY, 'GITHUB_SHA': SHA,
            'GITHUB_WORKFLOW_SHA': SHA, 'GITHUB_REF': route.REF,
            'GITHUB_WORKFLOW_REF': route.WORKFLOW_REF, 'GITHUB_EVENT_NAME': 'push',
            'DIAGNOSTIC_ONLY': 'true', 'RUNNER_OS': 'macOS', 'RUNNER_ARCH': 'ARM64',
            'GITHUB_JOB': 'platform', 'EVIDENCE_SCOPE': 'ipad_mini',
            'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}

    @contextlib.contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory(prefix='qr-mini-route-source-') as name:
            root = Path(name).resolve(); (root / 'build').mkdir(); prior = Path.cwd()
            for path, text in ((route.CANONICAL, self.canonical), (route.WORKFLOW, self.workflow)):
                target = root / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(text)
            env = {**self.env, 'GITHUB_WORKSPACE': str(root), 'GITHUB_ENV': str(root / 'env'),
                'QRCATCHER_OWNED_PROCESS_BARRIER': str(root / 'build/owned-process-cleanup.json')}
            marker = root / 'build/ipad-mini-host-inflight.json'
            data = {'source': SHA, 'workflow_sha': SHA, 'run_id': '123', 'run_attempt': '1',
                'scope': 'ipad_mini', 'phase': 'host-prepare', 'owner_pid': os.getpid(),
                'command': ['bash', 'scripts/ipad_mini_prepare.sh']}
            marker.write_text(json.dumps(data)); marker.chmod(0o600)
            with patch.dict(os.environ, env, clear=True):
                os.chdir(root)
                try:
                    yield root, marker
                finally:
                    os.chdir(prior)

    def test_closed_scope_permissions_no_cancel_caps(self):
        record = route.identity(self.env, self.canonical, self.workflow)
        self.assertEqual(record['selected_scopes'], ['ipad_mini'])
        self.assertEqual(record['required_native_case_counts'], {'layout': 2, 'files': 1, 'photos': 1})
        self.assertEqual(record['permissions'], {'contents': 'read'})
        self.assertEqual(record['runner'], 'xcode-27')
        self.assertEqual(record['maximum_simultaneous_slots'], 1)
        self.assertFalse(record['cancel_in_progress']); self.assertFalse(record['release_qualification'])
        self.assertEqual((record['preflight_job_minutes'], record['platform_job_minutes'], record['mini_row_seconds']), (20, 50, 1920))
        self.assertIn("max-parallel: 1", self.workflow)

    def test_canonical_workflow_unchanged(self):
        self.assertEqual(hashlib.sha256(self.canonical.encode()).hexdigest(), route.CANONICAL_SHA256)
        self.assertIn('        - ipad_mini\n', self.canonical)
        self.assertIn('        - visionos_largest\n', self.canonical)
        self.assertNotEqual(self.canonical, self.workflow)

    def test_full_selected_command_bodies_unchanged_except_closed_binding(self):
        preflight, platform = route.job_parts(self.canonical)
        _, old, _ = route.split_platform(platform)
        _, new = route.job_parts(self.workflow)
        _, selected, _ = route.split_platform(new)
        self.assertEqual(tuple(route.step_name(x) for x in selected), route.SELECTED_STEPS)
        for step in old:
            name = route.step_name(step)
            if name not in route.SELECTED_STEPS or name in ('Capture original Mini job clock before checkout', 'Retain small phone and iPad evidence', 'Run native iPad mini workflows'):
                continue
            self.assertIn(step, selected, name)
        self.assertNotIn('Run large-phone UI regression', self.workflow)
        self.assertNotIn('Run native 13-inch iPad workflows', self.workflow)
        self.assertNotIn('Execute ephemeral ad-hoc App Sandbox UI gate', self.workflow)
        expected = preflight.replace('        test "$GITHUB_REF" = refs/heads/codex/apple-platforms\n',
            '        python3 scripts/diagnostic_mini_managed_route.py validate\n')
        self.assertEqual(route.job_parts(self.workflow)[0], expected)

    def test_initial_clock_stays_before_bounded_checkout(self):
        self.assertLess(self.workflow.index('Capture original Mini job clock'), self.workflow.index('Checkout Mini exact source'))
        for value in ("'checkout_main':60", "'prepare':120", "'build':480", "'mini':1920", "'checkout_post':60", "'overhead':30"):
            self.assertIn(value, self.workflow)
        self.assertIn("require(os.environ.get('GITHUB_WORKFLOW_REF')=='" + route.WORKFLOW_REF + "')", self.workflow)

    def test_mutated_canonical_rejected(self):
        with self.assertRaises(ValueError): route.render_workflow(self.canonical + '\n')

    def test_mutated_route_rejected(self):
        with self.assertRaises(ValueError): route.identity(self.env, self.canonical, self.workflow.replace('timeout-minutes: 32', 'timeout-minutes: 33'))

    def test_foreign_missing_or_malformed_identity_rejected(self):
        mutations = {'GITHUB_REPOSITORY': '100mango/ColorPicker', 'GITHUB_SHA': 'b' * 40,
            'GITHUB_WORKFLOW_SHA': 'b' * 40, 'GITHUB_REF': 'refs/heads/codex/apple-platforms',
            'GITHUB_WORKFLOW_REF': route.WORKFLOW_REF.replace('mini-managed-full-row.yml', 'apple-platforms.yml'),
            'GITHUB_EVENT_NAME': 'workflow_dispatch', 'DIAGNOSTIC_ONLY': 'false',
            'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64', 'GITHUB_JOB': 'other',
            'EVIDENCE_SCOPE': 'ipad_pro', 'GITHUB_RUN_ID': '0', 'GITHUB_RUN_ATTEMPT': '-1'}
        for key, value in mutations.items():
            with self.subTest(key=key):
                env = {**self.env, key: value}
                with self.assertRaises(ValueError): route.identity(env, self.canonical, self.workflow)
                env.pop(key)
                with self.assertRaises(ValueError): route.identity(env, self.canonical, self.workflow)

    def test_preflight_empty_scope_only(self):
        env = {**self.env, 'GITHUB_JOB': 'preflight', 'EVIDENCE_SCOPE': ''}
        self.assertEqual(route.identity(env, self.canonical, self.workflow)['job'], 'preflight')
        env['EVIDENCE_SCOPE'] = 'ipad_mini'
        with self.assertRaises(ValueError): route.identity(env, self.canonical, self.workflow)

    def test_generic_readback_never_runs_inside_platform_marker(self):
        with self.fixture(), patch.object(route, 'execute') as execute:
            with self.assertRaises(ValueError): route.source_readback(SHA)
            execute.assert_not_called()

    def test_prepared_real_marker_is_preserved_without_process(self):
        with self.fixture() as (root, marker), patch.object(route, 'execute') as execute:
            before = marker.read_bytes(); inode = marker.stat().st_ino
            record = route.prepared(SHA, TREE)
            self.assertEqual(marker.read_bytes(), before); self.assertEqual(marker.stat().st_ino, inode)
            self.assertEqual(record['tested_tree'], TREE); self.assertFalse(record['release_qualification'])
            self.assertEqual(record['source_readback_phase'], 'existing bounded Mini prepare HEAD/tree/diff commands')
            execute.assert_not_called()

    def test_prepared_without_real_marker_rejected(self):
        with self.fixture() as (root, marker), patch.object(route, 'execute') as execute:
            marker.unlink()
            with self.assertRaises((ValueError, OSError)): route.prepared(SHA, TREE)
            self.assertFalse((root / route.RECEIPT).exists()); execute.assert_not_called()

    def test_foreign_marker_rejected_without_process(self):
        for field, value in [('source', 'c' * 40), ('phase', 'host-build'), ('owner_pid', True), ('command', ['git', 'status'])]:
            with self.subTest(field=field), self.fixture() as (root, marker), patch.object(route, 'execute') as execute:
                data = json.loads(marker.read_text()); data[field] = value; marker.write_text(json.dumps(data))
                with self.assertRaises(ValueError): route.prepared(SHA, TREE)
                self.assertFalse((root / route.RECEIPT).exists()); execute.assert_not_called()

    def test_prepared_wrong_head_or_tree_rejected(self):
        with self.fixture(), patch.object(route, 'execute') as execute:
            for head, tree in [('c' * 40, TREE), (SHA, ''), (SHA, 'b' * 39)]:
                with self.assertRaises(ValueError): route.prepared(head, tree)
            execute.assert_not_called()

    def test_prepare_marker_mutation_is_not_silently_accepted(self):
        with self.fixture() as (root, marker):
            original = route.write_initial
            def mutate(*args):
                record = original(*args); marker.write_text('{}'); return record
            with patch.object(route, 'write_initial', side_effect=mutate):
                with self.assertRaises(ValueError): route.prepared(SHA, TREE)

    def test_sealed_retention_preserves_initial_source_and_never_spawns(self):
        with self.fixture() as (root, marker):
            route.prepared(SHA, TREE); (root / 'build/ios-platform-evidence').mkdir()
            before = marker.read_bytes()
            with patch.object(route, 'execute') as execute:
                record = route.retain_prepared(); execute.assert_not_called()
            self.assertEqual(marker.read_bytes(), before); self.assertEqual(record['tested_tree'], TREE)
            self.assertFalse(record['retention_verification']['fresh_source_readback_performed'])
            self.assertFalse(record['release_qualification'])

    def test_uncertainty_retention_is_explicit_initial_only(self):
        with self.fixture() as (root, marker):
            route.prepared(SHA, TREE); (root / 'build/ios-platform-evidence').mkdir()
            os.environ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED'] = 'true'
            with patch.object(route, 'execute') as execute:
                record = route.retain_prepared(); execute.assert_not_called()
            self.assertTrue(record['retention_verification']['device_barrier_observed'])
            self.assertFalse(record['release_qualification'])

    def test_missing_or_wrong_fingerprint_rejected(self):
        with self.fixture() as (root, marker):
            route.prepared(SHA, TREE); (root / 'build/ios-platform-evidence').mkdir()
            for value in ('', 'c' * 64):
                os.environ[route.INITIAL_HASH_KEY] = value
                with self.assertRaises(ValueError): route.retain_prepared()

    def test_wrong_run_cannot_reuse_prepared_receipt(self):
        with self.fixture() as (root, marker):
            route.prepared(SHA, TREE); (root / 'build/ios-platform-evidence').mkdir()
            os.environ['GITHUB_RUN_ID'] = '124'
            with self.assertRaises(ValueError): route.retain_prepared()

    def test_linked_evidence_parent_rejected(self):
        with self.fixture() as (root, marker):
            route.prepared(SHA, TREE); foreign = root / 'foreign'; foreign.mkdir()
            (root / 'build/ios-platform-evidence').symlink_to(foreign, target_is_directory=True)
            with self.assertRaises(ValueError): route.retain_prepared()
            self.assertEqual(list(foreign.iterdir()), [])

    def test_only_fixed_operations_permitted(self):
        for args in ([], ['retain'], ['prepared'], ['prepared', SHA, TREE, 'extra'], ['run', 'simctl']):
            with self.assertRaises(ValueError): route.main(args)

    def managed_prepare_fixture(self):
        # Reuse the existing component's actual controller/bounded Bash path and
        # explicitly named Apple/Git doubles, not another synthetic driver.
        sys.path.insert(0, str(ROOT / 'Tests/Harness'))
        module = importlib.import_module('test_ipad_mini_setup')
        owner = module.MiniSetupTests(methodName='test_actual_host_prepare_keeps_real_lease_without_redundant_unit_reruns')
        owner.setUp()
        try:
            env, log = owner.prepare_fixture()
        except BaseException:
            owner.tearDown()
            raise
        env.update(GITHUB_REF=route.REF, GITHUB_WORKFLOW_REF=route.WORKFLOW_REF,
                   GITHUB_JOB='platform', DIAGNOSTIC_ONLY='true', RUNNER_OS='macOS', RUNNER_ARCH='ARM64')
        value=json.loads(owner.f.origin.read_text());value['caps']={**owner.f.origin_value['caps'], 'mini':1920}
        owner.f.origin.write_text(json.dumps(value));owner.f.origin.chmod(0o600)
        return owner, env, log

    def test_actual_diagnostic_prepare_preserves_real_marker_and_original_commands(self):
        owner, env, log = self.managed_prepare_fixture()
        try:
            command = [sys.executable] + (['-O'] if not __debug__ else []) + [str(owner.f.root / 'scripts/ipad_mini_setup.py'), 'phase', 'prepare']
            result = subprocess.run(command, cwd=owner.f.root, env=env, capture_output=True, text=True,
                                    timeout=20, start_new_session=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('DIAGNOSTIC_MINI_MANAGED_PROVENANCE', result.stdout)
            self.assertNotIn('SHELL_ARGUMENT_ROUTING_PASS', result.stdout)
            self.assertFalse((owner.f.root / 'build/ipad-mini-host-inflight.json').exists())
            record = json.loads((owner.f.root / route.RECEIPT).read_text())
            self.assertEqual(record['ref'], route.REF); self.assertEqual(record['tested_tree'], TREE)
            self.assertFalse(record['release_qualification'])
            leases = [json.loads(line) for line in Path(str(log) + '.lease.jsonl').read_text().splitlines()]
            self.assertTrue(leases); self.assertEqual(len({item['sha256'] for item in leases}), 1)
            self.assertTrue(all(item['lease']['phase'] == 'host-prepare' for item in leases))
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertIn(['xcrun', ['swift', 'scripts/materialize_native_icons.swift']], calls)
            self.assertIn(['plutil', ['-lint', 'QRCatcherMac/Info.plist', 'QRCatcherVision/Info.plist', 'QRCatcher/Info.plist', 'QRCatcher/PrivacyInfo.xcprivacy']], calls)
            self.assertFalse(json.loads((owner.f.root / 'build/ipad-mini-job-state.json').read_text())['full_job_accepted'])
        finally:
            owner.tearDown()

    def test_actual_diagnostic_prepare_wrong_workflow_stops_before_commands(self):
        owner, env, log = self.managed_prepare_fixture()
        try:
            env['GITHUB_WORKFLOW_REF'] = route.WORKFLOW_REF.replace('mini-managed-full-row.yml', 'apple-platforms.yml')
            result = subprocess.run([sys.executable, str(owner.f.root / 'scripts/ipad_mini_setup.py'), 'phase', 'prepare'],
                                    cwd=owner.f.root, env=env, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0); self.assertFalse(log.exists())
            self.assertFalse((owner.f.root / route.RECEIPT).exists())
        finally:
            owner.tearDown()

    def diagnostic_row_fixture(self):
        sys.path.insert(0, str(ROOT / 'Tests/Harness'))
        module = importlib.import_module('test_ipad_mini_setup')
        owner = module.MiniSetupTests(methodName='test_actual_cli_full_row_module_alias_and_original_fixture_stager')
        owner.setUp()
        try:
            owner.install_source()
            os.environ.update(GITHUB_REF=route.REF, GITHUB_WORKFLOW_REF=route.WORKFLOW_REF,
                GITHUB_JOB='platform', DIAGNOSTIC_ONLY='true', RUNNER_OS='macOS', RUNNER_ARCH='ARM64')
            value=json.loads(owner.f.origin.read_text());value['caps']={**module.mini.CAPS,'mini':1920}
            owner.f.origin.write_text(json.dumps(value));owner.f.origin.chmod(0o600)
            owner.f.budget.path.unlink()
            owner.f.budget=module.mini.Budget(owner.f.clock)
            for phase in ('prepare','build'):
                owner.f.budget.enter(phase);owner.f.budget.state['phases'][phase]['status']='completed';owner.f.budget.persist()
            owner.f.configure()
        except BaseException:
            owner.tearDown();raise
        return owner,module

    def diagnostic_row_executor(self, owner, module, states):
        original=owner.f.executor
        def execute(command,cap,**kwargs):
            state_command=['xcrun','simctl','list','devices','available','-j']
            if command==state_command or command[:3] in (['xcrun','simctl','boot'],['xcrun','simctl','bootstatus']):
                owner.f.calls.append((command,cap));owner.f.clock.now+=.01
                if command==state_command:
                    self.assertTrue(states,'Unexpected repeated device-state query')
                    state=states.pop(0)
                    raw=json.dumps({'devices':{module.RUNTIME:[{'udid':module.DEVICE,'name':'QRCatcher Mini 123-1',
                        'deviceTypeIdentifier':module.TYPE,'isAvailable':True,'state':state}]}})
                elif command[:3]==['xcrun','simctl','bootstatus']:
                    from test_ipad_mini_state_handoff import bootstatus_output
                    raw=bootstatus_output('QRCatcher Mini 123-1',module.DEVICE)
                else:raw='Explicit state-handoff double; no simulator execution'
                return 0,raw,{'state':'completed','exit':0,'cleanup_confirmed':True,'elapsed_seconds':.01,'output_bytes':len(raw.encode())}
            return original(command,cap,**kwargs)
        return execute

    def test_full_diagnostic_row_booted_handoffs_preserve_all_four_cases_and_caps(self):
        owner,module=self.diagnostic_row_fixture()
        try:
            states=['Booted','Booted'];owner.f.executor=self.diagnostic_row_executor(owner,module,states)
            self.assertEqual(owner.f.row(),0);self.assertEqual(states,[])
            self.assertEqual(owner.f.setup()['unexecuted'],[])
            cases=[(command,cap) for command,cap in owner.f.calls if command[:2]==['xcodebuild','test-without-building']]
            self.assertEqual([cap for command,cap in cases],[480,240,360])
            self.assertEqual(len(cases),3);self.assertTrue(any('/testRealFilesImportAndReopen' in arg for arg in cases[1][0]))
            self.assertTrue(any('/testRealPhotoImportReplacesSelectionAndPreservesBothRecords' in arg for arg in cases[2][0]))
            self.assertEqual([cap for command,cap in owner.f.calls if command[:3]==['xcrun','simctl','addmedia']],[210])
            self.assertFalse(any(command[:3]==['xcrun','simctl','boot'] for command,cap in owner.f.calls))
            self.assertEqual(owner.f.budget.caps['mini'],1920);self.assertEqual(owner.f.budget.job_seconds,3000)
            self.assertEqual(module.mini.CAPS['mini'],1620);self.assertEqual(sum(module.mini.CAPS.values()),2700)
            self.assertFalse(owner.f.budget.state['full_job_accepted'])
        finally:owner.tearDown()

    def test_full_diagnostic_row_shutdown_recovers_once_at_both_handoffs(self):
        owner,module=self.diagnostic_row_fixture()
        try:
            states=['Shutdown','Shutdown'];owner.f.executor=self.diagnostic_row_executor(owner,module,states)
            self.assertEqual(owner.f.row(),0);self.assertEqual(states,[]);self.assertEqual(owner.f.setup()['unexecuted'],[])
            self.assertEqual([cap for command,cap in owner.f.calls if command[:3]==['xcrun','simctl','boot']],[30,30])
            self.assertEqual([cap for command,cap in owner.f.calls if command[:3]==['xcrun','simctl','bootstatus']],[90,90])
            handoffs=owner.f.budget.state['phases']['mini']['state_handoffs']
            self.assertEqual(set(handoffs),{'before_files_fixture','before_photos_seed'})
            self.assertEqual(len([command for command,cap in owner.f.calls if command==['xcrun','simctl','list','devices','available','-j']]),3)
            self.assertEqual([len(value['observations']) for value in handoffs.values()],[1,1])
            self.assertEqual([value['observations'][0]['state'] for value in handoffs.values()],['Shutdown','Shutdown'])
            self.assertTrue(all(value['boot_attempts']==1 and value['state']=='bootstatus_completion_observation_only' and
                                value['readiness_basis']=='exact_owned_uuid_bootstatus_completion' for value in handoffs.values()))
            self.assertTrue((owner.f.root/'build/ipad-mini-row-dispatched.json').exists())
        finally:owner.tearDown()

    def test_full_diagnostic_row_failed_files65_still_attempts_photos_after_two_shutdown_handoffs(self):
        owner,module=self.diagnostic_row_fixture()
        try:
            owner.f.file_exit=65;states=['Shutdown','Shutdown']
            owner.f.executor=self.diagnostic_row_executor(owner,module,states)
            self.assertEqual(owner.f.row(),65);self.assertEqual(states,[])
            setup=owner.f.setup();self.assertEqual(setup['unexecuted'],[])
            self.assertEqual(setup['real_files_case_exit'],65);self.assertEqual(setup['real_photo_case_exit'],0)
            cases=[(command,cap) for command,cap in owner.f.calls if command[:2]==['xcodebuild','test-without-building']]
            self.assertEqual([cap for command,cap in cases],[480,240,360]);self.assertEqual(len(cases),3)
            self.assertTrue(any('/testRealFilesImportAndReopen' in arg for arg in cases[1][0]))
            self.assertTrue(any('/testRealPhotoImportReplacesSelectionAndPreservesBothRecords' in arg for arg in cases[2][0]))
            self.assertEqual([cap for command,cap in owner.f.calls if command[:3]==['xcrun','simctl','addmedia']],[210])
            handoffs=owner.f.budget.state['phases']['mini']['state_handoffs']
            self.assertEqual([value['observations'][0]['state'] for value in handoffs.values()],['Shutdown','Shutdown'])
            self.assertEqual([value['boot_attempts'] for value in handoffs.values()],[1,1])
            self.assertEqual([value['state'] for value in handoffs.values()],['bootstatus_completion_observation_only']*2)
            self.assertFalse(owner.f.budget.state['full_job_accepted'])
        finally:owner.tearDown()

    def test_full_diagnostic_row_unknown_state_stops_before_files_and_photos(self):
        owner,module=self.diagnostic_row_fixture()
        try:
            owner.f.executor=self.diagnostic_row_executor(owner,module,['Booting'])
            with self.assertRaises(ValueError):owner.f.row()
            self.assertEqual(owner.f.setup()['unexecuted'],['files','photos'])
            self.assertFalse(any(command[:3] in (['xcrun','simctl','boot'],['xcrun','simctl','addmedia']) for command,cap in owner.f.calls))
            self.assertEqual(len([command for command,cap in owner.f.calls if command[:2]==['xcodebuild','test-without-building']]),1)
        finally:owner.tearDown()


if __name__ == '__main__':
    unittest.main()
