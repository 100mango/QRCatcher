#!/usr/bin/env python3
"""Retain one closed Vision case's actual pixels, receipts and bounded diagnostics.

Missing or invalid success evidence leaves a red gate and qualified=false. Failure
pixels are diagnostic only. They never stand in for a required held checkpoint.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import uuid

from vision_case_contract import CASES, case_identity, require_identity, select_case
from validate_evidence_budget import inspect

ICON = Path('QRCatcherVision/Assets.xcassets/AppIcon.solidimagestack/Back.solidimagestacklayer/Content.imageset/Icon.png')


def bounded_file(path, limit):
    path = Path(path)
    if path.resolve(strict=True) != path.absolute():
        raise ValueError('Evidence path traverses a symlink or alias: ' + path.name)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= limit:
            raise ValueError('Expected independent bounded evidence file: ' + path.name)
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            data = stream.read(limit + 1)
        after = os.fstat(descriptor); current = path.lstat()
        signature = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
                                   value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if len(data) != info.st_size or signature(info) != signature(after) or signature(after) != signature(current):
            raise ValueError('Evidence file changed during read: ' + path.name)
        return data
    finally:
        os.close(descriptor)


def bounded_json(path, limit=64 * 1024):
    return json.loads(bounded_file(path, limit))


def result_case_nodes(value):
    if isinstance(value, dict):
        if value.get('nodeType') == 'Test Case':
            yield value
        for child in value.values():
            yield from result_case_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from result_case_nodes(child)


def validate_result(summary, tests, case, device, hosted=False):
    count = 11 if hosted else 1
    expected = {'totalTestCount': count, 'passedTests': count, 'failedTests': 0,
                'skippedTests': 0, 'expectedFailures': 0, 'result': 'Passed'}
    if not isinstance(summary, dict) or any(summary.get(k) != v or
            (type(v) is int and type(summary.get(k)) is not int) for k, v in expected.items()):
        raise ValueError('Selected XCTest result did not pass all required existing tests')
    configurations = summary.get('devicesAndConfigurations')
    if not isinstance(configurations, list) or len(configurations) != 1:
        raise ValueError('Expected exactly one result device/configuration')
    actual = configurations[0].get('device', {})
    if actual.get('deviceId') != device or actual.get('platform') != 'visionOS Simulator':
        raise ValueError('Selected XCTest result device mismatch')
    if hosted:
        return
    rows = list(result_case_nodes(tests))
    if len(rows) != 1 or rows[0].get('name') != case.name + '()' or rows[0].get('result') != 'Passed':
        raise ValueError('Result bundle did not contain exactly the selected existing UI case')
    identifier = rows[0].get('nodeIdentifier')
    if identifier not in {'QRCatcherVisionUITests/' + case.name + '()',
                          'QRCatcherVisionUITests/' + case.name}:
        raise ValueError('Selected XCTest result case identity mismatch')
    expected_url = 'test://com.apple.xcode/QRCatcher/QRCatcherVisionUITests/QRCatcherVisionUITests/' + case.name
    if rows[0].get('nodeIdentifierURL') != expected_url:
        raise ValueError('Selected XCTest result target-qualified URL identity mismatch')


def validate_frames(case, expected, bindings, rows, runtime, require_complete=True):
    if not isinstance(bindings, list) or len(bindings) != 1:
        raise ValueError('Expected exactly one runner lease on this VM')
    binding = bindings[0]; require_identity(binding, expected)
    if binding.get('success') is not True:
        raise ValueError('Current selected-case runner was not bound')
    lease = binding.get('lease')
    if not isinstance(lease, str) or str(uuid.UUID(lease)).upper() != lease or binding.get('runner') != '100mango.QRCatcherVisionUITests.xctrunner' or type(binding.get('pid')) is not int or binding['pid'] <= 0:
        raise ValueError('Invalid selected-case runner lease/PID')
    if binding.get('exports') is not case.hosted_tests:
        raise ValueError('Runner export scope differs from selected case')
    if not isinstance(rows, list):
        raise ValueError('Checkpoint receipt list missing')
    allowed = set(case.frames) | {'vision-failure'}
    found = set(); retained = []
    for row in rows:
        require_identity(row, expected)
        name = row.get('checkpoint')
        if name not in allowed or name in found:
            raise ValueError('Unknown, duplicate or cross-case checkpoint')
        found.add(name)
        for key in ['lease', 'runner', 'pid']:
            if row.get(key) != binding.get(key):
                raise ValueError('Checkpoint does not match the sole current runner lease')
        if row.get('success') is not True or row.get('pixels_retained') is not True or row.get('screenshot_exit') != 0:
            raise ValueError('Held checkpoint did not complete successfully')
        filename = row.get('file')
        if filename != name + '.jpg':
            raise ValueError('Unexpected selected-case checkpoint filename')
        data = bounded_file(runtime / filename, 800 * 1024)
        if not data.startswith(b'\xff\xd8') or len(data) != row.get('bytes') or hashlib.sha256(data).hexdigest() != row.get('sha256'):
            raise ValueError('Checkpoint frame bytes/hash mismatch')
        if name.startswith('vision-exported-'):
            kind = 'png' if name == 'vision-exported-qr' else 'json'
            exported = bounded_file(runtime / ('actual-export.' + kind), 128 * 1024 - 1)
            receipt = row.get('actual_export_readback', {})
            store = receipt.get('test_store')
            if not isinstance(store, str) or str(uuid.UUID(store)).upper() != store:
                raise ValueError('Export receipt lacks exact test-store UUID')
            if receipt.get('type') != kind or receipt.get('bytes') != len(exported) or receipt.get('sha256') != hashlib.sha256(exported).hexdigest():
                raise ValueError('Actual export bytes do not match the held checkpoint receipt')
        retained.append((filename, data))
    if require_complete and not set(case.frames).issubset(found):
        raise ValueError('Required success checkpoints missing: ' + ','.join(sorted(set(case.frames) - found)))
    return retained


def validate_host_failure(expected, bindings, row, runtime):
    require_identity(row, expected)
    if not isinstance(bindings, list) or len(bindings) != 1:
        raise ValueError('Host failure pixels require the sole current lease')
    require_identity(bindings[0], expected)
    if bindings[0].get('success') is not True or any(row.get(key) != bindings[0].get(key) for key in ['lease', 'runner', 'pid']):
        raise ValueError('Host failure diagnostic differs from selected runner lease')
    if row.get('diagnostic_only') is not True or row.get('success') is not False:
        raise ValueError('Host failure frame must never be success evidence')
    if row.get('pixels_retained') is not True:
        return None
    if row.get('file') != 'vision-host-failure.jpg':
        raise ValueError('Unexpected host failure diagnostic filename')
    data = bounded_file(runtime / row['file'], 800 * 1024)
    if not data.startswith(b'\xff\xd8') or len(data) != row.get('bytes') or hashlib.sha256(data).hexdigest() != row.get('sha256'):
        raise ValueError('Host failure diagnostic pixels/hash mismatch')
    return data


def command_json(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    if len(result.stdout.encode()) > 128 * 1024:
        raise ValueError('XCTest structured summary exceeded bounded allocation')
    return json.loads(result.stdout)


def export(scope):
    case = select_case(scope)
    if os.environ.get('EVIDENCE_SCOPE') != scope:
        raise ValueError('Export scope differs from fresh matrix case')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    if commit != os.environ['GITHUB_SHA']:
        raise ValueError('Export checkout differs from tested source')
    out = Path('build/ios-platform-evidence')
    if out.exists() and any(out.iterdir()):
        raise ValueError('Fresh-case evidence destination is not empty')
    out.mkdir(parents=True, exist_ok=True)
    runtime = Path('build/vision-runtime')
    summary = {'scope': scope, 'case': case.name, 'result': case.result, 'source_commit': commit,
               'source_tree': tree, 'run_id': os.environ.get('GITHUB_RUN_ID'), 'qualified': False,
               'scope_limit_bytes': case.evidence_bytes, 'required_frames': list(case.frames),
               'diagnostic_failure_images_are_success_evidence': False, 'errors': [], 'files': []}

    def retain(path, name=None, cap=64 * 1024, tail=False):
        if not path.exists():
            return
        if tail:
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                raise ValueError('Unexpected diagnostic log type')
            with path.open('rb') as stream:
                stream.seek(0, 2); stream.seek(max(0, stream.tell() - cap)); data = stream.read(cap)
        else:
            data = bounded_file(path, cap)
        if path.suffix == '.json':
            json.loads(data)
        target = name or path.name
        if Path(target).name != target or (out / target).exists():
            raise ValueError('Duplicate or escaped evidence filename')
        (out / target).write_bytes(data)
        summary['files'].append({'name': target, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})

    from owned_process_barrier import blocked
    if blocked():
        summary['errors'].append('Owned-process cleanup remains unconfirmed')
    pending = Path('build/vision-command-inflight.json')
    if pending.exists() or pending.is_symlink():
        summary['errors'].append('Vision command bootstrap or cleanup remains unconfirmed')
        try: retain(pending, cap=1024)
        except (OSError, ValueError) as error: summary['errors'].append(str(error))

    fixture_pending = Path('build/fixture-query-inflight.json')
    if fixture_pending.exists() or fixture_pending.is_symlink():
        summary['errors'].append('Fixture container query completion remains unconfirmed')
        try: retain(fixture_pending, cap=2048)
        except (OSError, ValueError) as error: summary['errors'].append(str(error))

    # Retain each row's own compact diagnostics once. No raw xcresult or broad
    # runtime directory copying; known result/frame identities are checked below.
    diagnostic_json = ['runtime.json', 'optional-simulator.json', 'ui-cases.json', 'runner-bindings.json',
                       'checkpoint-captures.json', 'host-failure-capture.json', 'realitywidgets-crash-summary.json',
                       'fenced-install.json', 'fenced-shutdown.json']
    if scope == 'visionos_largest': diagnostic_json.append('system-content-size.json')
    for name in diagnostic_json:
        try: retain(runtime / name, 'vision-' + name, cap=16 * 1024 if name.startswith('fenced-') else 64 * 1024)
        except (OSError, ValueError) as error: summary['errors'].append(str(error))
    logs = [(Path('vision-test-build.log'), 16 * 1024), (Path('vision-ui-test.log'), 16 * 1024),
            (runtime / 'checkpoint-capture.log', 8 * 1024), (runtime / 'boot.log', 8 * 1024),
            (runtime / 'bootstatus.log', 8 * 1024), (runtime / (case.label + '-ui-tail.log'), 16 * 1024)]
    if case.hosted_tests: logs.append((Path('vision-test.log'), 16 * 1024))
    if case.release_package: logs.append((Path('release-vision.log'), 16 * 1024))
    for path, cap in logs:
        try: retain(path, cap=cap, tail=True)
        except (OSError, ValueError) as error: summary['errors'].append(str(error))
    try:
        expected = case_identity(case, commit, os.environ['VISION_SIMULATOR_ID'])
        summary.update(expected)
        for other in CASES:
            if other != case and Path(other.result).exists():
                raise ValueError('Unexpected other-case Vision result on this VM')
        if Path('VisionUIResults.xcresult').exists() or (not case.hosted_tests and Path('VisionTestResults.xcresult').exists()):
            raise ValueError('Unexpected combined or duplicate hosted Vision result')
        bindings = bounded_json(runtime / 'runner-bindings.json')
        failure_path = runtime / 'host-failure-capture.json'
        if failure_path.exists():
            summary['errors'].append('Selected XCTest failure event was recorded; host pixels are diagnostic only')
            try:
                failure = bounded_json(failure_path)
                if validate_host_failure(expected, bindings, failure, runtime) is not None:
                    retain(runtime / 'vision-host-failure.jpg', cap=800 * 1024)
                    summary['host_failure_diagnostic_retained'] = True
            except (OSError, ValueError) as error: summary['errors'].append(str(error))
        rows = bounded_json(runtime / 'checkpoint-captures.json')
        if not isinstance(rows, list): raise ValueError('Expected checkpoint receipt list')
        # Preserve individually valid partial checkpoints even when a later
        # assertion failed. Their presence cannot qualify an incomplete case.
        for row in rows:
            try:
                validate_frames(case, expected, bindings, [row], runtime, require_complete=False)
                retain(runtime / row['file'], 'vision-' + row['file'], cap=800 * 1024)
                if row.get('checkpoint') in {'vision-exported-qr', 'vision-exported-history'}:
                    kind = 'png' if row['checkpoint'] == 'vision-exported-qr' else 'json'
                    retain(runtime / ('actual-export.' + kind), cap=128 * 1024 - 1)
            except (OSError, ValueError) as error: summary['errors'].append(str(error))
        report = bounded_json(runtime / 'ui-cases.json'); require_identity(report, expected)
        if not isinstance(report.get('cases'), list) or len(report['cases']) != 1:
            raise ValueError('Expected exactly one attempted existing case')
        require_identity(report['cases'][0], expected)
        if report['cases'][0].get('state') != 'finished' or report['cases'][0].get('exit') != 0:
            raise ValueError('Selected case did not finish successfully')
        if report.get('cleanup_unconfirmed') or report.get('capture_cleanup_confirmed') is not True or report.get('capture_process_exit') != 0:
            raise ValueError('Selected case capture/cleanup did not finish successfully')
        validate_frames(case, expected, bindings, rows, runtime)
        if not case.hosted_tests and any(runtime.glob('actual-export.*')):
            raise ValueError('Unexpected cross-case exported output')
        if scope == 'visionos_largest':
            size = bounded_json(runtime / 'system-content-size.json')
            if size.get('status') != 'largest_ui_passed' or size.get('restore_verified') is not True or size.get('cleanup_unconfirmed'):
                raise ValueError('Actual largest system category and restoration were not verified')
        for result, hosted in [(case.result, False)] + ([('VisionTestResults.xcresult', True)] if case.hosted_tests else []):
            if not Path(result, 'Info.plist').is_file():
                raise ValueError('Required exact result bundle missing: ' + result)
            result_summary = command_json(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', result])
            tests = None if hosted else command_json(['xcrun', 'xcresulttool', 'get', 'test-results', 'tests', '--path', result])
            summary.setdefault('results', {})[result] = {'summary': result_summary, 'tests': tests}
            validate_result(result_summary, tests, case, expected['device'], hosted)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        summary['errors'].append(str(error))
    if case.release_package:
        try:
            retain(ICON, 'vision-retained-icon-source.png', cap=800 * 1024)
            retain(Path('build/native-release-evidence/vision-release.json'))
            retain(Path('build/import-fixture/fixture.json'), 'owned-import-fixture.json', cap=4096)
            if not (out / 'vision-retained-icon-source.png').exists() or not (out / 'vision-release.json').exists() or not (out / 'owned-import-fixture.json').exists():
                raise ValueError('Required Files Release/source-icon/fixture evidence missing')
        except (OSError, ValueError) as error: summary['errors'].append(str(error))
    summary['qualified'] = not summary['errors']
    encoded = (json.dumps(summary, indent=2) + '\n').encode()
    if len(encoded) > 64 * 1024:
        raise ValueError('Case manifest exceeded bounded metadata cap')
    (out / 'manifest.json').write_bytes(encoded)
    try:
        inspect(out, limit=case.evidence_bytes)
    except (OSError, ValueError) as error:
        summary['qualified'] = False
        summary['errors'].append(str(error))
        (out / 'manifest.json').write_text(json.dumps(summary, indent=2) + '\n')
        raise
    print(json.dumps({'scope': scope, 'qualified': summary['qualified'], 'errors': summary['errors']}), flush=True)
    if not summary['qualified']:
        raise SystemExit('Required case-bound Vision evidence is incomplete; retained diagnostics do not qualify success')
    return summary


if __name__ == '__main__':
    if len(sys.argv) != 2: raise SystemExit('Expected exactly one closed Vision scope')
    export(sys.argv[1])
