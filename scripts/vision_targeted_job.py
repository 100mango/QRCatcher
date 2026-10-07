#!/usr/bin/env python3
"""Fixed privacy functional workflow adapter with retained legacy helper coverage. Native execution requires a separately approved workflow."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

from atomic_json import write_json
from owned_process_barrier import blocked, mark_unconfirmed
from vision_case_contract import select_case
from validate_evidence_budget import inspect
from watch_process import execute
from run_vision_ui_cases import native_operation_unconfirmed

PARENT = 'fe50717d8a3783b7b451b161f2541b9207bcf385'
BRANCH = 'refs/heads/codex/vision-targeted-completion'
WORKFLOW = '.github/workflows/vision-targeted-completion.yml'
JOBS = {'photos': ('visionos_photos', 2700, 450), 'privacy': ('visionos_privacy', 1500, 330)}
COMMON = {'prepare': 180, 'build': 440, 'probe': 690, 'install': 120,
          'shutdown': 75, 'source_final': 30, 'validate': 30, 'verdict': 10}
CAPS = {
    'photos': dict(COMMON, hosted=595, seed=155, ui=690, collect=180),
    'privacy': dict(COMMON, ui=390, collect=90),
}
BUSINESS = {
    'photos': ('prepare', 'build', 'probe', 'install', 'hosted', 'seed', 'ui'),
    'privacy': ('prepare', 'build', 'probe', 'install', 'ui'),
}
FINAL = ('collect', 'shutdown', 'source_final', 'validate', 'verdict')
ALLOWED_CHANGED = {
    '.github/workflows/vision-targeted-completion.yml',
    'QRCatcherVisionUITests/QRCatcherVisionUITests.swift',
    'Tests/Harness/test_vision_async_contract.py',
    'Tests/Harness/test_vision_targeted_job.py',
    'Tests/Harness/test_vision_targeted_privacy.py',
    'scripts/capture_vision_checkpoints.py',
    'scripts/export_vision_case_evidence.py',
    'scripts/vision_case_contract.py',
    'scripts/vision_targeted_job.py',
    'scripts/vision_targeted_source_inputs.json',
}
NATIVE = {'build', 'probe', 'install', 'hosted', 'seed', 'ui', 'shutdown'}


def require(value, message):
    if not value:
        raise ValueError(message)


def load_regular(path, limit=512 * 1024):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path.absolute(),
            'Expected a canonical regular input: ' + path.name)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= limit,
                'Invalid input file size or identity')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(limit + 1)
        after = os.fstat(fd)
        signature = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(data) == before.st_size and signature(before) == signature(after) == signature(path.stat()),
                'Input changed while reading')
        return data
    finally:
        os.close(fd)


def read_json(path, limit=512 * 1024):
    return json.loads(load_regular(path, limit))


def inspect_clock(value, env, now):
    job = env.get('GITHUB_JOB')
    require(job in JOBS, 'Unknown fixed targeted job')
    scope, ceiling, reserve = JOBS[job]
    expected = {'schema': 1, 'repository': '100mango/QRCatcher', 'ref': BRANCH,
                'source': env.get('GITHUB_SHA'), 'workflow_sha': env.get('GITHUB_WORKFLOW_SHA'),
                'run_id': env.get('GITHUB_RUN_ID'), 'attempt': env.get('GITHUB_RUN_ATTEMPT'),
                'job': job, 'scope': scope, 'ceiling_seconds': ceiling, 'reserve_seconds': reserve}
    require(isinstance(value, dict) and set(value) == set(expected) | {'started_monotonic'}, 'Clock schema mismatch')
    for key, item in expected.items():
        require(type(value[key]) is type(item) and value[key] == item, 'Clock binding mismatch: ' + key)
    require(env.get('GITHUB_REPOSITORY') == expected['repository'] and env.get('GITHUB_REF') == BRANCH,
            'Wrong repository or branch')
    require(re.fullmatch('[0-9a-f]{40}', expected['source'] or '') and expected['source'] == expected['workflow_sha'],
            'Workflow/source identity mismatch')
    require(all(re.fullmatch('[1-9][0-9]{0,19}', expected[k] or '') for k in ['run_id', 'attempt']),
            'Invalid run identity')
    require(env.get('EVIDENCE_SCOPE') == scope, 'Job and selected case differ')
    start = value['started_monotonic']
    require(type(start) in (int, float) and math.isfinite(start) and 0 < start <= now, 'Invalid original job clock')
    return job, scope, ceiling - (now - start)


def phase_allowance(job, phase, remaining):
    require(phase in CAPS[job], 'Unknown or unrequested phase')
    cap = CAPS[job][phase]
    if phase in BUSINESS[job]:
        reserve = JOBS[job][2]
    else:
        # Evidence is collected before shutdown. All post-work phases preserve
        # later phase caps and a 90s upload/checkout-post reserve.
        reserve = sum(CAPS[job][p] for p in FINAL[FINAL.index(phase) + 1:]) + 90
    require(type(remaining) in (int, float) and math.isfinite(remaining) and remaining >= cap + reserve,
            'Original clock cannot admit this phase with its remaining reserve')
    return cap


def uncertain_operation(phase, code, operation, inner=None):
    if phase not in NATIVE:
        return False
    if code in (124, 125, 126) or operation.get('cleanup_confirmed') is not True or operation.get('state') != 'completed':
        return True
    if phase == 'ui':
        rows = inner.get('cases', []) if isinstance(inner, dict) else []
        if len(rows) != 1:
            return True
        row = rows[0]; command = row.get('operation', {})
        termination = row.get('pre_case_app_termination', {})
        capture_exit = inner.get('capture_process_exit')
        return (native_operation_unconfirmed(termination.get('exit'), termination)
                or native_operation_unconfirmed(row.get('exit'), command)
                or type(capture_exit) is not int or capture_exit < 0 or capture_exit in (124, 125, 126)
                or inner.get('capture_cleanup_confirmed') is not True
                or inner.get('cleanup_unconfirmed') is True)
    return False


def source_snapshot(root, runner):
    def git(*args):
        code, text, operation = runner(['git', *args], 10)
        require(code == 0 and operation.get('cleanup_confirmed') is True, 'Source Git command failed')
        return text.strip()
    head = git('rev-parse', 'HEAD')
    require(head == os.environ['GITHUB_SHA'], 'Checkout does not match selected source')
    require(git('rev-list', '--parents', '-n', '1', 'HEAD').split() == [head, PARENT], 'Expected exactly the published sole parent')
    require(git('diff', '--name-only', 'HEAD', '--') == '', 'Tracked source was modified')
    changed = set(git('diff', '--name-only', PARENT, 'HEAD', '--').splitlines())
    require(changed == ALLOWED_CHANGED, 'Unexpected source delta outside the frozen targeted candidate')
    paths = git('ls-files').splitlines()
    require(paths and len(paths) == len(set(paths)), 'Invalid source inventory')
    rows = []
    for name in paths:
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Escaped source input')
        path = root / name
        raw = load_regular(path, 4 * 1024 * 1024)
        rows.append({'path': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                     'mode': '100755' if path.stat().st_mode & 0o111 else '100644'})
    actual = {r['path']: r for r in rows}
    reference = read_json(root / 'scripts/vision_targeted_source_inputs.json')
    require(reference.get('base_commit') == PARENT and reference.get('base_tree') == 'dc749076aecb943e47136888444721a282ac2cdd',
            'Wrong published input reference')
    expected = reference.get('unchanged_inputs')
    require(isinstance(expected, list) and len(expected) == 416, 'Incomplete unchanged-input reference')
    require(len({r['path'] for r in expected}) == len(expected), 'Duplicate unchanged input')
    for row in expected:
        require(row['path'] not in ALLOWED_CHANGED and actual.get(row['path']) == row,
                'Unchanged product/build input differs: ' + row['path'])
    return {'source': head, 'tree': git('rev-parse', 'HEAD^{tree}'), 'files': rows}


class Job:
    def __init__(self, phase):
        self.root = Path.cwd().resolve(strict=True)
        require(os.environ.get('GITHUB_WORKSPACE') == str(self.root), 'Wrong canonical workspace')
        clock = Path(os.environ['QRCATCHER_VISION_TARGETED_CLOCK'])
        temporary = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
        expected_name = 'qr-vision-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT'] + '-' + os.environ['GITHUB_JOB'] + '.json'
        require(clock.parent == temporary and clock.name == expected_name, 'Wrong original clock path')
        self.clock = read_json(clock, 4096)
        self.job, self.scope, self.remaining = inspect_clock(self.clock, os.environ, time.monotonic())
        self.case = select_case(self.scope); self.phase = phase
        self.cap = phase_allowance(self.job, phase, self.remaining)
        self.deadline = time.monotonic() + self.cap
        self.stages = self.root / 'build/vision-targeted-stages'; self.stages.mkdir(parents=True, exist_ok=True)
        binding_path = self.stages / 'original-clock.json'
        clock_binding = {'sha256': hashlib.sha256(load_regular(clock, 4096)).hexdigest(),
                         'device': clock.stat().st_dev, 'inode': clock.stat().st_ino}
        if binding_path.exists():
            require(read_json(binding_path, 4096) == clock_binding, 'The original clock was replaced or reset')
        elif phase == 'prepare':
            fd = os.open(binding_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as output:
                json.dump(clock_binding, output); output.flush(); os.fsync(output.fileno())
        elif phase in NATIVE:
            raise ValueError('No prepared original clock binding before native work')
        for path in self.stages.glob('*.json'):
            if path.name == 'original-clock.json':
                continue
            prior = read_json(path, 128 * 1024)
            if prior.get('phase') in NATIVE and prior.get('state') == 'started':
                mark_unconfirmed({'state': 'targeted_controller_interrupted', 'exit': 126, 'cleanup_confirmed': False})
        self.receipt = self.stages / (phase + '.json')
        require(not self.receipt.exists() and not self.receipt.is_symlink(), 'A phase cannot run twice')
        self.row = {'phase': phase, 'source': os.environ['GITHUB_SHA'], 'scope': self.scope, 'job': self.job,
                    'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                    'started_monotonic': time.monotonic(), 'original_started_monotonic': self.clock['started_monotonic'],
                    'remaining_at_admission': self.remaining, 'allowance_seconds': self.cap, 'state': 'started', 'operations': []}
        fd = os.open(self.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump(self.row, out); out.flush(); os.fsync(out.fileno())

    def previous(self, name):
        value = read_json(self.stages / (name + '.json'), 128 * 1024)
        expected = {'phase': name, 'source': os.environ['GITHUB_SHA'], 'scope': self.scope,
                    'job': self.job, 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT']}
        require(isinstance(value, dict) and all(value.get(k) == v for k, v in expected.items()),
                'Prior phase belongs to another source/case/run')
        return value

    def write(self):
        write_json(self.receipt, self.row, limit=128 * 1024)

    def run(self, args, seconds):
        require(time.monotonic() + seconds + 3 <= self.deadline, 'Phase clock cannot admit the unchanged command cap')
        if self.phase in NATIVE:
            require(not blocked(), 'Unresolved operation forbids another native command')
        self.row['operations'].append({'command': args, 'timeout_seconds': seconds, 'state': 'starting'})
        self.write()
        try:
            code, output, operation = execute(args, seconds, output_limit=16 * 1024 * 1024, tail_limit=128 * 1024)
        except BaseException:
            if self.phase in NATIVE:
                mark_unconfirmed({'state': 'targeted_controller_interrupted', 'exit': 126, 'cleanup_confirmed': False})
                self.row['simulator_operation_unconfirmed'] = True
            raise
        inner = None
        if self.phase == 'ui' and (self.root / 'build/vision-runtime/ui-cases.json').is_file():
            inner = read_json(self.root / 'build/vision-runtime/ui-cases.json')
        unknown = uncertain_operation(self.phase, code, operation, inner)
        self.row['operations'][-1] = operation
        if unknown:
            mark_unconfirmed(dict(operation, state='targeted_native_operation_uncertain', exit=126))
            self.row['simulator_operation_unconfirmed'] = True
        self.write()
        require(not unknown, 'Native operation completion is uncertain; no further device command')
        require(code == 0 and operation.get('cleanup_confirmed') is True, 'Required command failed: ' + args[0])
        return code, output, operation

    def require_predecessors(self):
        if self.phase not in BUSINESS[self.job]:
            return
        for name in BUSINESS[self.job][:BUSINESS[self.job].index(self.phase)]:
            prior = self.previous(name)
            require(prior.get('state') == 'passed' and prior.get('source') == os.environ['GITHUB_SHA']
                    and prior.get('scope') == self.scope, 'Required predecessor did not pass: ' + name)
        require(not blocked(), 'A previous uncertain operation remains blocked')

    def prepare(self):
        initial = source_snapshot(self.root, self.run)
        write_json(self.root / 'build/vision-targeted-source.json', initial, limit=512 * 1024)
        _, version, _ = self.run(['xcodebuild', '-version'], 15)
        require('27A266a' in version, 'Unexpected Xcode toolchain')
        _, architecture, _ = self.run(['uname', '-m'], 5)
        require(architecture.strip() == 'arm64', 'Expected the standard arm64 runner')
        for args, cap in [([sys.executable, '-m', 'unittest', 'discover', '-s', 'Tests/Harness', '-p', 'test_vision_*.py'], 65),
                          ([sys.executable, '-O', '-m', 'unittest', 'discover', '-s', 'Tests/Harness', '-p', 'test_vision_*.py'], 65),
                          ([sys.executable, 'scripts/verify_portable_source.py'], 10),
                          ([sys.executable, 'scripts/materialize_qr_fixtures.py'], 10),
                          (['xcrun', 'swift', 'scripts/materialize_native_icons.swift'], 25),
                          ([sys.executable, 'scripts/generate_project.py'], 10)]:
            self.run(args, cap)
        require(source_snapshot(self.root, self.run) == initial, 'Preparation changed tracked inputs')

    def native(self):
        device = os.environ.get('VISION_SIMULATOR_ID', '')
        if self.phase in {'install', 'hosted', 'seed', 'ui', 'shutdown'}:
            require(re.fullmatch('[A-F0-9-]{36}', device), 'No exact owned Vision device')
        common = ['xcodebuild', 'test-without-building', '-project', 'QRCatcher.xcodeproj', '-scheme', 'QRCatcherVision',
                  '-configuration', 'Debug', '-derivedDataPath', 'build/VisionTests', '-destination',
                  'platform=visionOS Simulator,id=' + device, '-parallel-testing-enabled', 'NO',
                  '-collect-test-diagnostics', 'never', '-test-timeouts-enabled', 'YES']
        commands = {
            'build': (['xcodebuild', 'build-for-testing', '-project', 'QRCatcher.xcodeproj', '-scheme', 'QRCatcherVision',
                       '-configuration', 'Debug', '-derivedDataPath', 'build/VisionTests', '-destination',
                       'generic/platform=visionOS Simulator', 'ARCHS=arm64', 'CODE_SIGNING_ALLOWED=NO'], 435),
            'probe': ([sys.executable, '-u', 'scripts/probe_vision_runtime.py'], 670),
            'install': (['bash', '-c', '. scripts/run_vision_fenced_command.sh install'], 110),
            'hosted': (common + ['-default-test-execution-time-allowance', '90', '-maximum-test-execution-time-allowance', '150',
                                '-only-testing:QRCatcherVisionTests', '-resultBundlePath', 'VisionTestResults.xcresult', 'CODE_SIGNING_ALLOWED=NO'], 555),
            'seed': (['xcrun', 'simctl', 'addmedia', device, 'Tests/Fixtures/unicode.png'], 150),
            'ui': ([sys.executable, '-u', 'scripts/run_vision_ui_cases.py', device, self.scope], 680 if self.job == 'photos' else 380),
            'shutdown': (['bash', '-c', '. scripts/run_vision_fenced_command.sh shutdown'], 65),
        }
        self.run(*commands[self.phase])
        if self.phase == 'hosted':
            _, text, _ = self.run(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary',
                                  '--path', 'VisionTestResults.xcresult'], 30)
            summary = json.loads(text)
            from export_vision_case_evidence import validate_result
            validate_result(summary, {}, self.case, device, hosted=True)
            runtime = self.root / 'build/vision-runtime'; runtime.mkdir(exist_ok=True)
            write_json(runtime / 'hosted-summary.json', summary, limit=128 * 1024)
            self.row['actual_hosted_passed'] = 11

    def retain_host_failure(self, reason):
        out = self.root / 'build/ios-platform-evidence'
        out.mkdir(exist_ok=True)
        require(not any(out.iterdir()), 'Failure evidence destination is not empty')
        runtime = self.root / 'build/vision-runtime'
        names = ['runtime.json', 'hosted-summary.json', 'ui-cases.json', 'runner-bindings.json', 'checkpoint-captures.json',
                 'host-failure-capture.json', 'fenced-install.json', 'fenced-shutdown.json']
        candidates = [(runtime / n, 'vision-' + n, 64 * 1024) for n in names]
        candidates += [(runtime / (n + '.jpg'), 'vision-' + n + '.jpg', 800 * 1024) for n in self.case.frames]
        candidates += [(runtime / 'vision-host-failure.jpg', 'vision-host-failure.jpg', 800 * 1024)]
        rows = []
        for path, name, cap in candidates:
            if not path.exists():
                continue
            try:
                raw = load_regular(path, cap)
                if path.suffix == '.json': json.loads(raw)
                (out / name).write_bytes(raw)
                rows.append({'name': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
            except (OSError, ValueError) as error:
                rows.append({'name': name, 'unretained_error': str(error)[:500]})
        manifest = {'scope': self.scope, 'source_commit': os.environ['GITHUB_SHA'],
                   'run_id': os.environ['GITHUB_RUN_ID'], 'qualified': False, 'host_only_retention': True,
                   'native_followup_started': False, 'reason': reason, 'files': rows}
        if self.case.functional_only:
            manifest.update(qualification='functional-only', new_privacy_pixels=False, store_screenshots=False)
        write_json(out / 'manifest.json', manifest, limit=64 * 1024)
        self.row['host_only_retention'] = True

    def collect(self):
        try:
            passed = self.previous('ui').get('state') == 'passed'
        except (OSError, ValueError):
            passed = False
        if blocked() or not passed:
            self.retain_host_failure('UI was unexecuted, failed or uncertain; diagnostic pixels do not qualify')
            return
        self.run([sys.executable, 'scripts/export_vision_case_evidence.py', self.scope], self.cap - 10)

    def source_final(self):
        require(source_snapshot(self.root, self.run) == read_json(self.root / 'build/vision-targeted-source.json'),
                'Final source differs from pre-native inputs')

    def validate(self):
        out = self.root / 'build/ios-platform-evidence'
        required = list(BUSINESS[self.job]) + ['collect', 'shutdown', 'source_final']
        receipts = {}
        for name in required:
            try: receipts[name] = self.previous(name)
            except (OSError, ValueError): receipts[name] = {'state': 'unexecuted'}
        try: manifest = read_json(out / 'manifest.json')
        except (OSError, ValueError): manifest = {'qualified': False}
        qualified = (not blocked() and manifest.get('qualified') is True
                     and all(r.get('state') == 'passed' for r in receipts.values()))
        terminal = {'source': os.environ['GITHUB_SHA'], 'scope': self.scope, 'job': self.job,
                    'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                    'qualified': qualified, 'phases': receipts,
                    'original_started_monotonic': self.clock['started_monotonic'],
                    'elapsed_seconds': time.monotonic() - self.clock['started_monotonic'],
                    'scope_limit_bytes': self.case.evidence_bytes, 'only_requested_case': self.case.name,
                    'files_rerun': False, 'system_size_modified': False}
        if self.case.functional_only:
            terminal.update(qualification='functional-only', new_privacy_pixels=False, store_screenshots=False)
        try:
            require(out.is_dir() and not out.is_symlink(), 'No safe collected evidence directory')
            write_json(out / 'targeted-job.json', terminal, limit=128 * 1024)
            inspect(out, limit=self.case.evidence_bytes)
            path = 'build/ios-platform-evidence'
        except (OSError, ValueError) as error:
            # Do not destroy or truncate required pixels just to make a cap pass.
            # Retain a separate bounded failure receipt if the primary artifact
            # cannot be uploaded, while leaving all original evidence local.
            qualified = False; terminal['qualified'] = False
            terminal['primary_evidence_blocker'] = str(error)[:1000]
            fallback = self.root / 'build/vision-targeted-failure'; fallback.mkdir(exist_ok=True)
            write_json(fallback / 'targeted-job.json', terminal, limit=128 * 1024)
            inspect(fallback, limit=self.case.evidence_bytes)
            path = 'build/vision-targeted-failure'
        self.row.update(qualified=qualified, artifact_path=path, evidence_validated=True)
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write('eligible=true\nartifact_path=' + path + '\n')

    def verdict(self):
        require(self.previous('validate').get('qualified') is True, 'Requested Vision case has not qualified')
        require(not blocked(), 'Unresolved operation prevents successful verdict')

    def perform(self):
        try:
            self.require_predecessors()
            if self.phase == 'shutdown' and (blocked() or not os.environ.get('VISION_SIMULATOR_ID')):
                self.row['state'] = 'unexecuted_unsafe_or_no_device'; self.write()
                raise ValueError('No safe simulator shutdown after uncertainty or missing device')
            if self.phase in NATIVE: self.native()
            else: getattr(self, self.phase)()
            self.row['state'] = 'passed'; self.row['elapsed_seconds'] = time.monotonic() - self.row['started_monotonic']
            self.write()
        except BaseException as error:
            self.row.update(state='failed', error=str(error)[:1600], elapsed_seconds=time.monotonic() - self.row['started_monotonic'])
            self.write()
            raise


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('phase', choices=tuple(COMMON) + ('hosted', 'seed', 'ui', 'collect'))
    args = parser.parse_args()
    require(os.environ.get('GITHUB_JOB') == 'privacy' and os.environ.get('EVIDENCE_SCOPE') == 'visionos_privacy',
            'This published adapter admits only the fixed functional privacy job')
    Job(args.phase).perform()


if __name__ == '__main__':
    main()
