#!/usr/bin/env python3
"""Closed original-iOS missing-case route; reuse the reviewed executors."""
import os
import json
import math
from pathlib import Path
import re
import sys
import time
import ios_original_release_route as original

BRANCH = 'codex/ios-original-supplement'
REF = 'refs/heads/' + BRANCH
WORKFLOW = Path('.github/workflows/ios-original-supplement.yml')
WORKFLOW_REF = '100mango/QRCatcher/.github/workflows/ios-original-supplement.yml@' + REF
SCOPES = original.SCOPES
PHONE_SCOPES = ('iphone_pro', 'iphone_se3')
PROJECT = original.PROJECT
SCHEME = original.SCHEME
PHONE_CHECKS = (
    'QRCatcherUITests/QRCatcherUITests/testDeniedCameraAndEmptyHistory',
    'QRCatcherUITests/QRCatcherImageImportUITests/testRealPickerWarmupAndCancelPreservesPreviousSelection',
)
FILES = 'QRCatcherUITests/QRCatcherImageImportUITests/testRealFilesImportAndReopen'
PHONE_PHOTOS = 'QRCatcherUITests/QRCatcherImageImportUITests/testRealPhotosImportAndReopen'
PAD_PHOTOS = 'QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords'
MINI_WARMUP = PHONE_CHECKS[1]
PRIOR_SOURCE = 'dfb0dd0d8d3bd67b554950dec8aa4ee4d51031f1'
PRIOR_TREE = '6890389c8ffc97ab9d5a86020982050474720494'
PRIOR_RUN = '37478641479'

# Only the first public result reader in each fresh selected VM gets30s.
# Every admission remains inside its existing native phase, never a new clock.
SUMMARY_PHASE_SECONDS = {'iphone_pro': 1200, 'iphone_se3': 1320, 'ipad_pro': 1080}
SUMMARY_POST_RETURN_SECONDS = 2
SUMMARY_CLEANUP_SECONDS = 20
SUMMARY_CAPS = {
    'iphone_pro': {'iOSUnitResults.xcresult': 30, 'PhoneUIResults.xcresult': 10,
                   'PhoneUIResults-files.xcresult': 10, 'PhoneUIResults-imports.xcresult': 10},
    'iphone_se3': {'CompactPhoneUIResults.xcresult': 30, 'CompactPhoneUIResults-files.xcresult': 10,
                   'CompactPhoneUIResults-imports.xcresult': 10},
    'ipad_pro': {'PadUIResults-layout.xcresult': 30, 'PadUIResults-files.xcresult': 10,
                 'PadUIResults.xcresult': 10},
}

def summary_admission(scope, result, started, now=None):
    original.require(scope in SUMMARY_CAPS and result in SUMMARY_CAPS[scope], 'Closed supplemental summary profile required')
    now = time.monotonic() if now is None else now
    original.require(type(started) in (int,float) and type(now) in (int,float) and
        math.isfinite(started) and math.isfinite(now) and 0 < started <= now, 'Invalid original native phase clock')
    cap = SUMMARY_CAPS[scope][result]
    phase_seconds = 900 if result == 'iOSUnitResults.xcresult' else SUMMARY_PHASE_SECONDS[scope]
    required = cap + SUMMARY_POST_RETURN_SECONDS + SUMMARY_CLEANUP_SECONDS
    deadline = started + phase_seconds
    original.require(now + required <= deadline, 'Full summary and cleanup reserve unavailable inside original native phase')
    return {'phase_started_monotonic': started, 'phase_deadline_monotonic': deadline,
            'phase_seconds': phase_seconds, 'summary_seconds': cap,
            'post_return_seconds': SUMMARY_POST_RETURN_SECONDS, 'cleanup_reserve_seconds': SUMMARY_CLEANUP_SECONDS,
            'required_seconds': required, 'remaining_seconds': round(deadline-now,3)}

