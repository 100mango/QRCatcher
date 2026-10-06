#!/usr/bin/env python3
"""Closed, unsigned original-iOS compilation/package prerequisite; no runtime GO.

900s = admission/controller slack20 + Debug390 + cleanup/dispatch10 +
Debug package20 + cleanup/dispatch10 + Release archive390 + cleanup/dispatch10 +
Release package20 + cleanup/dispatch10 + final receipt20. Every launch reserves
the complete remaining schedule; phases are never shortened or retried.
The original all-platform Debug cap180 becomes390 only in this closed iOS-first
redistribution, alongside a new Release prerequisite. This is not evidence that
the earlier compiler latency has been fixed. Completion must be clean and
observed strictly before cap+2, using the existing owned-process runner and uncertainty latch.
Only a timely clean package exit1 with a bound, safely complete owned-inventory
failure receipt may leave the independent Release archive/inspection phases
eligible. All original phase/full-schedule admission remains; any failure still
returns nonzero and prevents runtime. Build/unknown/timeout/unsafe scan stops.
"""
import hashlib
import json
import math
from pathlib import Path
import sys
import time

from atomic_json import write_json
import ios_original_release_route as route
from ios_import_continuation import read_regular
from owned_process_barrier import blocked, mark_unconfirmed
from watch_process import execute

TOTAL_SECONDS = 900
ADMISSION_SECONDS = 20
FINAL_SECONDS = 20
CLEANUP_SECONDS = 10
TIMELY_ALLOWANCE = 2
LOG_BYTES = 16 * 1024
REPORT_BYTES = 64 * 1024
ROOT = Path('build/ios-original-preflight')
DEBUG_APP = 'build/iOS/Build/Products/Debug-iphonesimulator/QRCatcher.app'
ARCHIVE = 'build/QRCatcher-iOS-Release.xcarchive'
PACKAGE_REPORTS = {'debug-package': 'build/ios-first-debug-package.json',
                   'release-package': 'build/ios-first-release-package.json'}
PHASES = (
    ('debug-build', 390, ['xcodebuild', 'build-for-testing', '-project', 'QRCatcher-iOS-Only.xcodeproj',
      '-scheme', 'QRCatcher', '-configuration', 'Debug', '-derivedDataPath', 'build/iOS',
      '-destination', 'generic/platform=iOS Simulator', '-jobs', '2', 'ARCHS=arm64',
      'CODE_SIGNING_ALLOWED=NO']),
    ('debug-package', 20, ['python3', 'scripts/ios_original_release_route.py', 'debug-package']),
    ('release-archive', 390, ['xcodebuild', 'archive', '-project', 'QRCatcher-iOS-Only.xcodeproj',
      '-scheme', 'QRCatcher', '-configuration', 'Release', '-derivedDataPath', 'build/iOS-Release',
      '-archivePath', ARCHIVE, '-destination', 'generic/platform=iOS', '-jobs', '2',
      'ARCHS=arm64', 'CODE_SIGNING_ALLOWED=NO']),
    ('release-package', 20, ['python3', 'scripts/verify_ios_only_release.py', ARCHIVE,
      '--platform', 'device', '--configuration', 'Release', '--output', PACKAGE_REPORTS['release-package']]),
)


def require(value, message):
    if not value:
        raise ValueError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def required_seconds(index):
    return sum(cap + CLEANUP_SECONDS for _, cap, _ in PHASES[index:]) + FINAL_SECONDS


def package_receipt(label):
    path = PACKAGE_REPORTS[label]
    raw = read_regular(path, REPORT_BYTES)
    value = json.loads(raw)
    debug = label == 'debug-package'
    require(type(value) is dict and value.get('status') == 'pass' and value.get('schema_version') == 1,
            'Missing successful strict package report')
    require(value.get('safe_inventory_complete') is True and value.get('findings') == []
            and value.get('findings_complete') is True and type(value.get('findings_omitted')) is int
            and value['findings_omitted'] == 0, 'Successful package must retain complete inventory and zero findings')
    require(value.get('configuration') == ('Debug' if debug else 'Release') and
            value.get('platform') == ('simulator' if debug else 'device') and
            value.get('bundle_id') == '100mango.QRCatcher' and value.get('device_families') == [1, 2] and
            value.get('package') == str(Path(DEBUG_APP if debug else ARCHIVE).absolute()) and
            value.get('app') == str(Path(DEBUG_APP if debug else ARCHIVE + '/Products/Applications/QRCatcher.app').absolute()),
            'Strict package report is outside this exact app/archive scope')
    require(value.get('scope') == ('ios-only-debug-hosted-test-package' if debug else 'ios-only-shipping-package'),
            'Wrong shipping/test package scope')
    hosted = value.get('hosted_tests')
    if debug:
        require(type(hosted) is dict and hosted.get('scope') == 'exact-xctestrun-bound-test-only-subtree',
                'Actual Debug hosted-test binding required')
    else:
        require('hosted_tests' in value and hosted is None, 'Release must admit zero XCTest exceptions')
    return {'path': path, 'sha256': hashlib.sha256(raw).hexdigest(), 'status': 'pass',
            'scope': value['scope'], 'configuration': value['configuration'], 'platform': value['platform']}


