#!/usr/bin/env python3
"""Execute one explicitly selected existing Vision case on this fresh matrix VM."""
import json, os, subprocess, sys
from pathlib import Path
from watch_process import execute
from atomic_json import write_json
from owned_process_barrier import blocked, mark_unconfirmed
from run_native_size_case import run_case
from owned_process_group import stop_group
from vision_case_contract import select_case, case_identity


def main():
    if blocked(): raise SystemExit(126)
    if len(sys.argv) != 3:
        raise ValueError('Expected exact device UUID and one Vision case scope')
    udid, scope = sys.argv[1:]
    case = select_case(scope)
    identity = case_identity(case, os.environ['GITHUB_SHA'], udid)
    if os.environ.get('EVIDENCE_SCOPE') != scope:
        raise ValueError('Matrix evidence scope must match the selected case')
    out = Path('build/vision-runtime'); out.mkdir(parents=True, exist_ok=True)
    marker = out / 'ui-completed.marker'
    if (out / 'ui-cases.json').exists() or marker.exists():
        raise ValueError('A Vision case already ran on this VM; automatic retry forbidden')
    if any(Path(item).exists() for item in ['VisionUIResults.xcresult', 'VisionPhotosUIResults.xcresult',
                                          'VisionFilesUIResults.xcresult', 'VisionChineseUIResults.xcresult',
                                          'VisionLargestUIResults.xcresult']):
        raise ValueError('Unexpected pre-existing Vision UI result on fresh VM')
    report = dict(identity, cases=[])
    row = dict(identity, state='starting')
    report['cases'].append(row); write_json(out / 'ui-cases.json', report)
    common = ['xcodebuild', 'test-without-building', '-project', 'QRCatcher.xcodeproj',
              '-scheme', 'QRCatcherVision', '-configuration', 'Debug', '-derivedDataPath', 'build/VisionTests',
              '-destination', 'platform=visionOS Simulator,id=' + udid, '-parallel-testing-enabled', 'NO',
              '-collect-test-diagnostics', 'never', '-test-timeouts-enabled', 'YES',
              '-default-test-execution-time-allowance', str(case.default_seconds),
              '-maximum-test-execution-time-allowance', str(case.maximum_seconds), 'CODE_SIGNING_ALLOWED=NO']
    failed = False
    with (out / 'checkpoint-capture.log').open('w') as output:
        capture = subprocess.Popen(['python3', '-u', 'scripts/capture_vision_checkpoints.py',
                                    udid, 'vision-ui-test.log', scope],
                                   stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            cleanup, _, cleanup_info = execute(['xcrun', 'simctl', 'terminate', udid, '100mango.QRCatcher'], 30)
            row['pre_case_app_termination'] = cleanup_info
            if cleanup == 126 or cleanup_info.get('cleanup_confirmed') is not True:
                row['state'] = 'blocked_owned_process_cleanup_unconfirmed'
                report['cleanup_unconfirmed'] = True
                mark_unconfirmed(cleanup_info); failed = True
            else:
                print('VISION_CASE_START ' + json.dumps(row), flush=True)
                if scope == 'visionos_largest':
                    code, size_report = run_case('vision', udid)
                    report['system_text_size_ui_exit'] = code
                    report['largest_text_ui'] = size_report['status']
                    row.update(state='finished', exit=code, system_text_size=size_report)
                    if code == 126 or size_report.get('cleanup_unconfirmed'):
                        report['cleanup_unconfirmed'] = True
                else:
                    code, tail, operation = execute(common + [
                        '-only-testing:QRCatcherVisionUITests/QRCatcherVisionUITests/' + case.name,
                        '-resultBundlePath', case.result], case.seconds)
                    (out / (case.label + '-ui-tail.log')).write_text(tail[-16 * 1024:])
                    row.update(state='finished', exit=code, operation=operation)
                    if code == 126 or operation.get('cleanup_confirmed') is not True:
                        report['cleanup_unconfirmed'] = True; mark_unconfirmed(operation)
                failed = code != 0 or bool(report.get('cleanup_unconfirmed'))
                print('VISION_CASE_END ' + json.dumps(row), flush=True)
            write_json(out / 'ui-cases.json', report)
        finally:
            marker.touch()
            try: capture_exit = capture.wait(timeout=30)
            except subprocess.TimeoutExpired: capture_exit = 124
            capture_clean = stop_group(capture)
            report['capture_cleanup_confirmed'] = capture_clean
            if not capture_clean:
                report['cleanup_unconfirmed'] = True
                mark_unconfirmed({'state': 'capture_cleanup_unconfirmed', 'exit': 126, 'cleanup_confirmed': False})
                failed = True
            report['capture_process_exit'] = capture_exit
            write_json(out / 'ui-cases.json', report)
            failed |= capture_exit != 0
    if failed:
        raise SystemExit('Selected Vision UI/capture gate failed; no case is retried on this VM')


if __name__ == '__main__':
    main()
