#!/usr/bin/env python3
"""Local single Store screenshot workflow candidate. Native execution requires a separately approved exact tree."""
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
from vision_store_evidence import inspect
from watch_process import execute
from run_vision_ui_cases import native_operation_unconfirmed
from vision_archive_capture import capture, CaptureStopped

BASE = '6675f0051fbb597ed7212819cd34fb0b1e42c7b5'
BASE_TREE = 'f7cefb13a5ddf20b9564b67df094b52f2a37dce8'
PARENT = 'f7009c0e4bbd594a2bdee37c60ba2afb77780df3'
PARENT_TREE = '2bbee558315fe43ff2699de43b1ccbacc0189c48'
SUCCESSOR_PATHS = {'scripts/vision_store_job.py'}
BRANCH = 'refs/heads/vision-store-screenshot'
WORKFLOW = '.github/workflows/vision-store-screenshot.yml'
JOBS = {'store': ('visionos_store', 2700, 360)}
COMMON = {'prepare': 180, 'build': 440, 'probe': 690, 'install': 120,
          'shutdown': 75, 'source_final': 30, 'validate': 30, 'verdict': 10}
CAPS = {'store': dict(COMMON, seed=155, ui=510, collect=100)}
BUSINESS = {'store': ('prepare', 'build', 'probe', 'install', 'seed', 'ui')}
FINAL = ('collect', 'shutdown', 'source_final', 'validate', 'verdict')
ALLOWED_CHANGED = {'scripts/vision_store_image.py', 'scripts/run_vision_store_case.py', '.github/workflows/vision-store-screenshot.yml', 'Tests/Harness/test_vision_store_job.py', 'QRCatcherVisionUITests/QRCatcherVisionUITests.swift', 'Tests/Harness/test_vision_async_contract.py', 'Tests/Harness/test_vision_store_image.py', 'scripts/vision_command_fence.py', 'scripts/capture_vision_store_checkpoint.py', 'scripts/probe_vision_runtime.py', 'Tests/Harness/test_vision_targeted_job.py', 'scripts/run_vision_fenced_command.sh', 'scripts/vision_store_evidence.py', 'scripts/vision_case_contract.py', 'scripts/vision_store_job.py', 'Tests/Harness/test_vision_store_capture.py', 'scripts/vision_store_source_inputs.json'}
NATIVE = {'build', 'probe', 'install', 'seed', 'ui', 'shutdown'}


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
    require(job in JOBS, 'Unknown fixed store job')
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
    require(env.get('GITHUB_RUN_ATTEMPT') == '1' and env.get('GITHUB_EVENT_NAME') == 'push', 'Only the first fixed push attempt is allowed')
    require(env.get('GITHUB_WORKFLOW_REF') == '100mango/QRCatcher/' + WORKFLOW + '@' + BRANCH, 'Unexpected workflow identity')
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
        capture_exit = inner.get('capture_process_exit')
        return (native_operation_unconfirmed(row.get('exit'), command)
                or type(capture_exit) is not int or capture_exit < 0 or capture_exit in (124, 125, 126)
                or inner.get('capture_cleanup_confirmed') is not True
                or inner.get('cleanup_unconfirmed') is True)
    return False


def source_git_read(args, seconds):
    allowed = {('git', 'rev-parse', 'HEAD'), ('git', 'rev-list', '--parents', '-n', '1', 'HEAD'),
               ('git', 'diff', '--name-only', 'HEAD', '--'), ('git', 'rev-parse', PARENT + '^{tree}'),
               ('git', 'diff', '--name-only', PARENT, 'HEAD', '--'), ('git', 'ls-files'),
               ('git', 'rev-parse', 'HEAD^{tree}')}
    require(tuple(args) in allowed, 'Only the fixed read-only source Git commands are permitted')
    started = time.monotonic()
    operation = {'command': args, 'timeout_seconds': seconds, 'host_read_only': True}
    try:
        result = capture(args, seconds=seconds, cap=256 * 1024, cleanup_grace=2)
        raw = result.stdout + result.stderr
        operation.update(state='completed', exit=result.returncode, cleanup_confirmed=True)
    except CaptureStopped as error:
        raw = getattr(error, 'stdout_prefix', b'') + getattr(error, 'stderr_capture', b'')
        operation.update(state='capture_stopped', exit=126, cleanup_confirmed=error.cleanup_confirmed,
                         reason=str(error), cancelled_signal=error.cancelled_signal)
    operation.update(output_bytes=len(raw), elapsed_seconds=time.monotonic() - started)
    return operation['exit'], raw.decode('utf-8', 'replace'), operation