def rejected_package_receipt(label):
    """Closed safe diagnostic dependency; never a successful package proof."""
    path = PACKAGE_REPORTS[label]
    raw = read_regular(path, REPORT_BYTES)
    value = json.loads(raw)
    debug = label == 'debug-package'
    expected = Path(DEBUG_APP if debug else ARCHIVE).absolute()
    app = Path(DEBUG_APP if debug else ARCHIVE + '/Products/Applications/QRCatcher.app').absolute()
    require(type(value) is dict and value.get('schema_version') == 1 and value.get('status') == 'fail'
            and value.get('qualification') == 'unqualified' and value.get('safe_inventory_complete') is True,
            'Only complete safe owned-inventory rejection may continue independent Release diagnostics')
    require(value.get('configuration') == ('Debug' if debug else 'Release') and
            value.get('platform') == ('simulator' if debug else 'device') and
            value.get('package') == str(expected) and value.get('app') == str(app),
            'Rejected package receipt is outside this exact app/archive scope')
    findings = value.get('findings')
    require(type(findings) is list and 1 <= len(findings) <= 64 and
            all(type(item) is dict and set(item) == {'code', 'stage', 'scope'} and
                all(type(item[key]) is str and 0 < len(item[key]) <= (512 if key == 'scope' else 64)
                    for key in ('code', 'stage', 'scope')) for item in findings),
            'Bounded closed rejected-package findings required')
    require(type(value.get('findings_complete')) is bool and type(value.get('findings_omitted')) is int
            and 0 <= value['findings_omitted'] and (not value['findings_complete'] or value['findings_omitted'] == 0)
            and value.get('reason') == findings[0]['code'],
            'Rejected package findings binding is invalid')
    return {'path': path, 'sha256': hashlib.sha256(raw).hexdigest(), 'status': 'fail',
            'qualification': 'unqualified', 'safe_inventory_complete': True,
            'configuration': value['configuration'], 'platform': value['platform'],
            'reason': value['reason'], 'findings_count': len(findings),
            'findings_complete': value['findings_complete'], 'findings_omitted': value['findings_omitted']}


