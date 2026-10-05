"""Portable fail-closed fixtures, never native runtime or release proof."""
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
import diagnostic_mac_smoke_route as route
from ios_import_continuation import identity as pro_identity


class DiagnosticMacSmokeRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = (ROOT / route.CANONICAL).read_text()
        cls.workflow = (ROOT / route.WORKFLOW).read_text()

    def environment(self, job='platform', scope='macos'):
        return {'GITHUB_SHA': 'a' * 40, 'GITHUB_WORKFLOW_SHA': 'a' * 40,
                'GITHUB_REPOSITORY': route.REPOSITORY,
                'GITHUB_REF': route.REF, 'GITHUB_WORKFLOW_REF': route.WORKFLOW_REF,
                'GITHUB_EVENT_NAME': 'push', 'DIAGNOSTIC_ONLY': 'true',
                'RUNNER_OS': 'macOS', 'RUNNER_ARCH': 'ARM64', 'GITHUB_JOB': job,
                'EVIDENCE_SCOPE': scope, 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}

    def test_good_exact_source_scopes_and_preflight(self):
        for job, scope in [('preflight', ''), ('platform', 'macos')]:
            record = route.identity(self.environment(job, scope), self.canonical, self.workflow)
            self.assertIs(record['diagnostic_only'], True)
            self.assertIs(record['release_qualification'], False)
            self.assertEqual(record['selected_scopes'], ['macos'])
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
                     ('EVIDENCE_SCOPE', 'iphone_se3'), ('EVIDENCE_SCOPE', 'watchos'), ('EVIDENCE_SCOPE', 'watchos_40'),
                     ('EVIDENCE_SCOPE', 'watchos_49'),
                     ('EVIDENCE_SCOPE', 'iphone_pro'), ('EVIDENCE_SCOPE', 'ipad_pro'),
                     ('EVIDENCE_SCOPE', 'macos,watchos'), ('EVIDENCE_SCOPE', ''),
                     ('GITHUB_RUN_ID', '0'), ('GITHUB_RUN_ID', '-1'),
                     ('GITHUB_RUN_ATTEMPT', '1\n')]
        for key, value in mutations:
            env = self.environment(); env[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                route.identity(env, self.canonical, self.workflow)
        with self.assertRaises(ValueError):
            route.identity(self.environment('preflight', 'macos'), self.canonical, self.workflow)

    def test_wrong_workflow_permissions_runners_scopes_parallelism_and_mode_rejected(self):
        mutations = [('contents: read', 'contents: write'),
                     ('  contents: read\n', '  contents: read\n  actions: write\n'),
                     ('runs-on: xcode-27', 'runs-on: macos-latest'),
                     ('runs-on: xcode-27', 'runs-on: xcode-27-large'),
                     ('runs-on: xcode-27', 'runs-on: self-hosted'),
                     ('max-parallel: 1', 'max-parallel: 3'),
                     ('max-parallel: 1', 'max-parallel: 2'),
                     ('cancel-in-progress: false', 'cancel-in-progress: true'),
                     ('        - macos\n', '        - iphone_se3\n'),
                     ('        - macos\n', '        - macos\n        - watchos\n'),
                     ('        - macos\n', '        - macos\n        - watchos_40\n'),
                     ('        - macos\n', '        - macos\n        - watchos_49\n'),
                     ('        - macos\n', ''),
                     ("DIAGNOSTIC_ONLY: 'true'", "DIAGNOSTIC_ONLY: 'false'"),
                     ('timeout-minutes: 45', 'timeout-minutes: 46'),
                     ('timeout-minutes: 20', 'timeout-minutes: 21'),
                     ('run_bounded.py 1155', 'run_bounded.py 1255'),
                     ('retention-days: 1', 'retention-days: 2'),
                     ('  push:', '  workflow_dispatch:'),
                     ('    - ' + route.BRANCH + '\n', '    - main\n'),
                     ('group: qrcatcher-apple-platforms', 'group: independent-smoke'),
                     ('persist-credentials: false', 'persist-credentials: true'),
                     ("&& steps.mac_diagnostic_identity.outcome == 'success'", '')]
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
                                  '        python3 scripts/diagnostic_mac_smoke_route.py validate\n')
            if name.startswith('Retain small'):
                old = old.replace('name: qrcatcher-${{ matrix.scope }}-evidence',
                                  'name: qrcatcher-diagnostic-mac48-${{ matrix.scope }}-evidence')
                label = 'mac' if 'Mac' in name else 'watch'
                budget = 'mac_evidence_budget' if label == 'mac' else 'platform_evidence_budget'
                old = old.replace("always() && steps." + budget + ".outcome == 'success'",
                                  "always() && steps." + budget + ".outcome == 'success' && steps." +
                                  label + "_diagnostic_identity.outcome == 'success'")
            with self.subTest(name=name):
                self.assertEqual(old, new)
        self.assertEqual(originals['checkout'], selected['checkout'])
        old_preflight = route.job_parts(self.canonical)[0]
        new_preflight = route.job_parts(self.workflow)[0]
        self.assertEqual(old_preflight.replace('        test "$GITHUB_REF" = refs/heads/codex/apple-platforms\n',
                                             '        python3 scripts/diagnostic_mac_smoke_route.py validate\n'), new_preflight)

    def test_no_pro_continuation_branch_identity_bypass(self):
        device = '11111111-1111-4111-8111-111111111111'
        env = self.environment(); env.update(EVIDENCE_SCOPE='iphone_pro', SIMULATOR_ID=device)
        with patch.dict(os.environ, env, clear=True), self.assertRaises(ValueError):
            pro_identity(device, 'PhoneUIResults.xcresult')
        env['GITHUB_REF'] = 'refs/heads/codex/apple-platforms'
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(pro_identity(device, 'PhoneUIResults.xcresult'), 'a' * 40)
        self.assertNotIn('GITHUB_REF=', self.workflow)

    def execute_in_checkout(self, mode, scope='macos', mutate=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / '.github/workflows').mkdir(parents=True)
            (root / route.CANONICAL).write_text(self.canonical)
            (root / route.WORKFLOW).write_text(self.workflow)
            folder = root / 'build/mac-evidence'
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

    def test_existing_mac_evidence_folder_receives_bounded_receipt(self):
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
                             ('scope', 'watchos'), ('canonical_workflow_sha256', 'c' * 64),
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
                root = Path(temp).resolve()
                (root / '.github/workflows').mkdir(parents=True)
                (root / route.CANONICAL).write_text(self.canonical)
                (root / route.WORKFLOW).write_text(self.workflow)
                folder = root / 'build/mac-evidence'
                folder.mkdir(parents=True)
                env = self.environment(scope=scope)
                initial = route.identity(env, self.canonical, self.workflow)
                initial.update(tested_tree='b' * 40, source_readback_phase='before build or device/runtime work')
                data = (json.dumps(initial, indent=2) + '\n').encode()
                (root / route.RECEIPT).write_bytes(data)
                env.update({route.INITIAL_HASH_KEY: hashlib.sha256(data).hexdigest(),
                            'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED': 'true', 'GITHUB_WORKSPACE': str(root)})
                program = ("import sys\nfrom pathlib import Path\nsys.path.insert(0," + repr(str(ROOT / 'scripts')) + ")\n"
                           "import diagnostic_mac_smoke_route as route\n"
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

    def test_workflow_has_exact_closed_one_slot_bounds(self):
        self.assertEqual(self.workflow.count('    runs-on: xcode-27\n'), 2)
        self.assertIn('    needs: preflight\n', self.workflow)
        self.assertIn('      max-parallel: 1\n', self.workflow)
        self.assertNotIn('actions/cache', self.workflow)
        self.assertNotIn('actions/download-artifact', self.workflow)
        self.assertNotIn('continue-on-error', self.workflow)
        self.assertIn('python3 -u scripts/compile_platform_preflight.py', self.workflow)
        self.assertIn('        - macos\n', self.workflow)
        self.assertNotIn('        - watchos', self.workflow)
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
            (root / 'build/mac-evidence').mkdir(parents=True)
            old = Path.cwd()
            try:
                os.chdir(root)
                env = self.environment()
                env.update(GITHUB_ENV=str(root / 'runner-environment.txt'), GITHUB_WORKSPACE=str(root))
                with patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()):
                    before = dict(os.environ)
                    with patch.object(route, 'source_readback', return_value='b' * 40):
                        route.main(['validate'])
                    self.assertEqual({key: value for key, value in os.environ.items()
                                      if key != route.INITIAL_HASH_KEY}, before)
                    yield root, dict(os.environ)
            finally:
                os.chdir(old)

    def executable_main(self, root, env, mode, expect_rejection=False):
        program = ("import sys\nfrom pathlib import Path\nsys.path.insert(0," + repr(str(ROOT / 'scripts')) + ")\n"
                   "import diagnostic_mac_smoke_route as route\n"
                   "def forbidden(*args, **kwargs):\n"
                   " Path('unexpected-process.txt').write_text('called')\n"
                   " raise RuntimeError('process/readback forbidden in this fixture')\n"
                   "def audit(event, args):\n"
                   " if event in {'subprocess.Popen','os.system','os.posix_spawn','os.posix_spawnp'}:\n"
                   "  forbidden()\n"
                   "sys.addaudithook(audit)\n"
                   "route.execute=forbidden\nroute.source_readback=forbidden\n"
                   "try:\n route.main(" + repr([mode]) + ")\n"
                   "except (ValueError,FileNotFoundError):\n"
                   " raise SystemExit(" + ('0' if expect_rejection else '2') + ")\n"
                   "raise SystemExit(" + ('1' if expect_rejection else '0') + ")\n")
        result = subprocess.run([sys.executable, '-c', program], cwd=root, env=env,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((root / 'unexpected-process.txt').exists())
        return result

    def test_executable_wrong_context_adversaries_fail_before_any_process(self):
        mutations = [('GITHUB_REPOSITORY', 'other/QRCatcher'),
                     ('GITHUB_REF', route.REF + '-other'),
                     ('GITHUB_WORKFLOW_REF', route.WORKFLOW_REF + '-other'),
                     ('GITHUB_SHA', 'c' * 40), ('GITHUB_WORKFLOW_SHA', 'c' * 40),
                     ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                     ('GITHUB_JOB', 'other'), ('EVIDENCE_SCOPE', 'watchos'),
                     ('EVIDENCE_SCOPE', 'iphone_pro'), ('GITHUB_RUN_ID', '0'),
                     ('GITHUB_RUN_ATTEMPT', '0'), ('RUNNER_OS', 'Linux'),
                     ('RUNNER_ARCH', 'X64'), ('DIAGNOSTIC_ONLY', 'false')]
        for key, value in mutations:
            with self.subTest(key=key, value=value), self.sealed_checkout() as (root, env):
                env[key] = value
                self.executable_main(root, env, 'validate', expect_rejection=True)
                self.executable_main(root, env, 'retain', expect_rejection=True)

    def test_executable_missing_tampered_swapped_and_linked_receipts_fail_without_processes(self):
        def missing(root, env): (root / route.RECEIPT).unlink()
        def tampered(root, env): (root / route.RECEIPT).write_text('{}')
        def swapped(root, env):
            original = root / route.RECEIPT
            original.rename(original.with_suffix('.saved.json'))
            original.write_text('{"source_sha":"wrong"}')
        def symlink(root, env):
            original = root / route.RECEIPT
            original.rename(original.with_suffix('.saved.json'))
            original.symlink_to(original.with_suffix('.saved.json'))
        def hardlink(root, env): os.link(root / route.RECEIPT, root / 'receipt-hardlink.json')
        def oversized(root, env):
            data = b' ' * 4097
            (root / route.RECEIPT).write_bytes(data)
            env[route.INITIAL_HASH_KEY] = route.sha256(data)
        def missing_hash(root, env): env.pop(route.INITIAL_HASH_KEY)
        for mutation in [missing, tampered, swapped, symlink, hardlink, oversized, missing_hash]:
            with self.subTest(mutation=mutation.__name__), self.sealed_checkout() as (root, env):
                mutation(root, env)
                env['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED'] = 'true'
                self.executable_main(root, env, 'retain', expect_rejection=True)
                self.assertFalse((root / 'build/mac-evidence' / route.RECEIPT.name).exists())

    def test_executable_resealed_wrong_receipt_identity_and_schema_fail_without_processes(self):
        mutations = [('source_sha', 'c' * 40), ('workflow_sha', 'c' * 40),
                     ('ref', 'refs/heads/main'), ('workflow_ref', route.WORKFLOW_REF + '-other'),
                     ('run_id', '124'), ('run_attempt', '2'), ('job', 'preflight'),
                     ('scope', 'watchos'), ('selected_scopes', ['macos', 'watchos']),
                     ('diagnostic_only', 1), ('release_qualification', True),
                     ('tested_tree', 'invalid'), ('source_readback_phase', 'after runtime'),
                     ('workflow_sha256', 'c' * 64), ('unknown', True)]
        for field, wrong in mutations:
            with self.subTest(field=field), self.sealed_checkout() as (root, env):
                receipt = root / route.RECEIPT
                value = json.loads(receipt.read_bytes()); value[field] = wrong
                data = json.dumps(value).encode(); receipt.write_bytes(data)
                env[route.INITIAL_HASH_KEY] = route.sha256(data)
                self.executable_main(root, env, 'retain', expect_rejection=True)

    def test_executable_durable_cleanup_uncertainty_retains_initial_source_only_without_processes(self):
        with self.sealed_checkout() as (root, env):
            # Deliberately no propagated cleanup flag: the durable marker alone
            # must be recorded, and cannot prevent pure failure-evidence retention.
            (root / 'build/owned-process-cleanup.json').write_text('{"blocked":true}')
            env['QRCATCHER_OWNED_PROCESS_BARRIER'] = str(root / 'build/owned-process-cleanup.json')
            result = self.executable_main(root, env, 'retain')
            receipt = root / 'build/mac-evidence' / route.RECEIPT.name
            self.assertLessEqual(receipt.stat().st_size, 4096)
            value = json.loads(receipt.read_bytes())
            self.assertIs(value['retention_verification']['owned_cleanup_uncertainty_observed'], True)
            self.assertIs(value['retention_verification']['fresh_source_readback_performed'], False)
            self.assertIn('Only initial source proof retained',
                          value['retention_verification']['final_verification_limit'])
            self.assertEqual(value['tested_tree'], 'b' * 40)
            self.assertIs(value['release_qualification'], False)
            self.assertIn('DIAGNOSTIC_MAC48_PROVENANCE', result.stdout)

    def test_initial_readback_stops_before_processes_on_cleanup_uncertainty(self):
        with patch.dict(os.environ, {'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED': 'true'}), \
                patch.object(route, 'execute') as execute:
            with self.assertRaises(ValueError): route.source_readback('a' * 40)
            execute.assert_not_called()
        with patch.object(route, 'blocked', side_effect=[False, True]), \
                patch.object(route, 'execute', return_value=(0, 'a' * 40,
                             {'state': 'completed', 'cleanup_confirmed': True})) as execute:
            with self.assertRaises(ValueError): route.source_readback('a' * 40)
            self.assertEqual(execute.call_count, 1)

    def test_initial_readback_rejects_untracked_or_staged_dirty_source(self):
        for status in ['?? untracked-script.py', 'M  tracked-script.py', ' M tracked-script.py']:
            responses = [(0, value, {'state': 'completed', 'cleanup_confirmed': True})
                         for value in ['a' * 40, 'b' * 40, '', status]]
            with self.subTest(status=status), patch.object(route, 'blocked', return_value=False), \
                    patch.object(route, 'execute', side_effect=responses), self.assertRaises(ValueError):
                route.source_readback('a' * 40)

    def test_actual_local_git_validation_binds_head_tree_cleanliness_and_seal(self):
        with tempfile.TemporaryDirectory() as temp:
            top = Path(temp).resolve(); root = top / 'checkout'; root.mkdir()
            (root / '.github/workflows').mkdir(parents=True)
            (root / route.CANONICAL).write_text(self.canonical)
            (root / route.WORKFLOW).write_text(self.workflow)
            (root / '.gitignore').write_text('build/\n')
            clean_env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
            def git(*arguments):
                return subprocess.run(['git', *arguments], cwd=root, env=clean_env, check=True,
                                      capture_output=True, text=True, timeout=5).stdout.strip()
            git('init', '-q'); git('add', '--', '.')
            git('-c', 'user.name=Portable fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Local diagnostic source fixture')
            source, tree = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')
            env = {**clean_env, **self.environment()}
            env.update(GITHUB_SHA=source, GITHUB_WORKFLOW_SHA=source,
                       GITHUB_ENV=str(top / 'runner-environment.txt'), GITHUB_WORKSPACE=str(root))
            program = ("import sys\nsys.path.insert(0," + repr(str(ROOT / 'scripts')) + ")\n"
                       "import diagnostic_mac_smoke_route as route\nraise SystemExit(route.main(['validate']))\n")
            def invoke(environment):
                return subprocess.run([sys.executable, '-c', program], cwd=root, env=environment,
                                      capture_output=True, text=True, timeout=10)
            result = invoke(env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = (root / route.RECEIPT).read_bytes(); value = json.loads(data)
            self.assertEqual(value['source_sha'], source); self.assertEqual(value['workflow_sha'], source)
            self.assertEqual(value['tested_tree'], tree); self.assertLessEqual(len(data), 4096)
            self.assertEqual((top / 'runner-environment.txt').read_text(),
                             route.INITIAL_HASH_KEY + '=' + route.sha256(data) + '\n')
            wrong = {**env, 'GITHUB_SHA': 'a' * 40, 'GITHUB_WORKFLOW_SHA': 'a' * 40}
            self.assertNotEqual(invoke(wrong).returncode, 0)
            (root / 'untracked.py').write_text('print("dirty")\n')
            self.assertNotEqual(invoke(env).returncode, 0)
            (root / 'untracked.py').unlink()
            (root / '.gitignore').write_text('build/\n# changed tracked source\n')
            self.assertNotEqual(invoke(env).returncode, 0)

    def test_host_only_always_summary_and_final_source_remain_byte_identical(self):
        _, canonical_platform = route.job_parts(self.canonical)
        _, canonical_steps, _ = route.split_platform(canonical_platform)
        _, mac_platform = route.job_parts(self.workflow)
        _, mac_steps, _ = route.split_platform(mac_platform)
        originals = {route.step_name(step): step for step in canonical_steps}
        selected = {route.step_name(step): step for step in mac_steps}
        for name in ['Summarize executed evidence', 'Verify source stayed unchanged']:
            self.assertEqual(originals[name], selected[name])
            self.assertIn('      if: always()\n', selected[name])
        self.assertIn('xcrun xcresulttool', selected['Summarize executed evidence'])
        self.assertIn('git rev-parse', selected['Verify source stayed unchanged'])
        self.assertNotIn('GITHUB_REF=', self.workflow)
        self.assertNotIn('GITHUB_SHA=', self.workflow)

    def test_workflow_file_aliases_and_oversize_fail_before_processes(self):
        for name in [route.CANONICAL, route.WORKFLOW]:
            with self.subTest(name=name), self.sealed_checkout() as (root, env):
                os.link(root / name, root / 'workflow-hardlink.yml')
                self.executable_main(root, env, 'validate', expect_rejection=True)
                self.executable_main(root, env, 'retain', expect_rejection=True)
            with self.subTest(name=name, oversized=True), self.sealed_checkout() as (root, env):
                (root / name).write_bytes(b' ' * (128 * 1024 + 1))
                self.executable_main(root, env, 'validate', expect_rejection=True)


if __name__ == '__main__':
    unittest.main()