def source_snapshot(root, runner):
    def git(*args):
        code, text, operation = runner(['git', *args], 10)
        require(code == 0 and operation.get('cleanup_confirmed') is True, 'Source Git command failed')
        return text.strip()
    head = git('rev-parse', 'HEAD')
    require(head == os.environ['GITHUB_SHA'], 'Checkout does not match selected source')
    require(git('rev-list', '--parents', '-n', '1', 'HEAD').split() == [head, PARENT], 'Expected exactly the published sole parent')
    require(git('diff', '--name-only', 'HEAD', '--') == '', 'Tracked source was modified')
    require(git('rev-parse', PARENT + '^{tree}') == PARENT_TREE, 'Published product parent tree differs')
    changed = set(git('diff', '--name-only', PARENT, 'HEAD', '--').splitlines())
    require(changed == SUCCESSOR_PATHS, 'Unexpected source delta outside the Store runner correction')
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
    reference = read_json(root / 'scripts/vision_store_source_inputs.json')
    require(reference.get('base_commit') == BASE and reference.get('base_tree') == BASE_TREE,
            'Wrong published input reference')
    expected = reference.get('unchanged_inputs')
    require(isinstance(expected, list) and len(expected) == 425, 'Incomplete unchanged-input reference')
    require(len({r['path'] for r in expected}) == len(expected), 'Duplicate unchanged input')
    for row in expected:
        require(row['path'] not in ALLOWED_CHANGED and actual.get(row['path']) == row,
                'Unchanged product/build input differs: ' + row['path'])
    return {'source': head, 'tree': git('rev-parse', 'HEAD^{tree}'), 'files': rows}


