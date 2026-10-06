"""Admit independent Pro imports only after the observed finalized UI failure.

Never retries a test or clears its failure. Missing finalization, an outer
timeout, changed source/device/products or uncertain owned cleanup fails closed.
"""
import json
import hashlib
import math
import os
from pathlib import Path
import plistlib
import re
import stat
import sys
import time
import uuid

from atomic_json import write_json
from owned_process_barrier import blocked
from watch_process import execute

RECORD = Path('build/ios-import-continuation.json')
RESULT = 'PhoneUIResults.xcresult'
RESERVE = 90  # Finish cleanup/receipts before the unchanged 20-minute step ends.
BUDGETS = {'setup-and-files': 75 + 360 + 8 + 10, 'files': 360 + 4,
           'seed-and-photos': 210 + 360 + 8 + 10, 'photos': 360 + 4}
CAMERA_TIMEOUT = 'Test exceeded execution time allowance of 3 minutes'


def read_regular(path, limit):
    path = Path(path)
    if path.is_symlink() or path.resolve(strict=True) != Path.cwd() / path:
        raise ValueError('Continuation evidence is outside its canonical checkout path')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= limit:
            raise ValueError('Continuation evidence is not an independent bounded file')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) != info.st_size or len(data) > limit:
            raise ValueError('Continuation evidence changed or exceeded its bound')
        return data
    finally:
        os.close(descriptor)


def budget(start, phase, now=None):
    now = time.monotonic() if now is None else now
    if not math.isfinite(start) or start < 0 or start > now or phase not in BUDGETS:
        raise ValueError('Invalid bounded step clock or phase')
    remaining = 1200 - (now - start)
    required = BUDGETS[phase] + RESERVE
    return {'phase': phase, 'remaining_seconds': round(remaining, 3), 'required_seconds': required,
            'cleanup_evidence_reserve_seconds': RESERVE, 'admitted': remaining >= required}


def checked(command, seconds):
    code, output, operation = execute(command, seconds, output_limit=256 * 1024, tail_limit=128 * 1024, echo=False)
    if code != 0 or operation.get('state') != 'completed' or operation.get('cleanup_confirmed') is not True:
        raise RuntimeError('Continuation prerequisite did not complete cleanly: ' + json.dumps(operation))
    return output


def identity(device, result):
    if str(uuid.UUID(device)).upper() != device or result != RESULT:
        raise ValueError('Continuation is scoped to the exact observed Pro result/device')
    source = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch('[0-9a-f]{40}', source) or os.environ.get('GITHUB_REPOSITORY') != '100mango/QRCatcher' or os.environ.get('GITHUB_REF') not in ('refs/heads/codex/apple-platforms','refs/heads/codex/ios-original-release'):
        raise ValueError('Unexpected source/repository/ref')
    if os.environ.get('GITHUB_REF')=='refs/heads/codex/ios-original-release':
        from ios_original_release_route import current_identity
        current_identity()  # Explicit source/ref/workflow/Pro binding; no process.
    if os.environ.get('EVIDENCE_SCOPE') != 'iphone_pro' or os.environ.get('SIMULATOR_ID') != device:
        raise ValueError('Unexpected platform/device profile')
    return source


def expected_command(device):
    project='QRCatcher.xcodeproj'
    if os.environ.get('GITHUB_REF')=='refs/heads/codex/ios-original-release':
        from ios_original_release_route import current_identity,PROJECT
        current_identity();project=PROJECT
    return ['xcodebuild', 'test-without-building', '-project', project, '-scheme', 'QRCatcher',
            '-configuration', 'Debug', '-derivedDataPath', 'build/iOS', '-destination', 'platform=iOS Simulator,id=' + device,
            '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never', '-test-timeouts-enabled', 'YES',
            '-default-test-execution-time-allowance', '180', '-maximum-test-execution-time-allowance', '240',
            'CODE_SIGNING_ALLOWED=NO', '-only-testing:QRCatcherUITests/QRCatcherUITests',
            '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPickerWarmupAndCancelPreservesPreviousSelection',
            '-resultBundlePath', RESULT]


def validate_finalization(operation, summary, device, now=None):
    if operation.get('command') != expected_command(device) or operation.get('timeout_seconds') != 570 or operation.get('state') != 'completed' or operation.get('exit') != 65 or operation.get('cleanup_confirmed') is not True:
        raise ValueError('Ordinary UI invocation was not a completed cleanup-confirmed65')
    elapsed = operation.get('elapsed_seconds')
    if type(elapsed) not in {int, float} or not 0 < elapsed <= 575:
        raise ValueError('Missing bounded invocation duration')
    if (summary.get('result'), summary.get('totalTestCount'), summary.get('passedTests'), summary.get('failedTests'), summary.get('skippedTests'), summary.get('expectedFailures')) != ('Failed', 9, 8, 1, 0, 0):
        raise ValueError('Expected the complete9-case Pro summary with one retained failure')
    if any(type(summary.get(key)) is not int for key in ['totalTestCount', 'passedTests', 'failedTests', 'skippedTests', 'expectedFailures']):
        raise ValueError('Invalid finalized case counts')
    failures = summary.get('testFailures', [])
    if len(failures) != 1 or failures[0].get('targetName') != 'QRCatcherUITests' or failures[0].get('testIdentifierString') != 'QRCatcherUITests/testProductionCameraAllowThenResetAndDeny' or failures[0].get('failureText') != CAMERA_TIMEOUT:
        raise ValueError('Failure differs from the observed permission-flow case')
    devices = summary.get('devicesAndConfigurations', [])
    if len(devices) != 1 or devices[0].get('device', {}).get('deviceId') != device or devices[0]['device'].get('platform') != 'iOS Simulator':
        raise ValueError('Finalized result is not from the exact simulator')
    now = time.time() if now is None else now
    start, finish = summary.get('startTime'), summary.get('finishTime')
    if type(start) not in {int, float} or type(finish) not in {int, float} or not now - elapsed - 60 <= start < finish <= now + 5 or finish < now - 60:
        raise ValueError('Result is stale, incomplete or outside this invocation')


