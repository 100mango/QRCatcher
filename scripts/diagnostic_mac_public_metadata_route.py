#!/usr/bin/env python3
"""Closed, exact-source diagnostic route. This never admits release qualification.

Canonical branch and Pro continuation validation remain unchanged. The only
diagnostic runtime scope is macos. No GITHUB_* value is changed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from atomic_json import write_json
from ios_import_continuation import read_regular
from owned_process_barrier import blocked
from watch_process import execute

REPOSITORY = '100mango/QRCatcher'
BRANCH = 'codex/apple-platforms-diagnostic-mac-public-metadata'
REF = 'refs/heads/' + BRANCH
WORKFLOW = '.github/workflows/apple-platforms-diagnostic-mac-public-metadata.yml'
WORKFLOW_REF = REPOSITORY + '/' + WORKFLOW + '@' + REF
CANONICAL = '.github/workflows/apple-platforms.yml'
CANONICAL_SHA256 = '481b9030b9b80637d35ab408c76d1f8de1e84a8fce5028eb9929a206c645830b'
BASE_SHA = '5b6b4f1cf5470ab6d834505698e56eb35ee8327d'
BASE_TREE = '90579d6202c3716b170c0e3596ff02f41b467653'
SCOPES = ('macos',)
COMPONENT_TREE = '4ebb9c0d0ce6efe8cf27e67ee5396b381d322b06'
CASES = ('testNativeWindowResizeKeepsFullActionTitles', 'testChineseCriticalFlow')
CHECKPOINTS = ('mac-before-resize', 'mac-minimum-window', 'mac-chinese-reopened', 'mac-chinese-policy')

def fixed_commands():
    # Closed argv only; no input, selectors or source/ref override exists.
    base = ['xcodebuild', 'build-for-testing', '-project', 'QRCatcher.xcodeproj',
            '-scheme', 'QRCatcherMacSandbox', '-configuration', 'Debug',
            '-derivedDataPath', 'build/MacSandbox', '-destination', 'platform=macOS,arch=arm64',
            'ARCHS=arm64', 'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGNING_REQUIRED=YES',
            'CODE_SIGN_IDENTITY=-', 'CODE_SIGN_STYLE=Manual', 'DEVELOPMENT_TEAM=',
            'PROVISIONING_PROFILE_SPECIFIER=']
    test = ['env', 'TEST_RUNNER_QRCATCHER_MAC_PUBLIC_METADATA_DIAGNOSTIC=1',
            'xcodebuild', 'test-without-building', '-project', 'QRCatcher.xcodeproj',
            '-scheme', 'QRCatcherMacSandbox', '-configuration', 'Debug',
            '-derivedDataPath', 'build/MacSandbox', '-destination', 'platform=macOS,arch=arm64',
            'ARCHS=arm64', '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
            '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '90',
            '-maximum-test-execution-time-allowance', '150']
    test += ['-only-testing:QRCatcherMacUITests/QRCatcherMacUITests/' + case for case in CASES]
    test += ['-resultBundlePath', 'MacSandboxResults.xcresult', 'CODE_SIGNING_ALLOWED=NO']
    return {'sandbox_build': (base, 240), 'sandbox_test': (test, 600)}

CANONICAL_DRIVER_SHA256 = '79468a33261c598b17f147c4812c32e7664852bd13cb720385632814356d412e'
COMPONENT_FILES = [('QRCatcherMac/QRCatcherMacApp.swift', '9f34a7460cdde90295598356da6ab094e673df6c479061dde69a09ff461b690b', 26393, '100644'), ('QRCatcherMacUITests/QRCatcherMacUITests.swift', '6ae59acc68685e734a912ea64aec3653764862a3770fe5bebf2b3ec6174b8b26', 74651, '100644'), ('Tests/Harness/test_mac_public_metadata.py', 'f7cdc9db6a45f424057ca3747caa439c2ffdf79886850da0421d26b58984e673', 30195, '100644'), ('scripts/mac_public_metadata_schema.py', '2672c4cfe6e67539ae30851b6e959b39fbd95e040683c55d366e88904c730894', 28891, '100644'), ('scripts/verify_mac_release.py', '4a5d934a1e1040bf5bf68922349e6f0a886ade2b005119d3fe795a5a291189f1', 2275, '100644')]


def render_driver(canonical):
    require(sha256(canonical.encode()) == CANONICAL_DRIVER_SHA256, 'Canonical Mac48 driver changed')
    value = canonical.replace('set -euo pipefail\n', 'set -euo pipefail\npython3 scripts/diagnostic_mac_public_metadata_route.py validate-target\n', 1)
    value = value.replace('600 xcodebuild test-without-building', '600 env TEST_RUNNER_QRCATCHER_MAC_PUBLIC_METADATA_DIAGNOSTIC=1 xcodebuild test-without-building')
    return value.replace('-resultBundlePath MacSandboxResults.xcresult', ' '.join('-only-testing:QRCatcherMacUITests/QRCatcherMacUITests/' + case for case in CASES) + ' -resultBundlePath MacSandboxResults.xcresult')


def verify_target_source():
    require(read_regular('scripts/run_mac_public_metadata.sh', 16 * 1024).decode() ==
            render_driver(read_regular('scripts/run_mac_sandbox.sh', 16 * 1024).decode()),
            'Fixed two-case driver differs from the closed reviewed route')
    for name, fingerprint, size, mode in COMPONENT_FILES:
        data = read_regular(name, 256 * 1024)
        actual_mode = '100755' if Path(name).stat().st_mode & 0o111 else '100644'
        require(len(data) == size and sha256(data) == fingerprint and actual_mode == mode,
                'Immutable metadata component bytes/mode changed: ' + name)
    return True

RECEIPT = Path('build/diagnostic-mac-public-metadata-provenance.json')
INITIAL_HASH_KEY = 'QRCATCHER_MAC_PUBLIC_METADATA_INITIAL_PROVENANCE_SHA256'

SELECTED_STEPS = (
    'Verify exact source and stable toolchain',
    'Build native Mac unsigned Release arm64 and x86_64',
    'Execute native Mac hosted regression tests',
    'Execute ephemeral ad-hoc App Sandbox UI gate',
    'Export bounded native Mac screenshots',
    'Validate native Mac outbound evidence budget',
    'Retain small native Mac evidence',
    'Summarize executed evidence',
    'Verify source stayed unchanged',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def job_parts(canonical):
    jobs = canonical.split('jobs:\n', 1)[1].split("'on':\n", 1)[0]
    preflight, platform = jobs.split('  platform:\n', 1)
    return preflight, platform


def split_platform(platform):
    header, remainder = platform.split('    steps:\n', 1)
    steps_text, tail = remainder.split('    name: ${{ matrix.scope }}', 1)
    steps = re.findall(r'    - (?:uses|name): .*?(?=    - (?:uses|name): |\Z)',
                       steps_text, re.DOTALL)
    require(''.join(steps) == steps_text, 'Unrecognized canonical steps')
    return header + '    steps:\n', steps, '    name: ${{ matrix.scope }}' + tail


def step_name(step):
    first = step.splitlines()[0]
    return first.removeprefix('    - name: ') if first.startswith('    - name: ') else 'checkout'


def render_workflow(canonical):
    require(sha256(canonical.encode()) == CANONICAL_SHA256,
            'Canonical thirteen-row workflow is not byte-identical')
    preflight, platform = job_parts(canonical)
    header, steps, _ = split_platform(platform)
    selected = [step for step in steps if step_name(step) == 'checkout' or step_name(step) in SELECTED_STEPS]
    require(len(selected) == len(SELECTED_STEPS) + 1, 'Missing or duplicate canonical selected step')
    route_check = '        python3 scripts/diagnostic_mac_public_metadata_route.py validate\n'
    ref_check = '        test "$GITHUB_REF" = refs/heads/codex/apple-platforms\n'
    require(preflight.count(ref_check) == 1, 'Missing preflight branch check')
    preflight = preflight.replace(ref_check, route_check)
    platform_text = header + ''.join(selected)
    require(platform_text.count(ref_check) == 1, 'Missing platform branch check')
    platform_text = platform_text.replace(ref_check, route_check)
    # Only the explicitly reviewed UI selector, collector and Release namespaces
    # differ from Mac48. Other selected commands and every cap remain unchanged.
    old_driver = '        bash scripts/run_mac_sandbox.sh\n'
    require(platform_text.count(old_driver) == 1, 'Missing exact sandbox driver')
    platform_text = platform_text.replace(old_driver, '        bash scripts/run_mac_public_metadata.sh\n')
    old_export = '      run: python3 -u scripts/export_mac_screenshots.py\n'
    require(platform_text.count(old_export) == 1, 'Missing exact canonical exporter')
    platform_text = platform_text.replace(old_export, '      run: python3 -u scripts/export_mac_public_metadata.py\n')
    old_names = 'QRCATCHER_TEST_STORE|QRCATCHER_SANDBOX_|sandboxDiagnostics|fixture-payload|reset-history|MAC_NATIVE_AX_'
    require(platform_text.count(old_names) == 1, 'Missing separate native Release regex')
    platform_text = platform_text.replace(old_names, old_names + '|QRCATCHER_MAC_PUBLIC_METADATA_|MAC_PUBLIC_METADATA_|QRCatcher\\.MacPublicMetadata\\.|org\\.qrcatcher\\.mac-public-metadata\\.|MacAuditPublicMetadataObserver')
    # Preserve all selected command bodies. Metadata changes label the artifacts
    # and an additional bounded receipt is included before existing budget gates.
    platform_text = platform_text.replace(
        '        name: qrcatcher-${{ matrix.scope }}-evidence\n',
        '        name: qrcatcher-diagnostic-mac-public-metadata-${{ matrix.scope }}-evidence\n')
    marker = '    - name: Validate native Mac outbound evidence budget\n'
    receipt = ('    - name: Retain diagnostic Mac identity\n'
               '      id: mac_diagnostic_identity\n'
               "      if: ${{ matrix.scope == 'macos' && always() }}\n"
               '      timeout-minutes: 1\n'
               '      run: python3 scripts/diagnostic_mac_public_metadata_route.py retain\n')
    require(platform_text.count(marker) == 1, 'Missing evidence gate')
    platform_text = platform_text.replace(marker, receipt + marker)
    platform_text = platform_text.replace(
        "always() && steps.mac_evidence_budget.outcome == 'success'",
        "always() && steps.mac_evidence_budget.outcome == 'success' && "
        "steps.mac_diagnostic_identity.outcome == 'success'")
    prefix = ("name: Diagnostic Mac public metadata (fixed two cases)\n"
              "permissions:\n  contents: read\n"
              "concurrency:\n  group: qrcatcher-apple-platforms\n  cancel-in-progress: false\n"
              "env:\n  DIAGNOSTIC_ONLY: 'true'\n"
              "jobs:\n")
    strategy = ("    name: ${{ matrix.scope }} · diagnostic-only fresh standard VM\n"
                "    strategy:\n      fail-fast: false\n      max-parallel: 1\n"
                "      matrix:\n        scope:\n        - macos\n")
    trigger = "'on':\n  push:\n    branches:\n    - " + BRANCH + '\n'
    return prefix + preflight + '  platform:\n' + platform_text + strategy + trigger


def verify_workflow(canonical, workflow):
    require(workflow == render_workflow(canonical),
            'Diagnostic workflow differs from the closed reviewed route')


def identity(environment, canonical, workflow):
    verify_workflow(canonical, workflow)
    source = environment.get('GITHUB_SHA', '')
    require(re.fullmatch('[0-9a-f]{40}', source) is not None, 'Invalid source SHA')
    require(environment.get('GITHUB_REPOSITORY') == REPOSITORY, 'Wrong repository')
    require(environment.get('GITHUB_REF') == REF, 'Wrong dedicated diagnostic branch')
    require(environment.get('GITHUB_WORKFLOW_REF') == WORKFLOW_REF, 'Wrong diagnostic workflow/ref')
    require(environment.get('GITHUB_WORKFLOW_SHA') == source, 'Workflow/source SHA differs')
    require(environment.get('GITHUB_EVENT_NAME') == 'push', 'Diagnostic route is dedicated branch push only')
    require(environment.get('DIAGNOSTIC_ONLY') == 'true', 'Diagnostic-only mode must be true')
    require(environment.get('RUNNER_OS') == 'macOS' and environment.get('RUNNER_ARCH') == 'ARM64',
            'Wrong standard Mac runner OS/architecture')
    job, scope = environment.get('GITHUB_JOB'), environment.get('EVIDENCE_SCOPE', '')
    require((job == 'preflight' and scope == '') or (job == 'platform' and scope in SCOPES),
            'Wrong diagnostic job or selected scope')
    require(re.fullmatch('[1-9][0-9]*', environment.get('GITHUB_RUN_ID', '')) is not None and
            re.fullmatch('[1-9][0-9]*', environment.get('GITHUB_RUN_ATTEMPT', '')) is not None,
            'Missing exact run identity')
    return {'version': 1, 'diagnostic_only': True, 'release_qualification': False,
            'repository': REPOSITORY, 'source_sha': source,
            'workflow_sha': environment['GITHUB_WORKFLOW_SHA'], 'ref': REF,
            'workflow_ref': WORKFLOW_REF, 'workflow_sha256': sha256(workflow.encode()),
            'canonical_workflow_sha256': CANONICAL_SHA256,
            'base_public_sha': BASE_SHA, 'base_public_tree': BASE_TREE,
            'metadata_component_tree': COMPONENT_TREE, 'selected_ui_cases': list(CASES),
            'metadata_checkpoints': list(CHECKPOINTS),
            'metadata_environment': 'QRCATCHER_MAC_PUBLIC_METADATA_DIAGNOSTIC=1',
            'native_hosted_test_count': 26, 'selected_ui_test_count': 2,
            'run_id': environment['GITHUB_RUN_ID'], 'run_attempt': environment['GITHUB_RUN_ATTEMPT'],
            'job': job, 'scope': scope, 'selected_scopes': list(SCOPES),
            'permissions': {'contents': 'read'}, 'runner': 'xcode-27',
            'maximum_simultaneous_slots': 1, 'cancel_in_progress': False,
            'preflight_job_minutes': 20, 'platform_job_minutes': 45,
            'scope_evidence_limit_bytes': {'macos': 3_000_000},
            'whole_run_limit_bytes': 20_000_000, 'retention_days': 1,
            'qualification_limit': 'Selected-source diagnostic only; source fixes require separate root admission; no release acceptance'}


def source_readback(source):
    def checked(command):
        require(not blocked(), 'Diagnostic source readback blocked by cleanup uncertainty')
        code, output, operation = execute(command, 5, output_limit=4096, tail_limit=4096, echo=False)
        require(code == 0 and operation.get('state') == 'completed' and
                operation.get('cleanup_confirmed') is True,
                'Diagnostic source readback did not finish with confirmed cleanup')
        require(not blocked(), 'Cleanup uncertainty arose during diagnostic source readback')
        return output.strip()
    require(checked(['git', 'rev-parse', 'HEAD']) == source, 'Checkout HEAD/source SHA differs')
    tree = checked(['git', 'rev-parse', 'HEAD^{tree}'])
    require(re.fullmatch('[0-9a-f]{40}', tree) is not None, 'Invalid source tree readback')
    checked(['git', 'diff', '--exit-code', 'HEAD', '--'])
    require(checked(['git', 'status', '--porcelain=v1', '--untracked-files=all']) == '',
            'Initial diagnostic checkout contains tracked or untracked changes')
    return tree


def retained_initial_record(expected):
    data = read_regular(RECEIPT, 4096)
    fingerprint = os.environ.get(INITIAL_HASH_KEY, '')
    require(re.fullmatch('[0-9a-f]{64}', fingerprint) is not None and sha256(data) == fingerprint,
            'Initial diagnostic receipt fingerprint differs or is missing')
    initial = json.loads(data)
    require(type(initial) is dict and set(initial) == set(expected) | {'tested_tree', 'source_readback_phase'},
            'Initial diagnostic receipt schema differs')
    require(json.dumps({key: initial[key] for key in expected}, sort_keys=True, allow_nan=False) ==
            json.dumps(expected, sort_keys=True, allow_nan=False),
            'Initial diagnostic receipt source/workflow/ref/run/job/scope differs')
    require(initial['source_readback_phase'] == 'before build or device/runtime work' and
            isinstance(initial['tested_tree'], str) and
            re.fullmatch('[0-9a-f]{40}', initial['tested_tree']) is not None,
            'Initial diagnostic source tree/readback phase differs')
    initial['retention_verification'] = {
        'initial_receipt_sha256': fingerprint,
        'owned_cleanup_uncertainty_observed': blocked(),
        'fresh_source_readback_performed': False,
        'final_verification_limit': 'Only initial source proof retained; separate unchanged final workflow step is authoritative if completed'}
    return initial


def current_identity():
    return identity(os.environ, read_regular(CANONICAL, 128 * 1024).decode('utf-8'),
                    read_regular(WORKFLOW, 128 * 1024).decode('utf-8'))


def main(arguments):
    require(arguments in [['validate'], ['retain'], ['validate-target']], 'Unknown diagnostic route operation')
    root = Path.cwd()
    record = current_identity()
    if arguments == ['validate-target']:
        require(record['job'] == 'platform' and record['scope'] == 'macos', 'Target is platform Mac only')
        require(not blocked(), 'Selected metadata target blocked by cleanup uncertainty')
        retained_initial_record(record)
        verify_target_source()
        return 0
    if arguments == ['retain']:
        require(record['job'] == 'platform', 'Only platform evidence may be retained')
        record = retained_initial_record(record)
        folder = Path('build/mac-evidence')
        require(folder.is_dir() and not folder.is_symlink() and folder.resolve() == root / folder,
                'Evidence folder must be the existing canonical real directory')
        write_json(folder / RECEIPT.name, record, limit=4096)
    else:
        record['tested_tree'] = source_readback(record['source_sha'])
        record['source_readback_phase'] = 'before build or device/runtime work'
        require(not RECEIPT.parent.is_symlink() and
                (not RECEIPT.parent.exists() or RECEIPT.parent.is_dir()),
                'Diagnostic receipt parent must be a real directory')
        RECEIPT.parent.mkdir(exist_ok=True)
        write_json(RECEIPT, record, limit=4096)
        fingerprint = sha256(read_regular(RECEIPT, 4096))
        # This job's runner-managed environment file propagates the exact initial
        # receipt fingerprint to later steps, without adding any source literal.
        environment_file = os.environ.get('GITHUB_ENV', '')
        require(environment_file, 'Missing runner-managed job environment file')
        with open(environment_file, 'a') as output:
            output.write(INITIAL_HASH_KEY + '=' + fingerprint + '\n')
        os.environ[INITIAL_HASH_KEY] = fingerprint
    print('DIAGNOSTIC_MAC_PUBLIC_METADATA_PROVENANCE ' + json.dumps(record, sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