class Job:
    def __init__(self, phase):
        self.root = Path.cwd().resolve(strict=True)
        require(os.environ.get('GITHUB_WORKSPACE') == str(self.root), 'Wrong canonical workspace')
        clock = Path(os.environ['QRCATCHER_VISION_STORE_CLOCK'])
        temporary = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
        expected_name = 'qr-vision-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT'] + '-' + os.environ['GITHUB_JOB'] + '.json'
        require(clock.parent == temporary and clock.name == expected_name, 'Wrong original clock path')
        self.clock = read_json(clock, 4096)
        self.job, self.scope, self.remaining = inspect_clock(self.clock, os.environ, time.monotonic())
        self.case = select_case(self.scope); self.phase = phase
        self.cap = phase_allowance(self.job, phase, self.remaining)
        self.deadline = time.monotonic() + self.cap
        self.stages = self.root / 'build/vision-store-stages'; self.stages.mkdir(parents=True, exist_ok=True)
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
                mark_unconfirmed({'state': 'store_controller_interrupted', 'exit': 126, 'cleanup_confirmed': False})
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
        host_source = self.phase == 'source_final'
        require(time.monotonic() + seconds + (4 if host_source else 3) <= self.deadline,
                'Phase clock cannot admit the unchanged command cap')
        if self.phase in NATIVE:
            require(not blocked(), 'Unresolved operation forbids another native command')
        self.row['operations'].append({'command': args, 'timeout_seconds': seconds, 'state': 'starting'})
        self.write()
        try:
            if host_source:
                # This closed host-only route never clears the device barrier.
                code, output, operation = source_git_read(args, seconds)
            else:
                code, output, operation = execute(args, seconds, output_limit=16 * 1024 * 1024, tail_limit=128 * 1024)
        except BaseException:
            if self.phase in NATIVE:
                mark_unconfirmed({'state': 'store_controller_interrupted', 'exit': 126, 'cleanup_confirmed': False})
                self.row['simulator_operation_unconfirmed'] = True
            raise
        inner = None
        if self.phase == 'ui' and (self.root / 'build/vision-runtime/ui-cases.json').is_file():
            inner = read_json(self.root / 'build/vision-runtime/ui-cases.json')
        unknown = uncertain_operation(self.phase, code, operation, inner)
        self.row['operations'][-1] = operation
        if unknown:
            mark_unconfirmed(dict(operation, state='store_native_operation_uncertain', exit=126))
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
        write_json(self.root / 'build/vision-store-source.json', initial, limit=512 * 1024)
        _, version, _ = self.run(['xcodebuild', '-version'], 15)
        require('27A266a' in version, 'Unexpected Xcode toolchain')
        _, architecture, _ = self.run(['uname', '-m'], 5)
        require(architecture.strip() == 'arm64', 'Expected the standard arm64 runner')
        # Full Vision aggregate is frozen and reviewed locally. Native work
        # only repeats this single-shot Store adapter's focused contracts.
        for args, cap in [([sys.executable, '-m', 'unittest', 'discover', '-s', 'Tests/Harness', '-p', 'test_vision_store_*.py'], 65),
                          ([sys.executable, '-O', '-m', 'unittest', 'discover', '-s', 'Tests/Harness', '-p', 'test_vision_store_*.py'], 65),
                          ([sys.executable, 'scripts/verify_portable_source.py'], 10),
                          ([sys.executable, 'scripts/materialize_qr_fixtures.py'], 10),
                          (['xcrun', 'swift', 'scripts/materialize_native_icons.swift'], 25),
                          ([sys.executable, 'scripts/generate_project.py'], 10)]:
            self.run(args, cap)
        require(source_snapshot(self.root, self.run) == initial, 'Preparation changed tracked inputs')

    def native(self):
        device = os.environ.get('VISION_SIMULATOR_ID', '')
        if self.phase in {'install', 'seed', 'ui', 'shutdown'}:
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
            'seed': (['xcrun', 'simctl', 'addmedia', device, 'Tests/Fixtures/unicode.png'], 150),
            'ui': ([sys.executable, '-u', 'scripts/run_vision_store_case.py', device, self.scope], 500),
            'shutdown': (['bash', '-c', '. scripts/run_vision_fenced_command.sh shutdown'], 65),
        }
        self.run(*commands[self.phase])

    def retain_host_failure(self, reason):
        from vision_store_evidence import collect
        collect(self.root, self.scope, allow_encode=False, failure_reason=reason)
        self.row['host_only_retention'] = True

    def collect(self):
        try:
            passed = self.previous('ui').get('state') == 'passed'
        except (OSError, ValueError):
            passed = False
        if blocked() or not passed:
            self.retain_host_failure('UI was unexecuted, failed or uncertain; diagnostic pixels do not qualify')
            return
        self.run([sys.executable, 'scripts/vision_store_evidence.py', self.scope], self.cap - 10)

    def source_final(self):
        require(source_snapshot(self.root, self.run) == read_json(self.root / 'build/vision-store-source.json'),
                'Final source differs from pre-native inputs')

    def validate(self):
        out = self.root / 'build/vision-store-evidence'
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
                    'files_rerun': False, 'full_photos_export_chain_rerun': False, 'system_size_modified': False,
                    'product_commit': BASE, 'store_upload_qualified': False, 'pixel_review_pending': True}
        if self.case.functional_only:
            terminal.update(qualification='functional-only', new_privacy_pixels=False, store_screenshots=False)
        try:
            require(out.is_dir() and not out.is_symlink(), 'No safe collected evidence directory')
            write_json(out / 'store-job.json', terminal, limit=128 * 1024)
            inspect(out, limit=self.case.evidence_bytes)
            path = 'build/vision-store-evidence'
        except (OSError, ValueError) as error:
            # Do not destroy or truncate required pixels just to make a cap pass.
            # Retain a separate bounded failure receipt if the primary artifact
            # cannot be uploaded, while leaving all original evidence local.
            qualified = False; terminal['qualified'] = False
            terminal['primary_evidence_blocker'] = str(error)[:1000]
            fallback = self.root / 'build/vision-store-failure'; fallback.mkdir(exist_ok=True)
            write_json(fallback / 'store-job.json', terminal, limit=128 * 1024)
            inspect(fallback, limit=self.case.evidence_bytes)
            path = 'build/vision-store-failure'
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
    parser.add_argument('phase', choices=tuple(COMMON) + ('seed', 'ui', 'collect'))
    args = parser.parse_args()
    require(os.environ.get('GITHUB_JOB') == 'store' and os.environ.get('EVIDENCE_SCOPE') == 'visionos_store',
            'This local candidate admits only the fixed single Store screenshot job')
    Job(args.phase).perform()


if __name__ == '__main__':
    main()
