"""Portable fail-closed fixtures, never native runtime or release proof."""
import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import diagnostic_phone_smoke_route as route
import ios_import_continuation as continuation
from ios_import_continuation import identity as pro_identity


class DiagnosticPhoneSmokeRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = (ROOT / route.CANONICAL).read_text()
        cls.workflow = (ROOT / route.WORKFLOW).read_text()

    def environment(self, job='platform', scope='iphone_pro'):
        return {'GITHUB_SHA': 'a' * 40, 'GITHUB_WORKFLOW_SHA': 'a' * 40,
                'GITHUB_REPOSITORY': route.REPOSITORY,
                'GITHUB_REF': route.REF, 'GITHUB_WORKFLOW_REF': route.WORKFLOW_REF,
                'GITHUB_EVENT_NAME': 'push', 'DIAGNOSTIC_ONLY': 'true',
                'RUNNER_OS': 'macOS', 'RUNNER_ARCH': 'ARM64', 'GITHUB_JOB': job,
                'EVIDENCE_SCOPE': scope, 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}

    def test_good_exact_source_scopes_and_preflight(self):
        for job, scope in [('preflight', ''), ('platform', 'iphone_pro'), ('platform', 'iphone_se3')]:
            record = route.identity(self.environment(job, scope), self.canonical, self.workflow)
            self.assertIs(record['diagnostic_only'], True)
            self.assertIs(record['release_qualification'], False)
            self.assertEqual(record['selected_scopes'], ['iphone_pro', 'iphone_se3'])
            self.assertLess(len(json.dumps(record, indent=2).encode()), 4096)

    def test_wrong_repository_ref_workflow_and_source_sha_rejected(self):
        mutations = [('GITHUB_REPOSITORY', 'somebody/QRCatcher'),
                     ('GITHUB_REF', 'refs/heads/codex/apple-platforms'),
                     ('GITHUB_REF', 'refs/heads/main'),
                     ('GITHUB_REF', route.REF + '-other'),
                     ('GITHUB_WORKFLOW_REF', route.REPOSITORY + '/' + route.CANONICAL + '@' + route.REF),
                     ('GITHUB_WORKFLOW_REF', route.WORKFLOW_REF.replace(route.REF, 'refs/heads/main')),
                     ('GITHUB_SHA', 'A' * 40), ('GITHUB_SHA', 'a' * 40 + '\n'),
                     ('GITHUB_SHA', 'a' * 39), ('GITHUB_WORKFLOW_SHA', 'b' * 40),
                     ('GITHUB_EVENT_NAME', 'workflow_dispatch')]
        for key, value in mutations:
            env = self.environment(); env[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                route.identity(env, self.canonical, self.workflow)

    def test_wrong_diagnostic_mode_and_missing_values_rejected(self):
        for value in ['', 'false', 'True', '1', True, None]:
            env = self.environment(); env['DIAGNOSTIC_ONLY'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                route.identity(env, self.canonical, self.workflow)
        for key in self.environment():
            env = self.environment(); del env[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                route.identity(env, self.canonical, self.workflow)

    def test_wrong_runners_scopes_jobs_and_run_ids_rejected(self):
        mutations = [('RUNNER_OS', 'Linux'), ('RUNNER_OS', 'Windows'),
                     ('RUNNER_ARCH', 'X64'), ('GITHUB_JOB', 'other'),
                     ('EVIDENCE_SCOPE', 'macos'), ('EVIDENCE_SCOPE', 'watchos_40'),
                     ('EVIDENCE_SCOPE', 'watchos_49'),
                     ('EVIDENCE_SCOPE', 'watchos'), ('EVIDENCE_SCOPE', 'ipad_pro'),
                     ('EVIDENCE_SCOPE', 'iphone_pro,iphone_se3'), ('EVIDENCE_SCOPE', ''),
                     ('GITHUB_RUN_ID', '0'), ('GITHUB_RUN_ID', '-1'),
                     ('GITHUB_RUN_ATTEMPT', '1\n')]
        for key, value in mutations:
            env = self.environment(); env[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                route.identity(env, self.canonical, self.workflow)
        with self.assertRaises(ValueError):
            route.identity(self.environment('preflight', 'iphone_pro'), self.canonical, self.workflow)

    def test_wrong_workflow_permissions_runners_scopes_parallelism_and_mode_rejected(self):
        mutations = [('contents: read', 'contents: write'),
                     ('  contents: read\n', '  contents: read\n  actions: write\n'),
                     ('runs-on: xcode-27', 'runs-on: macos-latest'),
                     ('runs-on: xcode-27', 'runs-on: xcode-27-large'),
                     ('runs-on: xcode-27', 'runs-on: self-hosted'),
                     ('max-parallel: 2', 'max-parallel: 3'),
                     ('max-parallel: 2', 'max-parallel: 1'),
                     ('cancel-in-progress: false', 'cancel-in-progress: true'),
                     ('        - iphone_se3\n', '        - macos\n'),
                     ('        - iphone_se3\n', '        - iphone_se3\n        - watchos_40\n'),
                     ('        - iphone_se3\n', '        - iphone_se3\n        - watchos_49\n'),
                     ('        - iphone_pro\n', ''),
                     ("DIAGNOSTIC_ONLY: 'true'", "DIAGNOSTIC_ONLY: 'false'"),
                     ('timeout-minutes: 45', 'timeout-minutes: 46'),
                     ('timeout-minutes: 20', 'timeout-minutes: 21'),
                     ('run_bounded.py 855', 'run_bounded.py 955'),
                     ('retention-days: 1', 'retention-days: 2'),
                     ('  push:', '  workflow_dispatch:'),
                     ('    - ' + route.BRANCH + '\n', '    - main\n'),
                     ('group: qrcatcher-apple-platforms', 'group: independent-smoke'),
                     ('persist-credentials: false', 'persist-credentials: true'),
                     ("&& steps.phone_diagnostic_identity.outcome == 'success'", '')]
        for old, new in mutations:
            self.assertIn(old, self.workflow)
            with self.subTest(old=old, new=new), self.assertRaises(ValueError):
                route.verify_workflow(self.canonical, self.workflow.replace(old, new))

    def test_canonical_bytes_are_immutable(self):
        self.assertEqual(hashlib.sha256(self.canonical.encode()).hexdigest(), route.CANONICAL_SHA256)
        with self.assertRaises(ValueError):
            route.verify_workflow(self.canonical + '\n', self.workflow)
        with self.assertRaises(ValueError):
            route.verify_workflow(self.canonical.replace('\n', '\r\n'), self.workflow)
        with self.assertRaises(ValueError):
            route.verify_workflow(self.canonical, self.workflow.replace('\n', '\r\n'))

    def test_every_selected_command_body_and_cap_preserved(self):
        _, canonical_platform = route.job_parts(self.canonical)
        _, canonical_steps, _ = route.split_platform(canonical_platform)
        _, smoke_platform = route.job_parts(self.workflow)
        _, smoke_steps, _ = route.split_platform(smoke_platform)
        originals = {route.step_name(step): step for step in canonical_steps}
        selected = {route.step_name(step): step for step in smoke_steps}
        for name in route.SELECTED_STEPS:
            old, new = originals[name], selected[name]
            if name == 'Verify exact source and stable toolchain':
                old = old.replace('        test "$GITHUB_REF" = refs/heads/codex/apple-platforms\n',
                                  '        python3 scripts/diagnostic_phone_smoke_route.py validate\n')
            if name.startswith('Retain small'):
                old = old.replace('name: qrcatcher-${{ matrix.scope }}-evidence',
                                  'name: qrcatcher-diagnostic-phone47-${{ matrix.scope }}-evidence')
                old = old.replace("always() && steps.platform_evidence_budget.outcome == 'success'",
                                  "always() && steps.platform_evidence_budget.outcome == 'success' && "
                                  "steps.phone_diagnostic_identity.outcome == 'success'")
            with self.subTest(name=name):
                self.assertEqual(old, new)
        self.assertEqual(originals['checkout'], selected['checkout'])
        old_preflight = route.job_parts(self.canonical)[0]
        new_preflight = route.job_parts(self.workflow)[0]
        self.assertEqual(old_preflight.replace('        test "$GITHUB_REF" = refs/heads/codex/apple-platforms\n',
                                             '        python3 scripts/diagnostic_phone_smoke_route.py validate\n'), new_preflight)

    def test_no_pro_continuation_branch_identity_bypass(self):
        device = '11111111-1111-4111-8111-111111111111'
        env = self.environment(); env.update(EVIDENCE_SCOPE='iphone_pro', SIMULATOR_ID=device)
        with patch.dict(os.environ, env, clear=True), self.assertRaises((ValueError, FileNotFoundError)):
            pro_identity(device, 'PhoneUIResults.xcresult')
        env['GITHUB_REF'] = 'refs/heads/codex/apple-platforms'
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(pro_identity(device, 'PhoneUIResults.xcresult'), 'a' * 40)
        self.assertNotIn('GITHUB_REF=', self.workflow)

    def execute_in_checkout(self, mode, scope='iphone_pro', mutate=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.github/workflows').mkdir(parents=True)
            (root / route.CANONICAL).write_text(self.canonical)
            (root / route.WORKFLOW).write_text(self.workflow)
            folder = root / 'build/ios-platform-evidence'
            if mode == 'retain': folder.mkdir(parents=True)
            old = Path.cwd()
            try:
                os.chdir(root)
                env = self.environment(scope=scope)
                env['GITHUB_ENV'] = str(root / 'runner-environment.txt')
                with patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()), patch.object(route, 'source_readback', return_value='b' * 40) as readback:
                    if mode == 'retain': route.main(['validate'])
                    if mutate: mutate(root, folder)
                    route.main([mode])
                    self.assertEqual(readback.call_count, 1)
                target = folder / route.RECEIPT.name if mode == 'retain' else root / route.RECEIPT
                return json.loads(target.read_text()), target.stat().st_size
            finally:
                os.chdir(old)

    def test_first_validate_creates_bounded_receipt_parent(self):
        value, size = self.execute_in_checkout('validate')
        self.assertIs(value['diagnostic_only'], True)
        self.assertEqual(value['tested_tree'], 'b' * 40)
        self.assertLessEqual(size, 4096)

    def test_both_existing_evidence_folders_receive_bounded_receipt(self):
        for scope in route.SCOPES:
            value, size = self.execute_in_checkout('retain', scope)
            self.assertEqual(value['scope'], scope)
            self.assertLessEqual(size, 4096)

    def test_unknown_mode_missing_folder_and_symlink_destinations_fail_closed(self):
        with self.assertRaises(ValueError): route.main(['run'])
        def remove_folder(root, folder): folder.rmdir()
        with self.assertRaises(ValueError): self.execute_in_checkout('retain', mutate=remove_folder)
        def receipt_symlink(root, folder):
            (root / 'other.json').write_text('{}')
            (folder / route.RECEIPT.name).symlink_to(root / 'other.json')
        with self.assertRaises(ValueError): self.execute_in_checkout('retain', mutate=receipt_symlink)
        def workflow_symlink(root, folder):
            value = (root / route.WORKFLOW).read_text()
            (root / route.WORKFLOW).unlink()
            (root / 'other.yml').write_text(value)
            (root / route.WORKFLOW).symlink_to(root / 'other.yml')
        with self.assertRaises(ValueError): self.execute_in_checkout('validate', mutate=workflow_symlink)
        def canonical_crlf(root, folder):
            (root / route.CANONICAL).write_bytes(self.canonical.replace('\n', '\r\n').encode())
        with self.assertRaises(ValueError): self.execute_in_checkout('validate', mutate=canonical_crlf)

    def test_missing_tampered_swapped_and_source_mismatched_initial_receipts_fail_closed(self):
        def missing(root, folder): (root / route.RECEIPT).unlink()
        def tampered(root, folder):
            initial = json.loads((root / route.RECEIPT).read_text())
            initial['tested_tree'] = 'c' * 40
            (root / route.RECEIPT).write_text(json.dumps(initial))
        def swapped(root, folder):
            original = root / route.RECEIPT
            original.rename(original.with_suffix('.saved.json'))
            original.write_text('{}')
        def source_mismatch(root, folder):
            initial = json.loads((root / route.RECEIPT).read_text())
            initial['source_sha'] = 'c' * 40
            data = json.dumps(initial).encode()
            (root / route.RECEIPT).write_bytes(data)
            os.environ[route.INITIAL_HASH_KEY] = hashlib.sha256(data).hexdigest()
        def missing_hash(root, folder): os.environ.pop(route.INITIAL_HASH_KEY)
        def symlink(root, folder):
            original = root / route.RECEIPT
            replacement = original.with_suffix('.saved.json')
            original.rename(replacement)
            original.symlink_to(replacement)
        def hardlink(root, folder):
            os.link(root / route.RECEIPT, root / 'receipt-hardlink.json')
        for mutation in [missing, tampered, swapped, source_mismatch, missing_hash, symlink, hardlink]:
            with self.subTest(mutation=mutation.__name__), self.assertRaises((ValueError, FileNotFoundError)):
                self.execute_in_checkout('retain', mutate=mutation)
        for field, wrong in [('source_sha', 'c' * 40), ('workflow_sha', 'c' * 40),
                             ('ref', 'refs/heads/main'), ('workflow_ref', route.WORKFLOW_REF + '-other'),
                             ('run_id', '456'), ('run_attempt', '2'), ('job', 'preflight'),
                             ('scope', 'iphone_se3'), ('canonical_workflow_sha256', 'c' * 64),
                             ('workflow_sha256', 'c' * 64), ('diagnostic_only', 1),
                             ('source_readback_phase', 'after runtime')]:
            def changed_identity(root, folder, field=field, wrong=wrong):
                initial = json.loads((root / route.RECEIPT).read_text())
                initial[field] = wrong
                data = json.dumps(initial).encode()
                (root / route.RECEIPT).write_bytes(data)
                os.environ[route.INITIAL_HASH_KEY] = hashlib.sha256(data).hexdigest()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.execute_in_checkout('retain', mutate=changed_identity)

    def test_executable_barrier_true_retain_preserves_bounded_failure_evidence_without_execute(self):
        for scope in route.SCOPES:
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / '.github/workflows').mkdir(parents=True)
                (root / route.CANONICAL).write_text(self.canonical)
                (root / route.WORKFLOW).write_text(self.workflow)
                folder = root / 'build/ios-platform-evidence'
                folder.mkdir(parents=True)
                env = self.environment(scope=scope)
                initial = route.identity(env, self.canonical, self.workflow)
                initial.update(tested_tree='b' * 40, source_readback_phase='before build or device/runtime work')
                data = (json.dumps(initial, indent=2) + '\n').encode()
                (root / route.RECEIPT).write_bytes(data)
                env.update({route.INITIAL_HASH_KEY: hashlib.sha256(data).hexdigest(),
                            'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED': 'true', 'GITHUB_WORKSPACE': str(root)})
                program = ("import sys\nfrom pathlib import Path\nsys.path.insert(0," + repr(str(ROOT / 'scripts')) + ")\n"
                           "import diagnostic_phone_smoke_route as route\n"
                           "def forbidden(*args, **kwargs):\n"
                           " Path('unexpected-execute.txt').write_text('called')\n"
                           " raise RuntimeError('retention must never execute')\n"
                           "route.execute=forbidden\nroute.source_readback=forbidden\n"
                           "raise SystemExit(route.main(['retain']))\n")
                result = subprocess.run([sys.executable, '-c', program], cwd=root,
                                        env={**os.environ, **env}, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((root / 'unexpected-execute.txt').exists())
                retained = folder / route.RECEIPT.name
                self.assertLessEqual(retained.stat().st_size, 4096)
                value = json.loads(retained.read_text())
                self.assertIs(value['diagnostic_only'], True)
                self.assertIs(value['release_qualification'], False)
                self.assertEqual(value['tested_tree'], 'b' * 40)
                self.assertIs(value['retention_verification']['owned_cleanup_uncertainty_observed'], True)
                self.assertIs(value['retention_verification']['fresh_source_readback_performed'], False)

    def test_workflow_has_exact_closed_two_slot_bounds(self):
        self.assertEqual(self.workflow.count('    runs-on: xcode-27\n'), 2)
        self.assertIn('    needs: preflight\n', self.workflow)
        self.assertIn('      max-parallel: 2\n', self.workflow)
        self.assertNotIn('actions/cache', self.workflow)
        self.assertNotIn('actions/download-artifact', self.workflow)
        self.assertNotIn('continue-on-error', self.workflow)
        self.assertIn('python3 -u scripts/compile_platform_preflight.py', self.workflow)
        self.assertIn('        - iphone_pro\n        - iphone_se3\n', self.workflow)
        self.assertEqual(self.workflow.count('retention-days: 1'), 1)

    def test_source_readback_preserves_exact_head_tree_cleanliness_and_cleanup_bounds(self):
        calls = []
        def good(command, seconds, **options):
            calls.append(command)
            self.assertEqual(seconds, 5)
            self.assertEqual(options['output_limit'], 4096)
            self.assertEqual(options['tail_limit'], 4096)
            output = 'a' * 40 if command[-1] == 'HEAD' else 'b' * 40 if command[-1] == 'HEAD^{tree}' else ''
            return 0, output, {'state': 'completed', 'cleanup_confirmed': True}
        with patch.object(route, 'execute', side_effect=good):
            self.assertEqual(route.source_readback('a' * 40), 'b' * 40)
        self.assertEqual(calls, [['git', 'rev-parse', 'HEAD'], ['git', 'rev-parse', 'HEAD^{tree}'],
                                 ['git', 'diff', '--exit-code', 'HEAD', '--'],
                                 ['git', 'status', '--porcelain=v1', '--untracked-files=all']])
        mutations = [
            (0, 'c' * 40, {'state': 'completed', 'cleanup_confirmed': True}),
            (65, '', {'state': 'completed', 'cleanup_confirmed': True}),
            (124, '', {'state': 'timed_out', 'cleanup_confirmed': True}),
            (0, 'a' * 40, {'state': 'completed', 'cleanup_confirmed': False}),
            (0, 'a' * 40, {'state': 'completed'}),
        ]
        for response in mutations:
            with self.subTest(response=response), patch.object(route, 'execute', return_value=response), self.assertRaises(ValueError):
                route.source_readback('a' * 40)
        clean = (0, 'a' * 40, {'state': 'completed', 'cleanup_confirmed': True})
        tree = (0, 'b' * 40, {'state': 'completed', 'cleanup_confirmed': True})
        for response in [(0, 'invalid tree', clean[2]), (65, 'dirty source', clean[2])]:
            responses = [clean, response] if response[0] == 0 else [clean, tree, response]
            with patch.object(route, 'execute', side_effect=responses), self.assertRaises(ValueError):
                route.source_readback('a' * 40)

    @contextlib.contextmanager
    def sealed_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / '.github/workflows').mkdir(parents=True)
            (root / route.CANONICAL).write_text(self.canonical)
            (root / route.WORKFLOW).write_text(self.workflow)
            old = Path.cwd()
            try:
                os.chdir(root)
                env = self.environment()
                env.update(SIMULATOR_ID='11111111-1111-4111-8111-111111111111',
                           GITHUB_ENV=str(root / 'runner-environment.txt'), GITHUB_WORKSPACE=str(root))
                with patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()):
                    with patch.object(route, 'source_readback', return_value='b' * 40):
                        route.main(['validate'])
                    yield root, env
            finally:
                os.chdir(old)

    def test_exact_sealed_diagnostic_continuation_is_pure_and_retains_source_identity(self):
        with self.sealed_checkout(), patch.object(route, 'execute') as execute, \
                patch.object(route, 'source_readback') as readback:
            before = dict(os.environ)
            self.assertEqual(pro_identity(os.environ['SIMULATOR_ID'], continuation.RESULT), 'a' * 40)
            self.assertEqual(dict(os.environ), before)
            execute.assert_not_called(); readback.assert_not_called()

    def test_canonical_continuation_does_not_depend_on_diagnostic_verifier(self):
        env = self.environment()
        device = '11111111-1111-4111-8111-111111111111'
        env.update(GITHUB_REF='refs/heads/codex/apple-platforms', SIMULATOR_ID=device)
        with patch.dict(os.environ, env, clear=True), \
                patch.object(route, 'verify_continuation_context', side_effect=RuntimeError('must not call')):
            self.assertEqual(pro_identity(device, continuation.RESULT), 'a' * 40)

    def test_continuation_uuid_result_scope_device_and_unrelated_route_rejected(self):
        with self.sealed_checkout(), patch.object(route, 'execute') as execute:
            device = os.environ['SIMULATOR_ID']
            for wrong in ['bad', device.lower(), '11111111-1111-4111-8111-111111111112']:
                # Numeric-only UUID's lowercase form is unchanged.
                if wrong == device: continue
                with self.subTest(device=wrong), self.assertRaises(ValueError):
                    pro_identity(wrong, continuation.RESULT)
            for wrong in ['CompactPhoneUIResults.xcresult', 'PhoneUIResults-other.xcresult']:
                with self.subTest(result=wrong), self.assertRaises(ValueError): pro_identity(device, wrong)
            for key, value in [('EVIDENCE_SCOPE', 'iphone_se3'), ('SIMULATOR_ID', 'wrong'),
                               ('GITHUB_REF', 'refs/heads/codex/apple-platforms-diagnostic-smoke47'),
                               ('GITHUB_REF', route.REF + '-other')]:
                with self.subTest(key=key), patch.dict(os.environ, {key: value}), self.assertRaises(ValueError):
                    pro_identity(device, continuation.RESULT)
            execute.assert_not_called()

    def test_continuation_rejects_missing_tampered_oversized_or_resealed_wrong_identity_receipt(self):
        def missing(root): (root / route.RECEIPT).unlink()
        def tampered(root): (root / route.RECEIPT).write_text('{}')
        def oversized(root):
            data = b' ' * 4097; (root / route.RECEIPT).write_bytes(data)
            os.environ[route.INITIAL_HASH_KEY] = route.sha256(data)
        def resealed(root):
            value = json.loads((root / route.RECEIPT).read_text()); value['scope'] = 'iphone_se3'
            data = json.dumps(value).encode(); (root / route.RECEIPT).write_bytes(data)
            os.environ[route.INITIAL_HASH_KEY] = route.sha256(data)
        for mutation in [missing, tampered, oversized, resealed]:
            with self.subTest(mutation=mutation.__name__), self.sealed_checkout() as (root, _), \
                    patch.object(route, 'execute') as execute, self.assertRaises((ValueError, FileNotFoundError)):
                mutation(root); pro_identity(os.environ['SIMULATOR_ID'], continuation.RESULT)
            execute.assert_not_called()

    def test_barrier_stops_continuation_and_initial_readback_before_any_process_call(self):
        with self.sealed_checkout(), patch.dict(os.environ, {'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED': 'true'}), \
                patch.object(route, 'execute') as execute:
            with self.assertRaises(ValueError): pro_identity(os.environ['SIMULATOR_ID'], continuation.RESULT)
            with self.assertRaises(ValueError): route.source_readback('a' * 40)
            execute.assert_not_called()
        with patch.object(route, 'blocked', side_effect=[False, True]), \
                patch.object(route, 'execute', return_value=(0, 'a' * 40,
                             {'state': 'completed', 'cleanup_confirmed': True})) as execute:
            with self.assertRaises(ValueError): route.source_readback('a' * 40)
            self.assertEqual(execute.call_count, 1)

    def test_dirty_untracked_initial_checkout_is_not_clean_source_proof(self):
        responses = [(0, value, {'state': 'completed', 'cleanup_confirmed': True})
                     for value in ['a' * 40, 'b' * 40, '', '?? untracked-script.py']]
        with patch.object(route, 'blocked', return_value=False), \
                patch.object(route, 'execute', side_effect=responses), self.assertRaises(ValueError):
            route.source_readback('a' * 40)

    def test_executable_context_adversaries_never_call_processes(self):
        mutations = [('repository', 'GITHUB_REPOSITORY', 'other/QRCatcher'),
                     ('ref', 'GITHUB_REF', route.REF + '-other'),
                     ('workflow', 'GITHUB_WORKFLOW_REF', route.WORKFLOW_REF + '-other'),
                     ('sha', 'GITHUB_WORKFLOW_SHA', 'c' * 40),
                     ('event', 'GITHUB_EVENT_NAME', 'workflow_dispatch'),
                     ('tamper', None, None), ('missing', None, None), ('uncertain', None, None)]
        for label, key, value in mutations:
            with self.subTest(label=label), self.sealed_checkout() as (root, _):
                env = dict(os.environ)
                if key: env[key] = value
                if label == 'tamper': (root / route.RECEIPT).write_text('{}')
                if label == 'missing': (root / route.RECEIPT).unlink()
                if label == 'uncertain':
                    # Exercise the durable file barrier, independently of the
                    # propagated workflow environment flag.
                    (root / 'build/owned-process-cleanup.json').write_text('{"blocked":true}')
                    env['QRCATCHER_OWNED_PROCESS_BARRIER'] = str(root / 'build/owned-process-cleanup.json')
                program = ("import sys\nfrom pathlib import Path\nsys.path.insert(0," + repr(str(ROOT / 'scripts')) + ")\n"
                           "import diagnostic_phone_smoke_route as route\n"
                           "import ios_import_continuation as gate\n"
                           "def forbidden(*args, **kwargs):\n"
                           " Path('unexpected-execute.txt').write_text('called')\n"
                           " raise RuntimeError('must not execute')\n"
                           "route.execute=forbidden\nroute.source_readback=forbidden\ngate.execute=forbidden\n"
                           "try:\n gate.identity('11111111-1111-4111-8111-111111111111',gate.RESULT)\n"
                           "except (ValueError,FileNotFoundError):\n raise SystemExit(0)\n"
                           "raise SystemExit(1)\n")
                result = subprocess.run([sys.executable, '-c', program], cwd=root, env=env,
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((root / 'unexpected-execute.txt').exists())

    def test_complete_nine_case_camera_failure_contract_remains_exact(self):
        device = '11111111-1111-4111-8111-111111111111'
        operation = {'command': continuation.expected_command(device), 'timeout_seconds': 570,
                     'state': 'completed', 'exit': 65, 'cleanup_confirmed': True, 'elapsed_seconds': 511.68}
        summary = {'result': 'Failed', 'totalTestCount': 9, 'passedTests': 8, 'failedTests': 1,
                   'skippedTests': 0, 'expectedFailures': 0, 'startTime': 9500, 'finishTime': 9999,
                   'testFailures': [{'targetName': 'QRCatcherUITests',
                                     'testIdentifierString': 'QRCatcherUITests/testProductionCameraAllowThenResetAndDeny',
                                     'failureText': continuation.CAMERA_TIMEOUT}],
                   'devicesAndConfigurations': [{'device': {'deviceId': device, 'platform': 'iOS Simulator'}}]}
        continuation.validate_finalization(operation, summary, device, 10000)
        for mutation in [{'totalTestCount': 8}, {'passedTests': 9}, {'failedTests': 0}, {'skippedTests': 1},
                         {'expectedFailures': 1}, {'testFailures': []}, {'result': 'Passed'}]:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                continuation.validate_finalization(operation, {**summary, **mutation}, device, 10000)
        self.assertEqual(operation['exit'], 65)
        self.assertEqual(operation['timeout_seconds'], 570)

    def test_executable_diagnostic_shell_preserves_red_continuation_and_device_fencing(self):
        from test_ios_import_continuation import ContinuationShellTests
        fixture = ContinuationShellTests('test_completed_original_failure_remains_red_after_fresh_distinct_imports')
        run = subprocess.run
        def with_exact_diagnostic(command, *args, **options):
            if command[:2] == ['bash', 'scripts/run_ios_platform_ui.sh']:
                root = Path(options['cwd'])
                (root / 'scripts/diagnostic_phone_smoke_route.py').write_bytes(
                    (ROOT / 'scripts/diagnostic_phone_smoke_route.py').read_bytes())
                (root / '.github/workflows').mkdir(parents=True)
                (root / route.CANONICAL).write_text(self.canonical)
                (root / route.WORKFLOW).write_text(self.workflow)
                env = options['env']
                env.update(self.environment())
                initial = route.identity(env, self.canonical, self.workflow)
                initial.update(tested_tree='b' * 40, source_readback_phase='before build or device/runtime work')
                data = (json.dumps(initial, indent=2) + '\n').encode()
                (root / route.RECEIPT).parent.mkdir(exist_ok=True)
                (root / route.RECEIPT).write_bytes(data)
                env[route.INITIAL_HASH_KEY] = route.sha256(data)
            return run(command, *args, **options)
        for mode, status, count in [('normal', 65, 3), ('partial-summary', 65, 1),
                                    ('wrong-head', 65, 1), ('files-barrier', 126, 2)]:
            with self.subTest(mode=mode), patch.object(subprocess, 'run', side_effect=with_exact_diagnostic):
                result, setup, calls = fixture.run_shell(mode)
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                commands = [args for name, args in calls if name == 'xcodebuild']
                self.assertEqual(len(commands), count)
                self.assertEqual(setup['layout_and_real_picker_cancel_exit'], 65)
                if mode == 'normal':
                    self.assertEqual(setup['real_files_case_exit'], 0)
                    self.assertEqual(setup['real_photo_case_exit'], 0)
                    self.assertEqual(setup['independent_import_continuation']['ordinary_tests'],
                                     {'passed': 8, 'failed': 1, 'total': 9})
                if mode == 'files-barrier':
                    self.assertFalse(any('addmedia' in args for _, args in calls))


if __name__ == '__main__':
    unittest.main()