def main():
    started = time.monotonic()
    build = Path('build')
    build.mkdir(exist_ok=True)
    require(build.is_dir() and not build.is_symlink() and build.resolve() == Path.cwd() / build,
            'Original iOS preflight requires this checkout build directory')
    require(not ROOT.exists() and not ROOT.is_symlink(), 'Original iOS preflight cannot be retried')
    ROOT.mkdir()
    report = {'version': 1, 'scope': 'closed original-iOS unsigned compilation and package inspection only',
              'runtime_tests_executed': 0, 'release_qualification': False, 'passed': False,
              'total_seconds': TOTAL_SECONDS, 'admission_slack_seconds': ADMISSION_SECONDS,
              'final_receipt_reserve_seconds': FINAL_SECONDS, 'cleanup_dispatch_reserve_per_phase_seconds': CLEANUP_SECONDS,
              'timely_postreturn_allowance_seconds': TIMELY_ALLOWANCE,
              'previous_all_platform_debug_cap_seconds': 180,
              'phase_caps_seconds': {name: cap for name, cap, _ in PHASES}, 'operations': [], 'package_reports': {},
              'rejected_package_phases': []}

    def save():
        write_json(ROOT / 'summary.json', report, limit=REPORT_BYTES)

    def uncertain(state, operation=None):
        report['cleanup_unconfirmed'] = True
        mark_unconfirmed({'state': state, 'exit': 126, 'cleanup_confirmed': False})
        if operation is not None:
            operation['state'] = state
        save()
        return 126

    try:
        identity = route.current_identity()
        require(identity.get('job') == 'preflight' and identity.get('scope') == '' and
                identity.get('project') == 'QRCatcher-iOS-Only.xcodeproj' and identity.get('scheme') == 'QRCatcher',
                'Only the exact original-iOS preflight job may compile')
        report['identity'] = identity
        for path in ('build/iOS', 'build/iOS-Release', ARCHIVE, *PACKAGE_REPORTS.values()):
            require(not Path(path).exists() and not Path(path).is_symlink(), 'Preflight output already exists: ' + path)
        save()
        for index, (label, cap, command) in enumerate(PHASES):
            require(route.current_identity() == identity, 'Original-iOS source/workflow identity changed')
            if blocked():
                report['operations'].append({'label': label, 'state': 'blocked_owned_process_cleanup_unconfirmed'})
                return uncertain('blocked_owned_process_cleanup_unconfirmed')
            now = time.monotonic()
            if not finite(started) or not finite(now) or now < started:
                report['operations'].append({'label': label, 'state': 'unknown_preflight_clock'})
                return uncertain('unknown_preflight_clock')
            remaining = TOTAL_SECONDS - (now - started)
            required = required_seconds(index)
            if remaining < required:
                report['operations'].append({'label': label, 'state': 'not_run_total_preflight_schedule',
                                             'remaining_seconds': round(remaining, 3), 'required_seconds': required})
                save()
                return 124
            phase_started = time.monotonic()
            if not finite(phase_started) or phase_started < now:
                report['operations'].append({'label': label, 'state': 'unknown_preflight_clock'})
                return uncertain('unknown_preflight_clock')
            if TOTAL_SECONDS - (phase_started - started) < required:
                report['operations'].append({'label': label, 'state': 'not_run_total_preflight_schedule',
                                             'remaining_seconds': round(TOTAL_SECONDS - (phase_started - started), 3),
                                             'required_seconds': required})
                save()
                return 124
            print('IOS_ORIGINAL_PREFLIGHT_START ' + json.dumps({'label': label, 'command': command}), flush=True)
            try:
                code, tail, operation = execute(command, cap, output_limit=16 * 1024 * 1024, tail_limit=LOG_BYTES)
                phase_ended = time.monotonic()
            except Exception as error:
                report['operations'].append({'label': label, 'state': 'command_completion_unknown', 'detail': str(error)[:400]})
                return uncertain('command_completion_unknown')
            if type(tail) is not str or type(operation) is not dict:
                report['operations'].append({'label': label, 'state': 'command_completion_unknown'})
                return uncertain('command_completion_unknown')
            (ROOT / (label + '.log')).write_bytes(tail.encode('utf-8')[-LOG_BYTES:].decode('utf-8', errors='ignore').encode('utf-8'))
            elapsed = operation.get('elapsed_seconds')
            # Retain only bounded runner fields. Nonfinite/foreign metadata
            # must still produce a valid failure receipt and durable latch.
            state = operation.get('state')
            row = {'label': label, 'command': command, 'timeout_seconds': cap,
                   'state': state[:120] if type(state) is str else 'unknown',
                   'exit': code if type(code) is int else None,
                   'reported_exit': operation.get('exit') if type(operation.get('exit')) is int else None,
                   'cleanup_confirmed': operation.get('cleanup_confirmed') is True,
                   'elapsed_seconds': elapsed if finite(elapsed) else None,
                   'output_bytes': operation.get('output_bytes') if type(operation.get('output_bytes')) is int else None}
            report['operations'].append(row)
            clean = (type(code) is int and type(operation.get('exit')) is int and code == operation['exit'] and
                     code not in (124, 125, 126) and operation.get('state') == 'completed' and
                     operation.get('command') == command and type(operation.get('timeout_seconds')) is int and operation['timeout_seconds'] == cap and
                     operation.get('cleanup_confirmed') is True and finite(elapsed) and 0 <= elapsed < cap + TIMELY_ALLOWANCE and
                     finite(phase_started) and finite(phase_ended) and phase_started <= phase_ended < phase_started + cap + TIMELY_ALLOWANCE)
            if not clean:
                return uncertain('command_completion_unconfirmed', row)
            save()
            print('IOS_ORIGINAL_PREFLIGHT_END ' + json.dumps(row), flush=True)
            if code != 0:
                if code == 1 and label in PACKAGE_REPORTS:
                    receipt = rejected_package_receipt(label)
                    report['package_reports'][label] = receipt
                    report['rejected_package_phases'].append(label)
                    save()
                    continue
                return code
            if label in PACKAGE_REPORTS:
                report['package_reports'][label] = package_receipt(label)
                save()
        require(route.current_identity() == identity, 'Original-iOS final source/workflow identity changed')
        ended = time.monotonic()
        require(finite(ended) and started <= ended <= started + TOTAL_SECONDS - FINAL_SECONDS,
                'Preflight final receipt reserve exhausted')
        report['elapsed_seconds'] = round(ended - started, 3)
        report['passed'] = not report['rejected_package_phases']
        save()
        print(json.dumps(report), flush=True)
        return 0 if report['passed'] else 1
    except (OSError, ValueError, TypeError) as error:
        report['failure'] = str(error)[:400]
        save()
        return 1


if __name__ == '__main__':
    if sys.argv[1:]:
        raise SystemExit('Closed original-iOS preflight accepts no arguments')
    raise SystemExit(main())
