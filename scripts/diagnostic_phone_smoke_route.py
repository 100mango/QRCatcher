#!/usr/bin/env python3
"""Closed, exact-source diagnostic route. This never admits release qualification.

Canonical branch behavior is preserved. The only diagnostic runtime scopes
are the complete iphone_pro and iphone_se3 profiles. No GITHUB_* value is changed.
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
BRANCH = 'codex/apple-platforms-diagnostic-phone47'
REF = 'refs/heads/' + BRANCH
WORKFLOW = '.github/workflows/apple-platforms-diagnostic-phone.yml'
WORKFLOW_REF = REPOSITORY + '/' + WORKFLOW + '@' + REF
CANONICAL = '.github/workflows/apple-platforms.yml'
CANONICAL_SHA256 = '481b9030b9b80637d35ab408c76d1f8de1e84a8fce5028eb9929a206c645830b'
BASE_SHA = '7b1c3b048f46f939e1a861569ed5f80fe27df59f'
BASE_TREE = '81562d42563b159e8a1ace7d3af6d5e2542c5733'
SCOPES = ('iphone_pro', 'iphone_se3')
RECEIPT = Path('build/diagnostic-phone47-provenance.json')
INITIAL_HASH_KEY = 'QRCATCHER_PHONE_DIAGNOSTIC_INITIAL_PROVENANCE_SHA256'

SELECTED_STEPS = (
    'Verify exact source and stable toolchain',
    'Compile iOS tests before this device boots',
    'Select this fresh VM phone or iPad device',
    'Run iOS codec equivalence and existing unit regression',
    'Run large-phone UI regression',
    'Run compact-phone UI regression',
    'Export bounded phone and iPad evidence',
    'Validate isolated platform and whole-run evidence allocation',
    'Retain small phone and iPad evidence',
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
            'Canonical thirteen-row workflow is not frozen47 byte-identical')
    preflight, platform = job_parts(canonical)
    header, steps, _ = split_platform(platform)
    selected = [step for step in steps if step_name(step) == 'checkout' or step_name(step) in SELECTED_STEPS]
    require(len(selected) == len(SELECTED_STEPS) + 1, 'Missing or duplicate canonical selected step')
    route_check = '        python3 scripts/diagnostic_phone_smoke_route.py validate\n'
    ref_check = '        test "$GITHUB_REF" = refs/heads/codex/apple-platforms\n'
    require(preflight.count(ref_check) == 1, 'Missing preflight branch check')
    preflight = preflight.replace(ref_check, route_check)
    platform_text = header + ''.join(selected)
    require(platform_text.count(ref_check) == 1, 'Missing platform branch check')
    platform_text = platform_text.replace(ref_check, route_check)
    # Preserve all selected command bodies. Metadata changes label the artifacts
    # and an additional bounded receipt is included before existing budget gates.
    platform_text = platform_text.replace(
        '        name: qrcatcher-${{ matrix.scope }}-evidence\n',
        '        name: qrcatcher-diagnostic-phone47-${{ matrix.scope }}-evidence\n')
    marker = '    - name: Validate isolated platform and whole-run evidence allocation\n'
    receipt = ('    - name: Retain diagnostic phone identity\n'
               '      id: phone_diagnostic_identity\n'
               '      if: ${{ always() }}\n'
               '      timeout-minutes: 1\n'
               '      run: python3 scripts/diagnostic_phone_smoke_route.py retain\n')
    require(platform_text.count(marker) == 1, 'Missing evidence gate')
    platform_text = platform_text.replace(marker, receipt + marker)
    platform_text = platform_text.replace(
        "always() && steps.platform_evidence_budget.outcome == 'success'",
        "always() && steps.platform_evidence_budget.outcome == 'success' && "
        "steps.phone_diagnostic_identity.outcome == 'success'")
    prefix = ("name: Diagnostic Apple phone smoke (Pro and SE3 only)\n"
              "permissions:\n  contents: read\n"
              "concurrency:\n  group: qrcatcher-apple-platforms\n  cancel-in-progress: false\n"
              "env:\n  DIAGNOSTIC_ONLY: 'true'\n"
              "jobs:\n")
    strategy = ("    name: ${{ matrix.scope }} · diagnostic-only fresh standard VM\n"
                "    strategy:\n      fail-fast: false\n      max-parallel: 2\n"
                "      matrix:\n        scope:\n        - iphone_pro\n        - iphone_se3\n")
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
            'run_id': environment['GITHUB_RUN_ID'], 'run_attempt': environment['GITHUB_RUN_ATTEMPT'],
            'job': job, 'scope': scope, 'selected_scopes': list(SCOPES),
            'permissions': {'contents': 'read'}, 'runner': 'xcode-27',
            'maximum_simultaneous_slots': 2, 'cancel_in_progress': False,
            'preflight_job_minutes': 20, 'platform_job_minutes': 45,
            'scope_evidence_limit_bytes': {'iphone_pro': 2_000_000, 'iphone_se3': 2_000_000},
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


def verify_continuation_context(source):
    """Additional exact phone context; pure file reads, no source/process call.

    The existing continuation caller still checks canonical UUID/result/Pro
    scope, finalized nine-case failure, source/products, budgets and cleanup.
    """
    require(not blocked(), 'Diagnostic continuation blocked by cleanup uncertainty')
    record = current_identity()
    require(record['source_sha'] == source and record['job'] == 'platform' and
            record['scope'] == 'iphone_pro', 'Wrong diagnostic continuation context')
    return retained_initial_record(record)


def main(arguments):
    require(arguments in [['validate'], ['retain']], 'Unknown diagnostic route operation')
    root = Path.cwd()
    record = current_identity()
    if arguments == ['retain']:
        require(record['job'] == 'platform', 'Only platform evidence may be retained')
        record = retained_initial_record(record)
        folder = Path('build/ios-platform-evidence')
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
    print('DIAGNOSTIC_PHONE_PROVENANCE ' + json.dumps(record, sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
