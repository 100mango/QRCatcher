#!/usr/bin/env python3
"""Closed original-iOS missing-case route; reuse the reviewed executors."""
import os
import json
import math
from pathlib import Path
import re
import sys
import ios_original_release_route as original

BRANCH = 'codex/ios-original-supplement'
REF = 'refs/heads/' + BRANCH
WORKFLOW = Path('.github/workflows/ios-original-supplement.yml')
WORKFLOW_REF = '100mango/QRCatcher/.github/workflows/ios-original-supplement.yml@' + REF
SCOPES = original.SCOPES
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

def render_workflow(canonical):
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
    body = original.replace_once(body, unit_line,
        '        set +e\n' + unit_line +
        '        UNIT_EXIT=${PIPESTATUS[0]}\n        set -e\n' +
        '        python3 scripts/ios_original_supplement_route.py retain-hosted "$SIMULATOR_ID" "$UNIT_EXIT"\n' +
        '        exit "$UNIT_EXIT"\n')
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
    original.require(workflow == render_workflow(canonical), 'Closed iOS supplement workflow differs')
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
    original.require((job == 'preflight' and scope == '') or (job == 'platform' and scope in SCOPES),
                     'Wrong supplement job/scope')
    original.require(all(re.fullmatch('[1-9][0-9]{0,19}', e.get(k, '')) for k in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')),
                     'Wrong run/attempt identity')
    return {'version': 1, 'release_candidate_only': True, 'diagnostic_only': True, 'release_qualification': False,
        'full_original_row_qualification': False, 'repository': original.REPOSITORY, 'source_sha': sha,
        'workflow_sha': sha, 'ref': REF, 'workflow_ref': WORKFLOW_REF, 'workflow_sha256': original.digest(workflow.encode()),
        'canonical_workflow_sha256': original.CANONICAL_SHA256, 'run_id': e['GITHUB_RUN_ID'],
        'run_attempt': e['GITHUB_RUN_ATTEMPT'], 'job': job, 'scope': scope, 'selected_scopes': list(SCOPES),
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

def retain_hosted(device, exit_code):
    """Retain the exact unchanged30-case hosted stage before later UI work."""
    from atomic_json import write_json
    from owned_process_barrier import blocked, mark_unconfirmed
    from watch_process import execute
    identity = current_identity()
    original.require(identity['job'] == 'platform' and identity['scope'] == 'iphone_pro',
                     'Hosted supplement belongs only to Pro')
    original.require(re.fullmatch('[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}', device), 'Wrong hosted device')
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
        code, output, receipt = execute(summary_command,10,output_limit=65536,tail_limit=65536,echo=False)
        write_json(Path('build/iOSUnitResults-summary-command.json'),receipt,limit=16384)
        if output: Path('build/iOSUnitResults-summary.json').write_text(output)
        duration = receipt.get('elapsed_seconds')
        original.require(code==0 and receipt.get('command')==summary_command and receipt.get('timeout_seconds')==10 and
            receipt.get('exit')==0 and receipt.get('state')=='completed' and receipt.get('cleanup_confirmed') is True and
            receipt.get('output_bytes')==len(output.encode()) and type(duration) in (int,float) and
            math.isfinite(duration) and 0<=duration<12, 'Hosted summary incomplete, late or unclean')
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

if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'write':
        WORKFLOW.write_text(render_workflow(original.read_regular(original.CANONICAL, 128*1024).decode()))
    elif len(sys.argv)==4 and sys.argv[1]=='retain-hosted':
        print(json.dumps(retain_hosted(sys.argv[2],int(sys.argv[3])),sort_keys=True))
    else:
        raise SystemExit('Use original route CLI with its exact supplementary identity dispatcher')