def current_products(source):
    if checked(['git', 'rev-parse', 'HEAD'], 5).strip() != source:
        raise ValueError('Source head changed')
    checked(['git', 'diff', '--exit-code', 'HEAD', '--'], 5)
    products = Path('build/iOS/Build/Products/Debug-iphonesimulator')
    metadata = {}
    for name, expected in [('QRCatcher.app', '100mango.QRCatcher'), ('QRCatcherUITests-Runner.app', '100mango.QRCatcherUITests.xctrunner')]:
        raw = read_regular(products / name / 'Info.plist', 256 * 1024)
        info = plistlib.loads(raw)
        if info.get('CFBundleIdentifier') != expected:
            raise ValueError('Built product identity mismatch')
        metadata[name] = {'bundle_id': expected, 'info_sha256': hashlib.sha256(raw).hexdigest()}
    return metadata


def admit(device, result, start):
    source = identity(device, result)
    first_budget = budget(start, 'setup-and-files')
    if not first_budget['admitted']:
        raise ValueError('Insufficient remaining step budget before verification')
    text = read_regular(Path(RESULT).with_suffix('.log'), 17 * 1024 * 1024).decode()
    records = [line.removeprefix('BOUNDED_COMMAND_END ') for line in text.splitlines() if line.startswith('BOUNDED_COMMAND_END ')]
    if len(records) != 1 or text.strip().splitlines()[-1] != 'BOUNDED_COMMAND_END ' + records[0] or '** TEST EXECUTE FAILED **' not in text:
        raise ValueError('Missing exact finalized command record')
    operation = json.loads(records[0])
    # Reject timeout/cleanup failures before any further public command.
    if operation.get('state') != 'completed' or operation.get('exit') != 65 or operation.get('cleanup_confirmed') is not True:
        raise ValueError('Ordinary command did not finish with confirmed cleanup')
    product_ids = current_products(source)
    summary = json.loads(checked(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', result], 15))
    validate_finalization(operation, summary, device)
    if blocked():
        raise RuntimeError('Owned cleanup barrier became unresolved')
    final_budget = budget(start, 'setup-and-files')
    return {'allowed': final_budget['admitted'], 'source': source, 'device': device, 'result': result,
            'original_layout_exit': 65, 'ordinary_tests': {'passed': 8, 'failed': 1, 'total': 9},
            'owned_process_cleanup_confirmed': True, 'capture_helper': 'none started by this phone-only route',
            'products': product_ids, 'step_started_monotonic': start, 'budget_checks': [final_budget],
            'provenance_limit': 'Fresh exact-SHA workflow build plus repeated clean source/product metadata checks; not compiled-binary attestation or release acceptance',
            'rule': 'Separate fresh import cases only; ordinary failure remains final-row failure; no rerun'}


def main(arguments):
    mode, device, result, raw_start = arguments
    start = float(raw_start)
    if blocked(): return 126
    if mode == 'admit':
        try: record = admit(device, result, start)
        except Exception as error:
            record = {'allowed': False, 'original_layout_exit': 65, 'reason': str(error)[:1800],
                      'budget_checks': [], 'imports': 'unexecuted'}
    else:
        try:
            source = identity(device, result)
            record = json.loads(read_regular(RECORD, 16 * 1024))
            if not record.get('allowed') or (record.get('source'), record.get('device'), record.get('result'), record.get('step_started_monotonic')) != (source, device, result, start):
                raise ValueError('No current continuation admission')
            check = budget(start, mode)
            if check['admitted']:
                if current_products(source) != record.get('products'):
                    raise ValueError('Built product metadata changed after admission')
                check = budget(start, mode)  # Identity checks consume real step time.
            record['budget_checks'].append(check)
            if not check['admitted']: record.update(allowed=False, imports='remaining cases unexecuted; insufficient step budget')
        except Exception as error:
            record = {'allowed': False, 'original_layout_exit': 65, 'reason': str(error)[:1800], 'imports': 'unexecuted'}
    write_json(RECORD, record, limit=16 * 1024)
    print('IOS_IMPORT_CONTINUATION ' + json.dumps(record), flush=True)
    if blocked(): return 126
    return 0 if record.get('allowed') else 65


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