def render_legacy_workflow(canonical):
    """Exact four-scope compatibility profile for existing component fixtures."""
    body = original.render_workflow(canonical)
    body = original.replace_once(body,
        'name: Original iPhone and iPad release qualification\n',
        'name: Original iOS targeted supplemental diagnostics\n')
    body = original.replace_once(body,
        "  IOS_FIRST_RELEASE_CANDIDATE_ONLY: 'true'\n",
        "  IOS_FIRST_RELEASE_CANDIDATE_ONLY: 'true'\n  QRCATCHER_IOS_SUPPLEMENT_ONLY: 'true'\n")
    body = body.replace(original.REF, REF).replace(original.WORKFLOW_REF, WORKFLOW_REF)
    body = body.replace('100mango/QRCatcher/.github/workflows/ios-original-release.yml@',
                        '100mango/QRCatcher/.github/workflows/ios-original-supplement.yml@')
    body = body.replace(' · original iOS qualification', ' · missing-case diagnostics')
    body = original.replace_once(body,
        '        name: qrcatcher-ios-original-${{ matrix.scope }}-evidence\n',
        '        name: qrcatcher-ios-supplement-${{ matrix.scope }}-evidence\n')
    body = original.replace_once(body,
        '        name: qrcatcher-ios-original-package-evidence\n',
        '        name: qrcatcher-ios-supplement-package-evidence\n')
    body = original.replace_once(body, '    - ' + original.BRANCH + '\n', '    - ' + BRANCH + '\n')
    body = original.replace_once(body,
        "        echo 'Original iPhone/iPad qualification requires this exact isolated app/archive and all selected iOS cases. Physical camera capture, denial and recovery remain device checks; signing/submission are separate. Deferred platform results are reported separately.' >> \"$GITHUB_STEP_SUMMARY\"\n",
        "        echo 'This diagnostic runs only declared missing cases. Historical components keep their original source/run/attempt; no original full-row or release pass is claimed. Physical camera, signing and submission remain separate.' >> \"$GITHUB_STEP_SUMMARY\"\n")
    unit_line = next(line+'\n' for line in body.splitlines()
                     if 'scripts/run_bounded.py 855 xcodebuild' in line)
    hosted_prefix = ('      timeout-minutes: 15\n      run: |\n'
                     '        python3 scripts/owned_process_barrier.py --check\n')
    body = original.replace_once(body, hosted_prefix,
        '      timeout-minutes: 15\n      run: |\n'
        '        HOSTED_STARTED=$(python3 -c \'import time;print(time.monotonic())\')\n'
        '        python3 scripts/owned_process_barrier.py --check\n')
    body = original.replace_once(body, unit_line,
        '        set +e\n' + unit_line +
        '        UNIT_EXIT=${PIPESTATUS[0]}\n        set -e\n' +
        '        python3 scripts/ios_original_supplement_route.py retain-hosted "$SIMULATOR_ID" "$UNIT_EXIT" "$HOSTED_STARTED"\n' +
        '        exit "$UNIT_EXIT"\n')
    summary_loop = next(line+'\n' for line in body.splitlines() if line.startswith('        for RESULT in '))
    summary_loop += ('          if [ -f "$RESULT/Info.plist" ]; then xcrun xcresulttool get test-results summary --path "$RESULT"; fi\n'
                     '        done\n')
    body = original.replace_once(body, summary_loop,
        '        python3 scripts/ios_original_supplement_route.py summary-retained\n')
    return body

def render_workflow(canonical):
    """The current completion cohort is exactly the two unfinished phones."""
    body = render_legacy_workflow(canonical)
    body = original.replace_once(body, "  QRCATCHER_IOS_SUPPLEMENT_ONLY: 'true'\n",
        "  QRCATCHER_IOS_SUPPLEMENT_ONLY: 'true'\n  PHONE_COMPLETION_ONLY: 'true'\n")
    body = original.replace_once(body,
        '        scope:\n        - iphone_pro\n        - iphone_se3\n        - ipad_pro\n        - ipad_mini\n',
        '        scope:\n        - iphone_pro\n        - iphone_se3\n')
    return body

def selected_cases(scope):
    if scope in ('iphone_pro', 'iphone_se3'):
        return list(PHONE_CHECKS) + [FILES, PHONE_PHOTOS]
    if scope == 'ipad_pro':
        return ['QRCatcherUITests/QRCatcherPadUITests/testLargeTextImportCancellationAndPrivacyReturn',
                'QRCatcherUITests/QRCatcherPadUITests/testSplitSelectionRotationAndAnchoredShare',
                FILES, PAD_PHOTOS]
    if scope == 'ipad_mini':
        return [MINI_WARMUP, PAD_PHOTOS]
    original.require(scope == '', 'Unknown fixed supplementary scope')
    return []

