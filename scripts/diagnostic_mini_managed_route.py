#!/usr/bin/env python3
"""One closed full-Mini diagnostic profile; never release qualification.

The thirteen-row canonical workflow remains byte-identical. Platform source
readback is performed by the existing bounded managed prepare/final scripts.
No command is spawned by prepared()/retain_prepared() inside the real lease.
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
BRANCH = 'codex/mini-managed-full-row'
REF = 'refs/heads/' + BRANCH
WORKFLOW = '.github/workflows/mini-managed-full-row.yml'
WORKFLOW_REF = REPOSITORY + '/' + WORKFLOW + '@' + REF
CANONICAL = '.github/workflows/apple-platforms.yml'
CANONICAL_SHA256 = '1c3b0759c211b54ec30bd8d19cac9e7a4f03b77dea94ae81146910f10ff202d4'
BASE_SHA = '7b1c3b048f46f939e1a861569ed5f80fe27df59f'
BASE_TREE = '81562d42563b159e8a1ace7d3af6d5e2542c5733'
SCOPES = ('ipad_mini',)
RECEIPT = Path('build/diagnostic-mini-managed-provenance.json')
INITIAL_HASH_KEY = 'QRCATCHER_MINI_DIAGNOSTIC_INITIAL_PROVENANCE_SHA256'
SELECTED_STEPS = (
    'Capture original Mini job clock before checkout',
    'Checkout Mini exact source with bounded main and post',
    'Verify Mini exact source inside original job budget',
    'Compile Mini tests inside original job budget',
    'Configure one newly owned Mini without manual boot or install',
    'Run native iPad mini workflows',
    'Export bounded complete Mini row evidence',
    'Validate Mini and whole-run evidence allocation',
    'Admit complete Mini artifact action inside original clock',
    'Retain small phone and iPad evidence',
    'Observe Mini artifact action without claiming host-group cleanup',
    'Summarize all four Mini cases from exact exported results',
    'Verify final Mini source while preserving checkout-post reserve',
)


def require(value, message):
    if not value:
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
            'Canonical managed thirteen-row workflow changed')
    preflight, platform = job_parts(canonical)
    header, steps, _ = split_platform(platform)
    selected = [step for step in steps if step_name(step) in SELECTED_STEPS]
    require(tuple(step_name(step) for step in selected) == SELECTED_STEPS,
            'Missing, reordered or duplicate selected full-Mini step')
    ref_check = '        test "$GITHUB_REF" = refs/heads/codex/apple-platforms\n'
    require(preflight.count(ref_check) == 1, 'Missing preflight branch check')
    preflight = preflight.replace(ref_check,
        '        python3 scripts/diagnostic_mini_managed_route.py validate\n')
    platform_text = header + ''.join(selected)
    require(header.count('    timeout-minutes: 45\n') == 1, 'Canonical platform job cap changed')
    platform_text = platform_text.replace('    timeout-minutes: 45\n', '    timeout-minutes: 50\n', 1)
    require(platform_text.count('      timeout-minutes: 27\n') == 1, 'Canonical Mini work cap changed')
    platform_text = platform_text.replace('      timeout-minutes: 27\n', '      timeout-minutes: 32\n', 1)
    require(platform_text.count("'mini':1620") == 1, 'Canonical Mini origin cap changed')
    platform_text = platform_text.replace("'mini':1620", "'mini':1920", 1)
    clock_ref = "        require(os.environ['GITHUB_REF']=='refs/heads/codex/apple-platforms')\n"
    require(platform_text.count(clock_ref) == 1, 'Missing exact original clock branch binding')
    clock_binding = ("        require(os.environ['GITHUB_REF']=='" + REF + "')\n"
        "        require(os.environ.get('GITHUB_WORKFLOW_REF')=='" + WORKFLOW_REF + "')\n"
        "        require(os.environ.get('GITHUB_EVENT_NAME')=='push' and os.environ.get('DIAGNOSTIC_ONLY')=='true')\n"
        "        require(os.environ.get('GITHUB_JOB')=='platform' and os.environ.get('EVIDENCE_SCOPE')=='ipad_mini')\n")
    platform_text = platform_text.replace(clock_ref, clock_binding)
    platform_text = platform_text.replace(
        '        name: qrcatcher-${{ matrix.scope }}-evidence\n',
        '        name: qrcatcher-diagnostic-mini-managed-${{ matrix.scope }}-evidence\n')
    prefix = ("name: Diagnostic full Mini managed row\npermissions:\n  contents: read\n"
        "concurrency:\n  group: qrcatcher-apple-platforms\n  cancel-in-progress: false\n"
        "env:\n  DIAGNOSTIC_ONLY: 'true'\njobs:\n")
    strategy = ("    name: ${{ matrix.scope }} · diagnostic-only fresh standard VM\n"
        "    strategy:\n      fail-fast: false\n      max-parallel: 1\n"
        "      matrix:\n        scope:\n        - ipad_mini\n")
    return prefix + preflight + '  platform:\n' + platform_text + strategy + "'on':\n  push:\n    branches:\n    - " + BRANCH + '\n'


def identity(environment, canonical, workflow):
    require(workflow == render_workflow(canonical), 'Diagnostic workflow differs from closed full-Mini route')
    source = environment.get('GITHUB_SHA', '')
    require(re.fullmatch('[0-9a-f]{40}', source) is not None, 'Invalid source SHA')
    require(environment.get('GITHUB_REPOSITORY') == REPOSITORY and environment.get('GITHUB_REF') == REF,
            'Wrong diagnostic repository/ref')
    require(environment.get('GITHUB_WORKFLOW_REF') == WORKFLOW_REF and
            environment.get('GITHUB_WORKFLOW_SHA') == source, 'Wrong workflow/ref/source binding')
    require(environment.get('GITHUB_EVENT_NAME') == 'push' and environment.get('DIAGNOSTIC_ONLY') == 'true',
            'Exact diagnostic-only branch push required')
    require(environment.get('RUNNER_OS') == 'macOS' and environment.get('RUNNER_ARCH') == 'ARM64',
            'Wrong standard Mac architecture')
    job, scope = environment.get('GITHUB_JOB'), environment.get('EVIDENCE_SCOPE', '')
    require((job == 'preflight' and scope == '') or (job == 'platform' and scope == 'ipad_mini'),
            'Wrong job/selected scope')
    require(all(re.fullmatch('[1-9][0-9]{0,19}', environment.get(key, '')) is not None
                for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')), 'Missing exact run identity')
    return {'version': 1, 'diagnostic_only': True, 'release_qualification': False,
        'repository': REPOSITORY, 'source_sha': source, 'workflow_sha': source,
        'ref': REF, 'workflow_ref': WORKFLOW_REF, 'workflow_sha256': sha256(workflow.encode()),
        'canonical_workflow_sha256': CANONICAL_SHA256,
        'base_public_sha': BASE_SHA, 'base_public_tree': BASE_TREE,
        'run_id': environment['GITHUB_RUN_ID'], 'run_attempt': environment['GITHUB_RUN_ATTEMPT'],
        'job': job, 'scope': scope, 'selected_scopes': list(SCOPES),
        'permissions': {'contents': 'read'}, 'runner': 'xcode-27',
        'maximum_simultaneous_slots': 1, 'cancel_in_progress': False,
        'preflight_job_minutes': 20, 'platform_job_minutes': 50, 'mini_row_seconds': 1920,
        'scope_evidence_limit_bytes': {'ipad_mini': 2_000_000},
        'whole_run_limit_bytes': 20_000_000, 'retention_days': 1,
        'required_native_case_counts': {'layout': 2, 'files': 1, 'photos': 1},
        'qualification_limit': 'Exact-source full-Mini diagnostic only; no release acceptance'}


def current_identity():
    return identity(os.environ, read_regular(CANONICAL, 128 * 1024).decode('utf-8'),
                    read_regular(WORKFLOW, 128 * 1024).decode('utf-8'))


def source_readback(source):
    """Preflight only. Never entered from the real platform host lease."""
    require(os.environ.get('GITHUB_JOB') == 'preflight', 'Generic source readback is preflight only')
    def checked(command):
        require(not blocked(), 'Preflight cleanup uncertainty')
        code, output, operation = execute(command, 5, output_limit=4096, tail_limit=4096, echo=False)
        require(code == 0 and operation.get('state') == 'completed' and
                operation.get('cleanup_confirmed') is True and not blocked(),
                'Preflight source readback incomplete or cleanup uncertain')
        return output.strip()
    require(checked(['git', 'rev-parse', 'HEAD']) == source, 'Preflight HEAD/source differs')
    tree = checked(['git', 'rev-parse', 'HEAD^{tree}'])
    require(re.fullmatch('[0-9a-f]{40}', tree) is not None, 'Invalid source tree')
    checked(['git', 'diff', '--exit-code', 'HEAD', '--'])
    require(checked(['git', 'status', '--porcelain=v1', '--untracked-files=all']) == '',
            'Initial preflight checkout contains changes')
    return tree


def write_initial(record, tree, phase):
    require(re.fullmatch('[0-9a-f]{40}', tree) is not None, 'Invalid prepared source tree')
    record = {**record, 'tested_tree': tree, 'source_readback_phase': phase}
    require(not RECEIPT.parent.is_symlink() and RECEIPT.parent.resolve() == Path.cwd() / RECEIPT.parent,
            'Real checkout receipt parent required')
    RECEIPT.parent.mkdir(exist_ok=True)
    write_json(RECEIPT, record, limit=4096)
    fingerprint = sha256(read_regular(RECEIPT, 4096))
    environment_file = os.environ.get('GITHUB_ENV', '')
    require(environment_file, 'Missing runner-managed job environment file')
    with open(environment_file, 'a') as output:
        output.write(INITIAL_HASH_KEY + '=' + fingerprint + '\n')
    os.environ[INITIAL_HASH_KEY] = fingerprint
    return record


def prepared(head, tree):
    """Pure bounded receipt operation inside existing controller-owned prepare."""
    record = current_identity()
    require(record['job'] == 'platform' and head == record['source_sha'], 'Wrong managed prepare HEAD/job')
    require(os.environ.get('GITHUB_WORKSPACE') == str(Path.cwd()) and
            Path.cwd().resolve(strict=True) == Path.cwd(), 'Actual managed prepare checkout required')
    marker = Path('build/ipad-mini-host-inflight.json')
    before = read_regular(marker, 4096)
    lease = json.loads(before)
    require(type(lease) is dict and type(lease.get('owner_pid')) is int and lease['owner_pid'] > 0 and
            lease == {'source': record['source_sha'], 'workflow_sha': record['workflow_sha'],
                      'run_id': record['run_id'], 'run_attempt': record['run_attempt'],
                      'scope': 'ipad_mini', 'phase': 'host-prepare', 'owner_pid': lease['owner_pid'],
                      'command': ['bash', 'scripts/ipad_mini_prepare.sh']}, 'Exact owned prepare marker required')
    # Pure reads and the small provenance write preserve the controller's marker.
    # Native/host ownership and inode completion stay with the existing Claim.
    result = write_initial(record, tree, 'existing bounded Mini prepare HEAD/tree/diff commands')
    require(read_regular(marker, 4096) == before, 'Prepare marker changed during receipt retention')
    return result


def retained_initial_record(expected):
    data = read_regular(RECEIPT, 4096)
    fingerprint = os.environ.get(INITIAL_HASH_KEY, '')
    require(re.fullmatch('[0-9a-f]{64}', fingerprint) is not None and sha256(data) == fingerprint,
            'Initial prepared receipt fingerprint differs or is missing')
    initial = json.loads(data)
    require(type(initial) is dict and set(initial) == set(expected) | {'tested_tree', 'source_readback_phase'},
            'Prepared receipt schema differs')
    require(json.dumps({key: initial[key] for key in expected}, sort_keys=True, allow_nan=False) ==
            json.dumps(expected, sort_keys=True, allow_nan=False), 'Prepared source/workflow/ref/run/job differs')
    require(initial['source_readback_phase'] == 'existing bounded Mini prepare HEAD/tree/diff commands' and
            re.fullmatch('[0-9a-f]{40}', initial['tested_tree']) is not None, 'Wrong prepared tree/readback phase')
    initial['retention_verification'] = {'initial_receipt_sha256': fingerprint,
        'device_barrier_observed': blocked(), 'fresh_source_readback_performed': False,
        'final_verification_limit': 'Initial prepare proof only; unchanged final managed HEAD/tree/diff phase and runner post result remain separate'}
    return initial


def retain_prepared():
    """No process execution; called inside the existing bounded export phase."""
    record = current_identity()
    require(record['job'] == 'platform', 'Platform evidence only')
    record = retained_initial_record(record)
    folder = Path('build/ios-platform-evidence')
    require(folder.is_dir() and not folder.is_symlink() and folder.resolve() == Path.cwd() / folder,
            'Existing real platform evidence directory required')
    write_json(folder / RECEIPT.name, record, limit=4096)
    return record


def main(arguments):
    if arguments == ['validate']:
        record = current_identity()
        require(record['job'] == 'preflight', 'Generic validation is preflight only')
        record = write_initial(record, source_readback(record['source_sha']), 'before preflight build or runtime work')
    elif len(arguments) == 3 and arguments[0] == 'prepared':
        record = prepared(arguments[1], arguments[2])
    else:
        raise ValueError('Only fixed preflight or prepared-source operations are permitted')
    print('DIAGNOSTIC_MINI_MANAGED_PROVENANCE ' + json.dumps(record, sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