def current_identity():
    canonical = original.read_regular(original.CANONICAL, 128*1024).decode()
    workflow = original.read_regular(WORKFLOW, 128*1024).decode()
    phone_completion = workflow == render_workflow(canonical)
    if phone_completion:
        original.require(os.environ.get('PHONE_COMPLETION_ONLY')=='true', 'Exact phone completion flag required')
        selected_scopes = PHONE_SCOPES
    else:
        original.require(workflow == render_legacy_workflow(canonical) and 'PHONE_COMPLETION_ONLY' not in os.environ,
                         'Closed legacy iOS supplement workflow/profile differs')
        selected_scopes = SCOPES
    # The original release workflow remains independently byte fenced.
    release = original.read_regular(original.WORKFLOW, 128*1024).decode()
    original.require(release == original.render_workflow(canonical), 'Original release workflow changed')
    e = os.environ; sha = e.get('GITHUB_SHA', '')
    original.require(re.fullmatch('[0-9a-f]{40}', sha) is not None and e.get('GITHUB_WORKFLOW_SHA') == sha,
                     'Wrong supplement source/workflow SHA')
    original.require(e.get('GITHUB_REPOSITORY') == original.REPOSITORY and e.get('GITHUB_REF') == REF and
                     e.get('GITHUB_WORKFLOW_REF') == WORKFLOW_REF, 'Wrong supplement repository/ref/workflow')
    original.require(e.get('GITHUB_EVENT_NAME') == 'push' and e.get('IOS_FIRST_RELEASE_CANDIDATE_ONLY') == 'true' and
                     e.get('QRCATCHER_IOS_SUPPLEMENT_ONLY') == 'true', 'Closed supplement push flags required')
    original.require(e.get('RUNNER_OS') == 'macOS' and e.get('RUNNER_ARCH') == 'ARM64', 'Wrong standard Mac architecture')
    job = e.get('GITHUB_JOB'); scope = e.get('EVIDENCE_SCOPE', '')
    original.require((job == 'preflight' and scope == '') or (job == 'platform' and scope in selected_scopes),
                     'Wrong supplement job/scope')
    original.require(all(re.fullmatch('[1-9][0-9]{0,19}', e.get(k, '')) for k in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')),
                     'Wrong run/attempt identity')
    identity = {'version': 1, 'release_candidate_only': True, 'diagnostic_only': True, 'release_qualification': False,
        'full_original_row_qualification': False, 'repository': original.REPOSITORY, 'source_sha': sha,
        'workflow_sha': sha, 'ref': REF, 'workflow_ref': WORKFLOW_REF, 'workflow_sha256': original.digest(workflow.encode()),
        'canonical_workflow_sha256': original.CANONICAL_SHA256, 'run_id': e['GITHUB_RUN_ID'],
        'run_attempt': e['GITHUB_RUN_ATTEMPT'], 'job': job, 'scope': scope, 'selected_scopes': list(selected_scopes),
        'selected_cases': selected_cases(scope), 'project': original.PROJECT, 'scheme': original.SCHEME,
        'shipping_watch_requested': False, 'maximum_simultaneous_slots': 1, 'cancel_in_progress': False,
        'permissions': {'contents': 'read'}, 'required_unit_cases': 30,
        'required_phone_cases': {'ordinary': 2, 'files': 1, 'photos': 1},
        'required_pad_cases': {'layout': 2, 'files': 1, 'photos': 1},
        'required_mini_supplement_cases': {'warmup': 1, 'photos': 1},
        'mini_row_seconds': 2220, 'mini_job_seconds': 3000, 'mini_build_phase_seconds': 180,
        'mini_compiler_seconds': 135, 'first_mini_bootstrap_caps': {'precheck': 30, 'boot': 30, 'bootstatus': 210},
        'first_mini_summary_seconds': 30, 'mini_full_row_reservation': {'command_seconds': 2090, 'operations': 21,
            'post_return_seconds_each': 2, 'cleanup_reserve_seconds': 20, 'total_seconds': 2152,
            'phase_headroom_seconds': 68, 'after_configure_seconds': 2026, 'after_first_bootstrap_seconds': 1750},
        'bootstrap_proves_automation_session_stability': False,
        'preflight_evidence_limit_bytes': 1000000, 'selected_runtime_evidence_limit_bytes': 8000000,
        'historical_component_reference': {'source_sha': PRIOR_SOURCE, 'tree_sha': PRIOR_TREE,
            'run_id': PRIOR_RUN, 'run_attempt': '1', 'historical_original_rows_passed': False},
        'unselected_cases_are_not_claimed_run_or_passed': True}
    if phone_completion: identity['phone_completion_only'] = True
    return identity

def retain_hosted(device, exit_code, started):
    """Retain the exact unchanged30-case hosted stage before later UI work."""
    from atomic_json import write_json
    from owned_process_barrier import blocked, mark_unconfirmed
    from watch_process import execute
    identity = current_identity()
    original.require(identity['job'] == 'platform' and identity['scope'] == 'iphone_pro',
                     'Hosted supplement belongs only to Pro')
    original.require(re.fullmatch('[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}', device), 'Wrong hosted device')
    original.require(os.environ.get('SIMULATOR_ID') == device, 'Wrong selected hosted device')
    command = ['xcodebuild','test-without-building','-project',PROJECT,'-scheme',SCHEME,'-configuration','Debug',
        '-derivedDataPath','build/iOS','-destination','platform=iOS Simulator,id='+device,
        '-only-testing:QRCatcherTests','-parallel-testing-enabled','NO','-collect-test-diagnostics','never',
        '-test-timeouts-enabled','YES','-default-test-execution-time-allowance','90',
        '-maximum-test-execution-time-allowance','120','-resultBundlePath','iOSUnitResults.xcresult',
        'CODE_SIGNING_ALLOWED=NO']
    raw = original.read_regular(Path('ios-unit.log'),17*1024*1024).decode()
    starts = [json.loads(line.split(' ',1)[1]) for line in raw.splitlines() if line.startswith('BOUNDED_COMMAND_START ')]
    ends = [json.loads(line.split(' ',1)[1]) for line in raw.splitlines() if line.startswith('BOUNDED_COMMAND_END ')]
    try:
        for suffix in ('command', 'summary', 'summary-command'):
            path = Path('build/iOSUnitResults-'+suffix+'.json')
            original.require(not path.exists() and not path.is_symlink(), 'Hosted result cannot retry or reuse stale evidence')
        original.require(len(starts)==1 and len(ends)==1 and raw.strip().splitlines()[-1]=='BOUNDED_COMMAND_END '+json.dumps(ends[0]),
                         'One finalized hosted operation required')
        operation = ends[0]
        write_json(Path('build/iOSUnitResults-command.json'),operation,limit=16384)
        elapsed = operation.get('elapsed_seconds')
        original.require(starts[0]=={'seconds':855,'command':command} and operation.get('command')==command and
            operation.get('timeout_seconds')==855 and operation.get('exit')==exit_code and exit_code in (0,65) and
            operation.get('state')=='completed' and operation.get('cleanup_confirmed') is True and
            type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<=elapsed<857 and not blocked(),
            'Hosted operation incomplete, late, foreign or unclean; no summary query')
        summary_command = ['xcrun','xcresulttool','get','test-results','summary','--path','iOSUnitResults.xcresult']
        admission = summary_admission(identity['scope'], 'iOSUnitResults.xcresult', started)
        print('IOS_SUPPLEMENT_SUMMARY_ADMISSION '+json.dumps(admission),flush=True)
        cap = admission['summary_seconds']
        summary_admission(identity['scope'], 'iOSUnitResults.xcresult', started)
        began = time.monotonic()
        code, output, receipt = execute(summary_command,cap,output_limit=65536,tail_limit=65536,echo=False)
        write_json(Path('build/iOSUnitResults-summary-command.json'),receipt,limit=16384)
        if output: Path('build/iOSUnitResults-summary.json').write_text(output)
        duration = receipt.get('elapsed_seconds')
        original.require(code==0 and receipt.get('command')==summary_command and receipt.get('timeout_seconds')==cap and
            receipt.get('exit')==0 and receipt.get('state')=='completed' and receipt.get('cleanup_confirmed') is True and
            receipt.get('output_bytes')==len(output.encode()) and type(duration) in (int,float) and
            math.isfinite(duration) and 0<=duration<cap+SUMMARY_POST_RETURN_SECONDS and
            time.monotonic()<began+cap+SUMMARY_POST_RETURN_SECONDS and
            time.monotonic()+SUMMARY_CLEANUP_SECONDS<=admission['phase_deadline_monotonic'],
            'Hosted summary incomplete, late or unclean')
        value = json.loads(output)
        counts = {key:value.get(key) for key in ('totalTestCount','passedTests','failedTests','skippedTests','expectedFailures')}
        rows = value.get('devicesAndConfigurations')
        original.require(all(type(v) is int and v>=0 for v in counts.values()) and counts['totalTestCount']==30 and
            counts['skippedTests']==0 and counts['expectedFailures']==0 and counts['passedTests']+counts['failedTests']==30 and
            isinstance(rows,list) and len(rows)==1 and rows[0].get('device',{}).get('deviceId')==device and
            value.get('runtimeWarnings')==[], 'Hosted exact count/destination mismatch')
        original.require((exit_code==0 and value.get('result')=='Passed' and counts['passedTests']==30 and value.get('testFailures')==[]) or
            (exit_code==65 and value.get('result')=='Failed' and counts['failedTests']>0 and
             isinstance(value.get('testFailures'),list) and bool(value['testFailures'])), 'Hosted CLI/summary conflict')
        return {'diagnostic_only':True,'counts':counts,'result':'iOSUnitResults.xcresult','device':device}
    except BaseException:
        mark_unconfirmed({'state':'supplement_hosted_unresolved','exit':126,'cleanup_confirmed':False})
        raise

def report_retained_summaries():
    """Print only existing bounded raw evidence; never query or qualify cases."""
    from ios_import_continuation import read_regular
    identity = current_identity()
    scope = identity['scope']
    original.require(identity['job']=='platform' and scope in SUMMARY_CAPS, 'Closed non-Mini supplemental reporting scope required')
    root = Path(os.environ.get('GITHUB_WORKSPACE',''))
    original.require(root.is_absolute() and root.resolve(strict=True)==root and Path.cwd()==root,
                     'Canonical supplemental reporting checkout required')
    reports = []
    for result,cap in SUMMARY_CAPS[scope].items():
        stem = result.removesuffix('.xcresult')
        report = {'result':result,'state':'missing','reader_receipt':'missing','acceptance':False,
                  'qualification':'Reporting only; original native and reader receipts retain their outcomes'}
        raw = None
        try:
            raw = read_regular(Path('build')/(stem+'-summary.json'),65536).decode()
            report['state'] = 'unqualified_retained_raw'
            command = ['xcrun','xcresulttool','get','test-results','summary','--path',result]
            receipt = json.loads(read_regular(Path('build')/(stem+'-summary-command.json'),16384))
            duration = receipt.get('elapsed_seconds')
            complete = (receipt.get('command')==command and receipt.get('timeout_seconds')==cap and
                receipt.get('exit')==0 and receipt.get('state')=='completed' and receipt.get('cleanup_confirmed') is True and
                receipt.get('output_bytes')==len(raw.encode()) and type(duration) in (int,float) and
                math.isfinite(duration) and 0<=duration<cap+SUMMARY_POST_RETURN_SECONDS)
            report['reader_receipt'] = 'completed' if complete else 'unqualified'
            if complete: report['state'] = 'retained_raw_not_requalified'
        except (OSError,ValueError,UnicodeError,AttributeError) as error:
            if raw is None and not isinstance(error,FileNotFoundError): report['state'] = 'unqualified_unreadable'
            report['reason'] = str(error)[:240]
        reports.append(report)
        print('IOS_SUPPLEMENT_RETAINED_SUMMARY '+json.dumps(report),flush=True)
        if raw is not None: print(raw,flush=True)
    return reports

if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'write':
        WORKFLOW.write_text(render_workflow(original.read_regular(original.CANONICAL, 128*1024).decode()))
    elif len(sys.argv)==5 and sys.argv[1]=='retain-hosted':
        print(json.dumps(retain_hosted(sys.argv[2],int(sys.argv[3]),float(sys.argv[4])),sort_keys=True))
    elif len(sys.argv)==2 and sys.argv[1]=='summary-retained':
        report_retained_summaries()
    else:
        raise SystemExit('Use original route CLI with its exact supplementary identity dispatcher')
