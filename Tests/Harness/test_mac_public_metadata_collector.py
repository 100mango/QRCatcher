"""Executable offline collector adversaries; synthetic bytes are not native proof."""
import copy
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
import uuid
import zlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import export_mac_public_metadata as collector
import diagnostic_mac_public_metadata_route as real_route
import mac_public_metadata_schema as schema

spec = importlib.util.spec_from_file_location('metadata_fixture', Path(__file__).with_name('test_mac_public_metadata.py'))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)

# Exact retained tree from public 0ab198e38bd8d0a3d54358812f487ec74fa6eac1,
# run 37371962733, artifact 11370899424. This attests tree shape only.
ACTUAL_NATIVE_TEST_RESULTS = zlib.decompress(base64.b64decode(
    'eNrtm91v2jAQwN/5K6w8bdIKJLQB+tahVUJbu60f28PUB8e5FGuOHdlOKZv6v88JbQIj6cfWdup0EkKQu/P57vzDxol/dgjxYrjgDIxHdsk3952Qn+W7k1DNZtwCs7mGQuwupOG29+ZGvrScxqVsB3ZofxyNaMJGw1HEBiyKkjDZhsCPfIj6/mDA+kEQ/25+SNNl4wcLckBZLU5VDKKSfuHa5lQUKjMuoVZT5m3ORXyYpxHoUjUI97aD0arGF9CGK7mUDrv9WpYJahOl01KUUvbx2CtFV+79rNDyLBh76LrSlCDXFRFrkLVoVXyLyu9qd6g2qd/DpM2sNJU3mU0oFxCTLbLH3DAwPOKC2wWhecwt+eZyslVm3MCWBpWBhPhsl0yUtJoaS5bWVUI33bjUnSyypat9p+zGEjlwfug5tFsZlWsGHxSj9rpubXE45cT14BO1s9JF79S4Yvd0LiXo3lzp773PRxNq2cx9bfjkxtPp9MTV2DRd65o5T2xrP51z4VJTj73QH7aoXjVev3rzh0XD/Lfk33+e/CM0CA1C8xzQvBOQgrRkRg2RiriJmGmelRnG+j0vP1iKF4hSpgRnC5x9cPZBZBAZRAaRQWQQGUQGkUFkEBlEBpFBZBAZRAaRQWTakJFAtViQjBqDlft35GAZXhhAeMMA7938vyA1XD1r8ubFua5y4fkp8cfGu1VxKo+BKRmXzxwNx91hOAx3/P7IvXaCRsuqzsXjSpMlhxPNLWdU7As1f/W62WNR4mnsBgZP+PXjU03p/atWT48+VF3b7fWYSrs0ywR0L5nTe3hh23rT3pdqEBf2ZEJN8/D1NJhc2Gq4u0mmcw8A/+GTWREkShe3yw3/AbjIx0U+rlGQGCQGiXlCYnAliYt65OjhHKVc8jRPt+ZcxmqOUw9OPYgMIoPIIDJPigyuEXC5hnuw63uwg/AhG7CDsDsc+aEfjMdBMArD0d07sIeulQv4WjJ4VP5xeg+Qmf1ciD1WODjhVoB5hF3ZR/X0JDu19+zh8+zedu4YK3UZG8LxNrWfNH3N/tbTcZxzu5mPu3Kxmoe1HNw//keMfbPdKsbTKSlaJFEuY7Ee520x3sRXxdYc1zGVcaQu6+Pgm/n9JGj969zmcv20eGHiFkoJP7/+NWk8Or6qcH2E3q8drYmrQ/DLirvOp0CW7Kz471x1fgHr+sSg'))


def unknown_metadata(rows):
    for index, (entry, body) in enumerate(rows):
        if entry.get('name', '').startswith('mac-public-metadata-'):
            value = schema.decode(body)
            value['sameState'], value['reason'] = 'UNKNOWN', 'state-or-geometry-mismatch'
            rows[index] = (entry, encoded(value))


ORDINARY_BYTES = b'UNRELATED-ORDINARY-SNAPSHOT-BYTES-MUST-NOT-BE-UPLOADED'


def ordinary_snapshots(rows, total):
    while len(rows) < total:
        rows.append((dict(name='Ordinary XCTest snapshot ' + str(len(rows))), ORDINARY_BYTES))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode()


def summary(hosted=False):
    count = 26 if hosted else 2
    device = dict(architecture='arm64', deviceId='a' * 40, deviceName='My Mac', modelName='Virtual Machine',
                  osBuildNumber='26A428', osVersion='27.0', platform='macOS')
    return dict(totalTestCount=count, passedTests=count if hosted else 0, failedTests=0 if hosted else count,
                skippedTests=0, expectedFailures=0, result='Passed' if hosted else 'Failed', startTime=1000.0,
                finishTime=1100.0, runtimeWarnings=[], testFailures=[],
                title='Test - QRCatcherMac' if hosted else 'Test - QRCatcherMacSandbox',
                devicesAndConfigurations=[dict(device=device, passedTests=count if hosted else 0,
                                               failedTests=0 if hosted else count, skippedTests=0, expectedFailures=0)])


def test_tree():
    return {'testNodes': [dict(nodeType='Test Case', name=c + '()', result='Failed',
                              nodeIdentifier='QRCatcherMacUITests/' + c + '()',
                              nodeIdentifierURL='test://com.apple.xcode/QRCatcher/QRCatcherMacUITests/QRCatcherMacUITests/' + c)
                          for c in collector.CASES]}


def non_case_children(tests):
    """Synthetic result details, never a claim about unretained native children."""
    for row in tests['testNodes']:
        row['children'] = [dict(nodeType='Failure Message', name='Strict audit callback',
                                children=[dict(nodeType='Source Location', name='fixture')])]


def paired(case, checkpoint, observed=True):
    native = fixtures.MacPublicMetadataTests().receipt(case, checkpoint, observed=True)
    token = ('7FAAE2C9-89A0-4FFB-946D-3F01CB62C875' if case == collector.CASES[0]
             else 'A9EEDC77-51E8-4464-943D-3531D70B3AD3')
    request = str(uuid.uuid5(uuid.NAMESPACE_URL, checkpoint)).upper()
    native['token'], native['requestID'] = token, request
    row = {key: native[key] for key in ('schema', 'token', 'case', 'checkpoint', 'sequence', 'requestID')}
    row.update(auditQualified=False, contrastQualified=False, sameState='OBSERVED' if observed else 'UNKNOWN',
               reason='bounded-public-pair' if observed else 'missing-or-invalid-receipt')
    if not observed:
        return row
    def converted(frame):
        return [frame[0], 768 - frame[1] - frame[3], frame[2], frame[3]]
    rows = [dict(kind=target['kind'], matches=1, frame=converted(target['wrapper']['frame']),
                 valueUTF16Length=target['expectedUTF16Length'], valueSHA256=target['expectedSHA256'])
            for target in native['targets']]
    row.update(native=native, generalChangeCountUnchanged=True,
               paired=dict(windows=1, mainWindowMatches=1, windowFrame=converted(native['window']['frame']),
                           sheets=1 if checkpoint == 'mac-chinese-policy' else 0, dialogs=0, foreground=True,
                           screenFrame=[0, 0, 1024, 768], targets=rows, screens=1,
                           coordinateSpace='XCTest-screen-top-left'))
    return row


def supporting(locale, phase):
    count = 1 if phase == 'full' else 2
    texts = (['Links open only when you choose Open in Browser.', f'{count} saved on this Mac'] if locale == 'en'
             else ['只有点击「在浏览器中打开」才会打开链接。', f'本机已保存 {count} 条记录'])
    case = collector.CASES[0 if locale == 'en' else 1]
    return dict(locale=locale, phase=phase, case='-[QRCatcherMacUITests ' + case + ']', window=[0, 0, 1000, 800],
                contrast_qualified=False, reference_font_is_resolved_element_font=False,
                height_proxy_used_as_acceptance=False,
                roles=[dict(role=role, text=text, frame=[20, 20, 200, 20], body_measurement_height=16,
                            reference_body_font='.SFNS-Regular', reference_body_point_size=13)
                       for role, text in zip(('link-policy', 'saved-count'), texts)])


def transition(locale, phase):
    before = 'https://example.com/qrcatcher?source=golden' if locale == 'en' else 'QRCatcher 你好 🌈 123'
    after = ('Keep the full QR result readable alongside its safety instruction and saved-history count. ' * 4
             if locale == 'en' else '完整保留二维码内容，支持中文和 English，并且仍能阅读说明与保存数量。' * 6)
    digest = hashlib.sha256(after.encode()).hexdigest()
    row = dict(locale=locale, phase=phase, wrapper_before=before, copy_before=before,
               wrapper_identity_refresh_scope='selectable Text only', raster_width=474, raster_height=474,
               clipboard_tiff_bytes=898970, expected_payload_utf8_bytes=len(after.encode()),
               expected_payload_sha256=digest, clipboard_tiff_sha256='a' * 64, fixture_control_exact=True,
               full_equality_verified=phase == 'copy-observed')
    if phase == 'copy-observed':
        row.update(wrapper_after=after, copy_after_sha256=digest, copy_after_utf8_bytes=len(after.encode()),
                   rendered_text_observation=dict(wrapper_hittable=False, wrapper_enabled=False, direct_child_count=1,
                                                  rendered_static_text_count=1, rendered_identifier='',
                                                  rendered_frame=[20, 20, 200, 20], wrapper_interaction_required=False,
                                                  observations_qualify_pass=False))
    return row


def png(name, size=0):
    data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + struct.pack('>II', 1024, 768) + name.encode()
    return data + b'x' * max(0, size - len(data))


def attachments():
    result = []
    for name in collector.FRAMES:
        result.append((dict(name=name), png(name) if name in collector.PNG_FRAMES else b'\xff\xd8' + name.encode()))
    for case in collector.CASES:
        for checkpoint in schema.CASES[case]:
            result.append((dict(name='mac-public-metadata-' + checkpoint), encoded(paired(case, checkpoint))))
    for locale in ('en', 'zh-Hans'):
        for phase in ('full', 'minimum-long-content'):
            result.append((dict(name='mac-supporting-text-layout'), encoded(supporting(locale, phase))))
        for phase in ('prepared', 'copy-observed'):
            result.append((dict(name='mac-payload-transition'), encoded(transition(locale, phase))))
    for name in collector.CHECKPOINTS:
        result.append((dict(name='mac-audit-element'), ('Checkpoint: ' + name + '\nContrast failed\nStrict callback').encode()))
    result.extend([(dict(name='mac-failure'), b'\xff\xd8failure1'), (dict(name='mac-failure'), b'\xff\xd8failure2')])
    return result


class CollectorTests(unittest.TestCase):
    def exercise(self, *, edit=None, edit_summary=None, edit_tests=None, mode=None, hosted=False, clock=None, native_tests=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / 'build').mkdir()
            (root / collector.RESULT).mkdir()
            (root / collector.RESULT / 'Info.plist').write_bytes(b'offline-fixture')
            if hosted:
                (root / 'MacTestResults.xcresult').mkdir()
                (root / 'MacTestResults.xcresult/Info.plist').write_bytes(b'offline-hosted-fixture')
            initial = dict(job='platform', scope='macos', diagnostic_only=True, release_qualification=False,
                           selected_ui_cases=list(collector.CASES), metadata_checkpoints=list(collector.CHECKPOINTS),
                           source_sha='a' * 40, tested_tree='b' * 40, workflow_sha='a' * 40, run_id='123',
                           run_attempt='1', ref=real_route.REF, workflow_ref=real_route.WORKFLOW_REF)
            route = types.SimpleNamespace(current_identity=lambda: copy.deepcopy(initial),
                                          retained_initial_record=lambda expected: copy.deepcopy(expected),
                                          fixed_commands=real_route.fixed_commands)
            for key, filename in [('sandbox_build', 'mac-sandbox-build.log'), ('sandbox_test', 'mac-sandbox-test.log')]:
                command, seconds = real_route.fixed_commands()[key]
                code = 0 if key == 'sandbox_build' else 65
                outcome = dict(command=command, timeout_seconds=seconds, state='completed', exit=code,
                               cleanup_confirmed=True, output_bytes=100, elapsed_seconds=10.0)
                if mode == 'receipt-cleanup' and key == 'sandbox_test':
                    outcome.update(state='cleanup_unconfirmed', exit=126, original_exit=65, cleanup_confirmed=False)
                if mode == 'receipt-timeout' and key == 'sandbox_test':
                    outcome.update(state='timed_out', exit=124, cleanup_confirmed=True, elapsed_seconds=601.0)
                if mode == 'wrong-command' and key == 'sandbox_test':
                    outcome['command'] = command + ['-only-testing:Other/Other/testOther']
                log = b'BOUNDED_COMMAND_START ' + encoded(dict(command=command, seconds=seconds)) + b'\n'
                if key == 'sandbox_test' and mode != 'missing-launch-context':
                    bundle = str(root / 'build/MacSandbox/Build/Products/Debug/QRCatcherMac.app')
                    for pid in (1200, 1201):
                        launch = dict(actual_bundle=bundle, expected_bundle=bundle,
                                      actual_executable=bundle + '/Contents/MacOS/QRCatcherMac', pid=pid,
                                      executable_sha256='a' * 64, product_app_sandbox=True,
                                      code_payload_sha256={'QRCatcherMac': 'a' * 64, 'QRCatcherMac.debug.dylib': 'b' * 64})
                        if mode == 'wrong-launch-path':
                            launch['actual_bundle'] = '/Applications/QRCatcherMac.app'
                        if mode == 'numeric-launch-sandbox':
                            launch['product_app_sandbox'] = 1
                        log += b'RUNNING_APP_PROVENANCE: ' + encoded(launch) + b'\n'
                log += b'product fixture log\nBOUNDED_COMMAND_END ' + encoded(outcome) + b'\n'
                (root / filename).write_bytes(log)
            if mode == 'durable-cleanup':
                (root / 'build/owned-process-cleanup.json').write_bytes(b'{"blocked":true}')
            if mode == 'fixture-latch':
                (root / 'build/fixture-query-inflight.json').write_bytes(b'{"inflight":true}')
            if mode == 'initial-seal':
                route.retained_initial_record = lambda _: (_ for _ in ()).throw(ValueError('Initial source/run seal differs'))
            if mode == 'result-symlink':
                (root / collector.RESULT / 'Info.plist').unlink()
                (root / 'info.plist').write_bytes(b'fixture')
                (root / collector.RESULT / 'Info.plist').symlink_to(root / 'info.plist')
            data = attachments()
            if edit:
                edit(data)
            native_summary, tests = summary(), schema.decode(ACTUAL_NATIVE_TEST_RESULTS) if native_tests else test_tree()
            if edit_summary:
                edit_summary(native_summary)
            if edit_tests:
                edit_tests(tests)
            calls = []

            def runner(command, seconds, **options):
                calls.append((command, seconds, options))
                operation = dict(command=command, timeout_seconds=seconds, cleanup_confirmed=True, state='completed',
                                 exit=0, output_bytes=0, elapsed_seconds=0.0)
                if mode == 'mid-cleanup' and len(calls) == 1:
                    operation.update(cleanup_confirmed=False, state='cleanup_unconfirmed', exit=126)
                    return 126, '', operation
                if mode == 'tests-cleanup' and len(calls) == 2 or mode == 'export-cleanup' and len(calls) == 3:
                    operation.update(cleanup_confirmed=False, state='cleanup_unconfirmed', exit=126)
                    return 126, '', operation
                if mode == 'durable-mid-cleanup' and len(calls) == 1:
                    (root / 'build/owned-process-cleanup.json').write_bytes(b'{"blocked":true}')
                if mode == 'tool-output-limit' and len(calls) == 1:
                    operation.update(state='output_limit', exit=125)
                    return 125, 'x' * collector.JSON_CAP, operation
                if mode == 'wrong-operation-command' and len(calls) == 1:
                    operation['command'] = command + ['--other']
                if mode == 'wrong-operation-cap' and len(calls) == 1:
                    operation['timeout_seconds'] = seconds + 1
                if mode == 'numeric-operation-exit' and len(calls) == 1:
                    operation['exit'] = False
                if mode == 'numeric-operation-cleanup' and len(calls) == 1:
                    operation['cleanup_confirmed'] = 1
                if mode == 'boolean-operation-bytes' and len(calls) == 1:
                    operation['output_bytes'] = True
                if mode == 'nonfinite-operation-time' and len(calls) == 1:
                    operation['elapsed_seconds'] = float('nan')
                if command[1:5] == ['xcresulttool', 'get', 'test-results', 'summary']:
                    text = encoded(summary(True) if command[-1] == 'MacTestResults.xcresult' else native_summary).decode()
                    if mode == 'hosted-wrong-device' and command[-1] == 'MacTestResults.xcresult':
                        value = schema.decode(text.encode())
                        value['devicesAndConfigurations'][0]['device']['deviceId'] = 'b' * 40
                        text = encoded(value).decode()
                elif command[1:5] == ['xcresulttool', 'get', 'test-results', 'tests']:
                    text = ACTUAL_NATIVE_TEST_RESULTS.decode() if native_tests and not edit_tests else encoded(tests).decode()
                    if mode == 'tests-durable-cleanup':
                        (root / 'build/owned-process-cleanup.json').write_bytes(b'{"blocked":true}')
                    if mode == 'tests-duplicate-keys':
                        text = '{"testNodes":[],"testNodes":[]}'
                    if mode == 'tests-nonfinite':
                        text = '{"testNodes":[],"value":NaN}'
                    if mode == 'tests-oversize':
                        text = '{"value":"' + 'x' * collector.JSON_CAP + '"}'
                elif command[1:4] == ['xcresulttool', 'export', 'attachments']:
                    staging = root / command[-1]
                    staging.mkdir()
                    manifest = []
                    for n, (entry, body) in enumerate(data):
                        entry = copy.deepcopy(entry)
                        filename = str(n) + ('.json' if body.startswith(b'{') else '.bin')
                        (staging / filename).write_bytes(body)
                        entry['exportedFileName'] = filename
                        manifest.append(entry)
                    if mode == 'attachment-path-escape':
                        manifest[0]['exportedFileName'] = '../outside.png'
                    if mode == 'attachment-symlink':
                        (staging / manifest[0]['exportedFileName']).unlink()
                        (staging / manifest[0]['exportedFileName']).symlink_to(root / 'info.png')
                        (root / 'info.png').write_bytes(png('redirected'))
                    if mode == 'attachment-hardlink':
                        os.link(staging / manifest[0]['exportedFileName'], staging / 'hardlink.png')
                    if mode == 'attachment-count':
                        manifest = [dict(exportedFileName=f'extra-{n}.bin') for n in range(1025)]
                    if mode == 'attachment-duplicate-filename':
                        manifest[1]['exportedFileName'] = manifest[0]['exportedFileName']
                    if mode == 'attachment-filename-type':
                        manifest[0]['exportedFileName'] = True
                    if mode == 'manifest-oversize':
                        manifest = {'oversize': 'x' * collector.JSON_CAP}
                    manifest_bytes = encoded(manifest)
                    if mode == 'manifest-duplicate-keys':
                        manifest_bytes = b'{"value":[],"value":[]}'
                    if mode == 'manifest-nonfinite':
                        manifest_bytes = b'{"value":NaN}'
                    if mode == 'manifest-node-bomb':
                        manifest_bytes = encoded({'value': ['x'] * 8192})
                    (staging / 'manifest.json').write_bytes(manifest_bytes)
                    text = ''
                else:
                    raise AssertionError('Unexpected command: ' + str(command))
                if mode != 'boolean-operation-bytes':
                    operation['output_bytes'] = len(text.encode())
                return 0, text, operation

            previous = Path.cwd()
            try:
                os.chdir(root)
                environment = {'GITHUB_WORKSPACE': str(root), 'QRCATCHER_OWNED_PROCESS_BARRIER': str(root / 'build/owned-process-cleanup.json')}
                if mode == 'propagated-cleanup':
                    environment['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED'] = 'true'
                with patch.dict(os.environ, environment, clear=True):
                    report = collector.collect(runner=runner, route=route, clock=clock)
                self.files = {p.name: p.read_bytes() for p in (root / collector.OUT).iterdir()}
                self.calls = calls
                self.size = sum(len(v) for v in self.files.values())
                self.assertLessEqual(self.size, collector.SCOPE_CAP)
                self.assertTrue(all(len(v) <= collector.FILE_CAP for v in self.files.values()))
                self.assertIs(report['auditQualified'], False)
                self.assertIs(report['contrastQualified'], False)
                self.assertIs(report['release_qualification'], False)
                self.assertFalse(any('xcresult' in name for name in self.files))
                return report
            finally:
                os.chdir(previous)

    def mutate_receipt(self, action, checkpoint=collector.CHECKPOINTS[0]):
        def edit(rows):
            for n, (entry, body) in enumerate(rows):
                if entry.get('name') == 'mac-public-metadata-' + checkpoint:
                    value = schema.decode(body)
                    action(value)
                    rows[n] = (entry, encoded(value))
                    return
            raise AssertionError(checkpoint)
        return edit

    def test_exact_two_failed_cases_preserve_actual_65_and_all_original_evidence(self):
        report = self.exercise()
        self.assertTrue(report['evidence_complete'], report['errors'])
        self.assertEqual(report['sameState'], 'OBSERVED')
        self.assertEqual(report['original_commands']['sandbox_test']['exit'], 65)
        self.assertEqual(len(report['executed_tests']), 2)
        self.assertEqual(len(report['metadata']), 4)
        self.assertEqual(len(report['screenshots']), 7)
        self.assertEqual(report['strict_audit_callbacks'], 4)
        self.assertIn(b'Strict callback', self.files['sandbox-audit-1.txt'])
        self.assertFalse(report['offline_freshness_revalidated'])
        self.assertEqual([call[1] for call in self.calls], [30, 30, 75])
        self.assertTrue(all(call[2] == dict(output_limit=131072, tail_limit=131072, echo=False) for call in self.calls))
        self.assertEqual(sum(call[1] for call in self.calls), 135)

    def test_exact_retained_native_tree_has_two_failed_cases_and_34_failure_message_children(self):
        self.assertEqual(len(ACTUAL_NATIVE_TEST_RESULTS), 16336)
        self.assertEqual(hashlib.sha256(ACTUAL_NATIVE_TEST_RESULTS).hexdigest(),
                         '865b06f231cd8d998eccd789c35b760feefefcbdef220534def6efa6a53e8f18')
        rows = [row for row in collector.walk(schema.decode(ACTUAL_NATIVE_TEST_RESULTS)) if row.get('nodeType') == 'Test Case']
        self.assertEqual([len(row['children']) for row in rows], [22, 12])
        self.assertTrue(all(child['nodeType'] == 'Failure Message' for row in rows for child in row['children']))
        report = self.exercise(native_tests=True, edit=lambda rows: (unknown_metadata(rows), ordinary_snapshots(rows, 200)))
        self.assertTrue(report['evidence_complete'], report['errors'])
        self.assertEqual(self.files['sandbox-test-results.json'], ACTUAL_NATIVE_TEST_RESULTS)
        self.assertEqual(report['test_identity']['state'], 'OBSERVED')
        self.assertEqual([row['result'] for row in report['executed_tests']], ['Failed', 'Failed'])
        self.assertEqual(report['original_commands']['sandbox_test']['exit'], 65)
        self.assertEqual(report['sameState'], 'UNKNOWN')
        self.assertTrue(all(row['receipt_retained'] and row['sameState'] == 'UNKNOWN' for row in report['metadata']))
        self.assertEqual([call[1] for call in self.calls], [30, 30, 75])

    def test_ordinary_snapshots_above128_and_at1024_keep_closed_bytes_without_uploading_ordinary_files(self):
        for total in (129, 200, 1024):
            report = self.exercise(edit=lambda rows: (unknown_metadata(rows), ordinary_snapshots(rows, total)))
            self.assertTrue(report['evidence_complete'], report['errors'])
            inventory = report['attachment_inventory']
            self.assertEqual(inventory['state'], 'COMPLETE')
            self.assertTrue(inventory['raw_retained'])
            self.assertEqual(inventory['total_records'], total)
            self.assertEqual(inventory['selected_owned_records'], 24)
            self.assertEqual(inventory['unselected_records'], total - 24)
            self.assertEqual(inventory['input_record_limit'], 1024)
            self.assertEqual(inventory['selected_owned_record_limit'], 128)
            self.assertEqual(inventory['retained_file_limit'], 120)
            self.assertLessEqual(len(self.files), 120)
            self.assertFalse(any(ORDINARY_BYTES in data for data in self.files.values()))
            self.assertEqual(sum(row['checkpoint'] in collector.FRAMES for row in report['screenshots']), 6)
            self.assertTrue(all(row['receipt_retained'] and row['sameState'] == 'UNKNOWN' for row in report['metadata']))
            manifest = schema.decode(self.files['sandbox-attachment-manifest.json'], collector.JSON_CAP)
            self.assertEqual(len(collector.attachment_records(manifest)), total)
            self.assertEqual([call[1] for call in self.calls], [30, 30, 75])

    def test_large_valid_required_images_cannot_starve_four_closed_metadata_receipts(self):
        def edit(rows):
            unknown_metadata(rows)
            for index, (entry, data) in enumerate(rows):
                name = entry.get('name')
                if name in collector.FRAMES:
                    data = (png(name, collector.FILE_CAP) if name in collector.PNG_FRAMES else
                            b'\xff\xd8' + b'x' * (collector.FILE_CAP - 2))
                    rows[index] = (entry, data)
            ordinary_snapshots(rows, 200)
        report = self.exercise(edit=edit, native_tests=True)
        self.assertFalse(report['evidence_complete'])
        self.assertEqual(report['sameState'], 'UNKNOWN')
        self.assertEqual(report['attachment_inventory']['state'], 'PARTIAL')
        self.assertTrue(report['missing_frames'])
        self.assertTrue(any('Mac allocation' in error for error in report['errors']))
        for row in report['metadata']:
            self.assertTrue(row['receipt_retained'])
            self.assertEqual(row['sameState'], 'UNKNOWN')
            self.assertIn('sandbox-public-metadata-' + row['checkpoint'] + '.json', self.files)
        self.assertLessEqual(self.size, collector.SCOPE_CAP)
        names = [row['name'] for row in report['files']]
        metadata_positions = [index for index, name in enumerate(names) if name.startswith('sandbox-public-metadata-')]
        frame_positions = [names.index(row['name']) for row in report['screenshots'] if row['checkpoint'] in collector.FRAMES]
        self.assertEqual(len(metadata_positions), 4)
        self.assertTrue(frame_positions)
        self.assertLess(max(metadata_positions), min(frame_positions))
        self.assertEqual([call[1] for call in self.calls], [30, 30, 75])

    def test_input1025_retains_strict_raw_manifest_then_rejects_inventory_without_extra_export(self):
        report = self.exercise(edit=lambda rows: (unknown_metadata(rows), ordinary_snapshots(rows, 1025)))
        self.assertFalse(report['evidence_complete'])
        self.assertEqual(report['attachment_inventory']['total_records'], 1025)
        self.assertEqual(report['attachment_inventory']['state'], 'PARTIAL')
        self.assertEqual(report['attachment_inventory']['unclassified_records'], 1025)
        self.assertTrue(report['attachment_inventory']['raw_retained'])
        self.assertIn('sandbox-attachment-manifest.json', self.files)
        self.assertTrue(any('Input attachment count exceeds 1024' in error for error in report['errors']))
        self.assertTrue(all(row['receipt_retained'] is False for row in report['metadata']))
        self.assertFalse(report['screenshots'])
        self.assertFalse(any(ORDINARY_BYTES in data for data in self.files.values()))
        self.assertEqual([call[1] for call in self.calls], [30, 30, 75])

    def test_frame_with_unproved_metadata_prefix_cannot_take_metadata_priority_or_starve_32k_receipts(self):
        def edit(rows):
            unknown_metadata(rows)
            for index, (entry, data) in enumerate(rows):
                name = entry.get('name', '')
                if name.startswith('mac-public-metadata-'):
                    rows[index] = (entry, data + b' ' * (32768 - len(data)))
                elif name in collector.FRAMES:
                    entry['suggestedHumanReadableName'] = 'mac-public-metadata-unproved-presentation'
                    size = 400 * 1024 if name == collector.FRAMES[3] else collector.FILE_CAP
                    data = png(name, size) if name in collector.PNG_FRAMES else b'\xff\xd8' + b'x' * (size - 2)
                    rows[index] = (entry, data)
            ordinary_snapshots(rows, 200)
        report = self.exercise(edit=edit, native_tests=True)
        self.assertFalse(report['evidence_complete'])
        self.assertTrue(report['missing_frames'])
        self.assertEqual(report['sameState'], 'UNKNOWN')
        self.assertTrue(all(row['receipt_retained'] and row['sameState'] == 'UNKNOWN' for row in report['metadata']))
        names = [row['name'] for row in report['files']]
        metadata_positions = [index for index, name in enumerate(names) if name.startswith('sandbox-public-metadata-')]
        frame_positions = [names.index(row['name']) for row in report['screenshots'] if row['checkpoint'] in collector.FRAMES]
        self.assertEqual(len(metadata_positions), 4)
        self.assertLess(max(metadata_positions), min(frame_positions))
        self.assertTrue(all(len(self.files[names[index]]) == 32768 for index in metadata_positions))
        self.assertLessEqual(self.size, collector.SCOPE_CAP)
        self.assertEqual([call[1] for call in self.calls], [30, 30, 75])

    def test_invalid_and_duplicate_input_filenames_reject_affected_bytes_but_keep_independent_receipts(self):
        for mode in ('attachment-path-escape', 'attachment-filename-type', 'attachment-symlink',
                     'attachment-hardlink', 'attachment-duplicate-filename'):
            report = self.exercise(mode=mode, edit=unknown_metadata)
            self.assertFalse(report['evidence_complete'])
            self.assertTrue(report['attachment_inventory']['raw_retained'])
            self.assertEqual(report['attachment_inventory']['state'], 'PARTIAL')
            self.assertNotIn('sandbox-' + collector.FRAMES[0] + '.png', self.files)
            self.assertTrue(all(row['receipt_retained'] and row['sameState'] == 'UNKNOWN' for row in report['metadata']))
            if mode == 'attachment-duplicate-filename':
                self.assertEqual(report['attachment_inventory']['duplicate_filenames'], 1)
                self.assertEqual(report['attachment_inventory']['duplicate_filename_records'], 2)
                self.assertNotIn('sandbox-' + collector.FRAMES[1] + '.png', self.files)
            self.assertEqual(len(self.calls), 3)

    def test_late_owned_identity_schema_type_and_byte_errors_never_qualify_or_erase_other_closed_bytes(self):
        for mutation in (lambda r: r.update(case='testOther'), lambda r: r.update(sequence=True),
                         lambda r: r.update(private_data='PRIVATE-RECEIPT-BYTES')):
            def edit(rows):
                unknown_metadata(rows)
                self.mutate_receipt(mutation)(rows)
                ordinary_snapshots(rows, 200)
            report = self.exercise(edit=edit)
            self.assertFalse(report['evidence_complete'])
            self.assertNotIn('sandbox-public-metadata-mac-before-resize.json', self.files)
            self.assertEqual(sum(row['receipt_retained'] for row in report['metadata']), 3)
            self.assertEqual(sum(row['checkpoint'] in collector.FRAMES for row in report['screenshots']), 6)
            self.assertFalse(any(b'PRIVATE-RECEIPT-BYTES' in data or ORDINARY_BYTES in data for data in self.files.values()))
        def duplicate(rows):
            unknown_metadata(rows)
            rows.append(copy.deepcopy(rows[6]))
            ordinary_snapshots(rows, 200)
        report = self.exercise(edit=duplicate)
        self.assertFalse(report['evidence_complete'])
        self.assertEqual(sum(row['receipt_retained'] for row in report['metadata']), 4)
        def wrong_frame(rows):
            unknown_metadata(rows)
            rows[0] = (rows[0][0], b'\xff\xd8not-a-required-lossless-PNG')
            ordinary_snapshots(rows, 200)
        report = self.exercise(edit=wrong_frame)
        self.assertFalse(report['evidence_complete'])
        self.assertIn(collector.FRAMES[0], report['missing_frames'])
        self.assertTrue(all(row['receipt_retained'] for row in report['metadata']))

    def test_selected_owned128_retained120_and_per_owner_limits_do_not_expand_with_input_inventory(self):
        def excessive(rows):
            unknown_metadata(rows)
            while len(rows) < 130:
                rows.append((dict(name='mac-audit-element'), b'Checkpoint: mac-before-resize\nStrict callback failure'))
        report = self.exercise(edit=excessive)
        self.assertFalse(report['evidence_complete'])
        self.assertEqual(report['attachment_inventory']['selected_owned_records'], 130)
        self.assertEqual(report['attachment_inventory']['selected_owned_record_limit'], 128)
        self.assertLessEqual(len(self.files), 120)
        self.assertLessEqual(report['strict_audit_callbacks'], 48)
        self.assertTrue(all(row['receipt_retained'] for row in report['metadata']))
        self.assertEqual(sum(row['checkpoint'] in collector.FRAMES for row in report['screenshots']), 6)

    def test_raw_manifest_strict_json_topology_and_cleanup_gates_precede_retention(self):
        for mode in ('manifest-oversize', 'manifest-duplicate-keys', 'manifest-nonfinite',
                     'manifest-node-bomb', 'export-cleanup'):
            report = self.exercise(mode=mode)
            self.assertFalse(report['evidence_complete'])
            self.assertFalse(report['attachment_inventory']['raw_retained'])
            self.assertNotIn('sandbox-attachment-manifest.json', self.files)
            self.assertFalse(report['screenshots'])
            self.assertEqual(len(self.calls), 3)

    def test_late_hosted_device_failure_preserves_closed_unknown_evidence_inside_existing_budget(self):
        report = self.exercise(hosted=True, native_tests=True, mode='hosted-wrong-device',
                               edit=lambda rows: (unknown_metadata(rows), ordinary_snapshots(rows, 200)))
        self.assertFalse(report['evidence_complete'])
        self.assertEqual(report['sameState'], 'UNKNOWN')
        self.assertTrue(all(row['receipt_retained'] and row['sameState'] == 'UNKNOWN' for row in report['metadata']))
        self.assertEqual(sum(row['checkpoint'] in collector.FRAMES for row in report['screenshots']), 6)
        self.assertTrue(report['attachment_inventory']['raw_retained'])
        self.assertEqual(report['attachment_inventory']['state'], 'PARTIAL')
        self.assertEqual([call[1] for call in self.calls], [30, 30, 75, 30])
        self.assertLessEqual(sum(call[1] for call in self.calls), collector.EXPORT_SECONDS)

    def test_unused_ordinary_presentation_errors_never_authorize_bytes_or_block_required_retention(self):
        def edit(rows):
            unknown_metadata(rows)
            ordinary_snapshots(rows, 200)
            rows[-1][0]['name'] = 'Unproved ordinary presentation ' + 'x' * 300
        report = self.exercise(edit=edit)
        self.assertFalse(report['evidence_complete'])
        self.assertTrue(all(row['receipt_retained'] for row in report['metadata']))
        self.assertEqual(sum(row['checkpoint'] in collector.FRAMES for row in report['screenshots']), 6)
        self.assertFalse(any(ORDINARY_BYTES in data for data in self.files.values()))

    def test_lossless_bytes_and_dimensions_are_preserved_without_conversion(self):
        report = self.exercise()
        for row in report['screenshots']:
            if row['checkpoint'] in collector.PNG_FRAMES:
                self.assertEqual(self.files[row['name']], png(row['checkpoint']))
                self.assertEqual(row['native_pixel_dimensions'], [1024, 768])
                self.assertTrue(row['source_bytes_preserved'])
        self.assertEqual(self.files['sandbox-mac-chinese-policy.jpg'], b'\xff\xd8mac-chinese-policy')

    def test_valid_unknown_metadata_is_retained_without_qualification(self):
        def edit(rows):
            for n, (entry, body) in enumerate(rows):
                if entry.get('name', '').startswith('mac-public-metadata-'):
                    value = schema.decode(body)
                    rows[n] = (entry, encoded(paired(value['case'], value['checkpoint'], observed=False)))
        report = self.exercise(edit=edit)
        self.assertTrue(report['evidence_complete'], report['errors'])
        self.assertEqual(report['sameState'], 'UNKNOWN')
        self.assertTrue(all(row['sameState'] == 'UNKNOWN' for row in report['metadata']))

    def test_no_process_after_propagated_durable_latch_or_receipt_cleanup_uncertainty(self):
        for mode in ('propagated-cleanup', 'durable-cleanup', 'fixture-latch', 'receipt-cleanup'):
            with self.subTest(mode=mode):
                report = self.exercise(mode=mode)
                self.assertFalse(self.calls)
                self.assertFalse(report['evidence_complete'])
                self.assertEqual(report['sameState'], 'UNKNOWN')
                self.assertTrue(report['owned_cleanup_uncertainty_observed'])
                self.assertIn('mac-sandbox-test-tail.log', self.files)
                self.assertEqual(len(report['metadata']), 4)
                self.assertTrue(all(row['sameState'] == 'UNKNOWN' and row['receipt_retained'] is False for row in report['metadata']))
                self.assertEqual(set(report['missing_metadata']), set(collector.CHECKPOINTS))
                if mode == 'receipt-cleanup':
                    self.assertEqual(report['original_commands']['sandbox_test']['original_exit'], 65)

    def test_mid_export_uncertainty_prevents_every_later_launch(self):
        for mode in ('mid-cleanup', 'durable-mid-cleanup', 'tool-output-limit'):
            with self.subTest(mode=mode):
                report = self.exercise(mode=mode)
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(report['sameState'], 'UNKNOWN')
                self.assertFalse(report['evidence_complete'])

    def test_public_tool_operator_identity_cap_boolean_and_numeric_receipts_reject(self):
        for mode in ('wrong-operation-command', 'wrong-operation-cap', 'numeric-operation-exit',
                     'numeric-operation-cleanup', 'boolean-operation-bytes', 'nonfinite-operation-time'):
            with self.subTest(mode=mode):
                report = self.exercise(mode=mode)
                self.assertEqual(len(self.calls), 1)
                self.assertFalse(report['evidence_complete'])
                self.assertEqual(report['sameState'], 'UNKNOWN')

    def test_actual_original_launches_bind_adjacent_debug_hashes_pids_source_run_device(self):
        report = self.exercise()
        launch = report['launch_context']
        self.assertEqual(launch['state'], 'OBSERVED')
        self.assertEqual([row['pid'] for row in launch['rows']], [1200, 1201])
        self.assertEqual(launch['source_sha'], report['provenance']['source_sha'])
        self.assertEqual(launch['run_id'], report['provenance']['run_id'])
        self.assertEqual(launch['result_device'], report['device'])
        self.assertTrue(launch['checkpoint_pid_pairing'].startswith('UNKNOWN'))
        for mode in ('missing-launch-context', 'wrong-launch-path', 'numeric-launch-sandbox'):
            report = self.exercise(mode=mode)
            self.assertEqual(report['launch_context']['state'], 'UNKNOWN')
            self.assertFalse(report['evidence_complete'])
            self.assertEqual(report['sameState'], 'UNKNOWN')
            self.assertEqual(sum(row['receipt_retained'] for row in report['metadata']), 4)

    def test_initial_seal_wrong_command_or_result_alias_cannot_launch_export(self):
        for mode in ('initial-seal', 'wrong-command', 'result-symlink'):
            report = self.exercise(mode=mode)
            self.assertFalse(self.calls)
            self.assertFalse(report['evidence_complete'])

    def test_leaf_missing_extra_duplicate_target_identifier_and_url_fail_closed(self):
        changes = [lambda t: t['testNodes'].pop(), lambda t: t['testNodes'].append(copy.deepcopy(t['testNodes'][0])),
                   lambda t: t['testNodes'][0].update(nodeIdentifier='QRCatcherMacUITests/testOther()'),
                   lambda t: t['testNodes'][0].update(nodeIdentifierURL=t['testNodes'][0]['nodeIdentifierURL'].replace('/QRCatcherMacUITests/', '/Other/', 1)),
                   lambda t: t['testNodes'][0].update(result='Skipped')]
        for edit in changes:
            report = self.exercise(edit_tests=edit)
            self.assertFalse(report['evidence_complete'])
            self.assertEqual(len(self.calls), 3)
            self.assertEqual(report['test_identity']['state'], 'UNKNOWN')
            self.assertTrue(report['test_identity']['raw_retained'])
            self.assertEqual(report['sameState'], 'UNKNOWN')
            self.assertEqual(report['strict_audit_callbacks'], 0)
            self.assertNotIn('sandbox-mac-failure.jpg', self.files)

    def test_bounded_non_case_children_preserve_exact_failed_cases_without_qualification(self):
        # Both original cases fail strict audits. Non-case detail rows do not
        # become selected tests; every actual Test Case still counts globally.
        report = self.exercise(edit_tests=non_case_children)
        self.assertTrue(report['evidence_complete'], report['errors'])
        self.assertEqual(report['test_identity']['state'], 'OBSERVED')
        self.assertEqual([row['result'] for row in report['executed_tests']], ['Failed', 'Failed'])
        self.assertEqual(report['original_commands']['sandbox_test']['exit'], 65)
        self.assertTrue(all(row['source_bytes_preserved'] for row in report['screenshots']))
        expected = test_tree()
        non_case_children(expected)
        self.assertEqual(self.files['sandbox-test-results.json'], encoded(expected))
        self.assertEqual([call[1] for call in self.calls], [30, 30, 75])

    def test_semantic_failure_keeps_bounded_raw_tree_and_only_closed_unqualified_diagnostics(self):
        def malformed(tests):
            non_case_children(tests)
            tests['testNodes'][0]['children'] = tests['testNodes'][0]['children'][0]
        def receipts(rows):
            for n, (entry, body) in enumerate(rows):
                if entry.get('name', '').startswith('mac-public-metadata-'):
                    value = schema.decode(body)
                    value = paired(value['case'], value['checkpoint'])
                    value['sameState'] = 'UNKNOWN'
                    value['reason'] = 'state-or-geometry-mismatch'
                    rows[n] = (entry, encoded(value))
            rows.append((dict(name='private-arbitrary-attachment'), b'private arbitrary bytes'))
        report = self.exercise(edit_tests=malformed, edit=receipts)
        self.assertFalse(report['evidence_complete'])
        self.assertEqual(report['sameState'], 'UNKNOWN')
        self.assertEqual(report['test_identity'], dict(state='UNKNOWN', reason='test-results-semantic-validation-failed', raw_retained=True))
        self.assertNotIn('executed_tests', report)
        self.assertTrue(any('children must be' in error for error in report['errors']))
        expected = test_tree()
        malformed(expected)
        self.assertEqual(self.files['sandbox-test-results.json'], encoded(expected))
        self.assertEqual(report['original_commands']['sandbox_test']['exit'], 65)
        self.assertEqual(report['strict_audit_callbacks'], 0)
        self.assertFalse(any(name.startswith('sandbox-audit-') or name == 'sandbox-mac-failure.jpg' for name in self.files))
        self.assertFalse(any(b'private arbitrary bytes' in data for data in self.files.values()))
        self.assertEqual(len(report['screenshots']), len(collector.FRAMES))
        for row in report['screenshots']:
            self.assertEqual(row['test_identity_binding'], 'UNKNOWN')
            self.assertEqual(self.files[row['name']], png(row['checkpoint']) if row['checkpoint'] in collector.PNG_FRAMES else b'\xff\xd8mac-chinese-policy')
        for row in report['metadata']:
            self.assertTrue(row['receipt_retained'])
            self.assertEqual(row['test_identity_binding'], 'UNKNOWN')
            self.assertEqual(row['sameState'], 'UNKNOWN')
            self.assertEqual(row['reason'], 'state-or-geometry-mismatch')
        self.assertEqual([call[1] for call in self.calls], [30, 30, 75])
        self.assertEqual(collector.EXPORT_SECONDS, 180)

    def test_nested_selected_or_extra_test_case_subtrees_never_complete_interpretation(self):
        def extra(tests):
            non_case_children(tests)
            tests['testNodes'][0]['children'].append(copy.deepcopy(tests['testNodes'][1]))
        def nested(tests):
            child = tests['testNodes'].pop()
            tests['testNodes'][0]['children'] = [dict(nodeType='Failure Message', children=[child])]
        for edit in (extra, nested):
            report = self.exercise(edit_tests=edit)
            self.assertFalse(report['evidence_complete'])
            self.assertEqual(report['test_identity']['state'], 'UNKNOWN')
            self.assertEqual(report['sameState'], 'UNKNOWN')
            self.assertIn('sandbox-test-results.json', self.files)
            self.assertEqual(len(self.calls), 3)
            self.assertEqual(sum(row['receipt_retained'] for row in report['metadata']), 4)

    def test_unknown_interpretation_preserves_closed_receipt_owner_schema_and_path_negatives(self):
        wrong_tree = lambda t: t['testNodes'][0].update(nodeIdentifier='Other/testOther()')
        changes = [lambda r: r.update(case='testOther'), lambda r: r.update(decoded_text='private history'),
                   lambda r: r.update(sequence=True)]
        for change in changes:
            report = self.exercise(edit_tests=wrong_tree, edit=self.mutate_receipt(change))
            self.assertFalse(report['evidence_complete'])
            self.assertEqual(report['test_identity']['state'], 'UNKNOWN')
            self.assertNotIn('sandbox-public-metadata-mac-before-resize.json', self.files)
        report = self.exercise(edit_tests=wrong_tree, mode='attachment-path-escape')
        self.assertFalse(report['evidence_complete'])
        self.assertIn(collector.FRAMES[0], report['missing_frames'])
        self.assertTrue(all(row['receipt_retained'] for row in report['metadata']))

    def test_unsafe_raw_tests_are_not_retained_and_cleanup_stops_before_diagnostic_export(self):
        for mode in ('tests-duplicate-keys', 'tests-nonfinite', 'tests-oversize',
                     'tests-cleanup', 'tests-durable-cleanup'):
            report = self.exercise(mode=mode)
            self.assertEqual(len(self.calls), 2)
            self.assertNotIn('sandbox-test-results.json', self.files)
            self.assertFalse(report['evidence_complete'])
            self.assertFalse(report['screenshots'])
        def deep(tests):
            value = 0
            for _ in range(34):
                value = [value]
            tests['details'] = value
        for edit in (deep, lambda t: t.update(details=['x'] * 8192)):
            report = self.exercise(edit_tests=edit)
            self.assertEqual(len(self.calls), 2)
            self.assertNotIn('sandbox-test-results.json', self.files)
            self.assertFalse(report['evidence_complete'])
            self.assertFalse(report['screenshots'])
        report = self.exercise(mode='export-cleanup', edit_tests=lambda t: t['testNodes'].pop())
        self.assertEqual(len(self.calls), 3)
        self.assertTrue(report['owned_cleanup_uncertainty_observed'])
        self.assertIn('sandbox-test-results.json', self.files)
        self.assertFalse(report['screenshots'])
        self.assertTrue(all(row['receipt_retained'] is False for row in report['metadata']))

    def test_bounded_test_display_variant_keeps_exact_ids_and_raw_tree_unqualified(self):
        report = self.exercise(edit_tests=lambda t: t['testNodes'][0].update(name='-[QRCatcherMacUITests testNativeWindowResizeKeepsFullActionTitles]'))
        self.assertFalse(report['evidence_complete'])
        self.assertIn('sandbox-test-results.json', self.files)
        self.assertEqual(report['executed_tests'][0]['presentation_binding'], 'UNKNOWN')
        self.assertEqual(len(report['metadata']), 4)

    def test_summary_exact_counts_booleans_device_and_original_exit_binding(self):
        changes = [lambda s: s.update(totalTestCount=True), lambda s: s.update(totalTestCount=7),
                   lambda s: s.update(skippedTests=1), lambda s: s['devicesAndConfigurations'][0]['device'].update(platform='macOS Simulator'),
                   lambda s: s['devicesAndConfigurations'][0]['device'].update(architecture='x86_64'),
                   lambda s: s['devicesAndConfigurations'].append(copy.deepcopy(s['devicesAndConfigurations'][0])),
                   lambda s: s.update(finishTime=1601), lambda s: s.update(title='Test - Other')]
        for edit in changes:
            report = self.exercise(edit_summary=edit)
            self.assertFalse(report['evidence_complete'])
            self.assertEqual(len(self.calls), 1)

    def test_optional_hosted_summary_is_exact_26_same_mac_device_and_within_three_minutes(self):
        report = self.exercise(hosted=True)
        self.assertTrue(report['evidence_complete'], report['errors'])
        self.assertIn('test-summary.json', self.files)
        self.assertEqual(sum(call[1] for call in self.calls), 165)
        hosted_summary = summary(True)
        hosted_summary['finishTime'] = hosted_summary['startTime'] + 1155
        collector.validate_summary(hosted_summary, hosted=True)
        hosted_summary['finishTime'] += 1
        with self.assertRaises(ValueError):
            collector.validate_summary(hosted_summary, hosted=True)
        for change in [lambda s: s.update(totalTestCount=27), lambda s: s.update(totalTestCount=True),
                       lambda s: s.update(title='Test - QRCatcherMacUITests')]:
            value = summary(True)
            change(value)
            with self.assertRaises(ValueError):
                collector.validate_summary(value, hosted=True)

    def test_total_export_clock_budget_stops_before_next_process(self):
        ticks = iter([0, 0, 31, 180, 180])
        report = self.exercise(clock=lambda: next(ticks))
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(report['evidence_complete'])
        self.assertTrue(any('time budget' in error for error in report['errors']))

    def test_metadata_unsafe_core_fields_are_never_retained(self):
        changes = [lambda r: r.update(token=r['token'].lower()), lambda r: r.update(sequence=True),
                   lambda r: r.update(case='testOther'), lambda r: r.update(checkpoint='mac-before-export'),
                   lambda r: r.update(requestID='not-a-uuid'), lambda r: r.update(auditQualified=True),
                   lambda r: r.update(contrastQualified=0), lambda r: r.update(decoded_text='private history'),
                   lambda r: r['native'].update(uptime=True), lambda r: r['native']['window'].update(visible=1),
                   lambda r: r['native']['targets'][0]['queried'].update(frame=[True, 0, 100, 20]),
                   lambda r: r['native']['targets'][0].update(requestedRange=[0, 4097]),
                   lambda r: r['paired'].update(screens=2)]
        for change in changes:
            with self.subTest(change=change):
                report = self.exercise(edit=self.mutate_receipt(change))
                self.assertFalse(report['evidence_complete'])
                self.assertNotIn('sandbox-public-metadata-mac-before-resize.json', self.files)

    def test_negative_native_uptime_is_not_an_admissible_offline_clock(self):
        receipt = paired(collector.CASES[0], collector.CHECKPOINTS[0])
        receipt['native']['uptime'] = -1.0
        with self.assertRaisesRegex(ValueError, 'native receipt uptime'):
            collector.validate_metadata(encoded(receipt))
        report = self.exercise(edit=self.mutate_receipt(lambda r: r['native'].update(uptime=-0.001)))
        self.assertFalse(report['evidence_complete'])
        self.assertEqual(report['sameState'], 'UNKNOWN')
        self.assertNotIn('sandbox-public-metadata-mac-before-resize.json', self.files)
        slot = next(row for row in report['metadata'] if row['checkpoint'] == collector.CHECKPOINTS[0])
        self.assertEqual(slot['sameState'], 'UNKNOWN')
        self.assertIs(slot['receipt_retained'], False)
        # The synthetic no-native UNKNOWN envelope has no freshness claim.
        absent = paired(collector.CASES[0], collector.CHECKPOINTS[0], observed=False)
        self.assertEqual(collector.validate_metadata(encoded(absent))['sameState'], 'UNKNOWN')

    def test_native_typed_font_variants_and_raw_cgcolor_unknown_remain_unqualified(self):
        def typed(r):
            attributes = r['native']['targets'][0]['runs'][0]['attributes']
            attributes['font']['name'] = '.AppleSystemUIFont Monospaced'
            attributes['accessibilityForegroundColor'] = {'state': 'UNKNOWN', 'type': 'unsupported'}
        report = self.exercise(edit=self.mutate_receipt(typed))
        self.assertTrue(report['evidence_complete'], report['errors'])
        self.assertIn(b'.AppleSystemUIFont Monospaced', self.files['sandbox-public-metadata-mac-before-resize.json'])
        def cg(r):
            r['native']['targets'][0]['runs'][0]['attributes']['foregroundColor'] = dict(state='OBSERVED', type='CGColor', components=[0, 0, 0, 1])
        report = self.exercise(edit=self.mutate_receipt(cg))
        self.assertFalse(report['evidence_complete'])
        self.assertNotIn('sandbox-public-metadata-mac-before-resize.json', self.files)

    def test_metadata_prefix_variants_preserve_validated_bytes_and_exact_name_diagnostics(self):
        for actual in ['mac-public-metadata-mac-before-resize_0_C17CB4FC-D16E-4FA8-9551-EDA6E400A4D2.json',
                       'mac-public-metadata-mac-before-resize (public diagnostic)',
                       'mac-public-metadata-mac-before-resize_01_unproved.json']:
            def edit(rows):
                for entry, _ in rows:
                    if entry.get('name') == 'mac-public-metadata-mac-before-resize':
                        entry.clear()
                        entry['suggestedHumanReadableName'] = actual
                        return
            report = self.exercise(edit=edit)
            self.assertFalse(report['evidence_complete'])
            self.assertIn('sandbox-public-metadata-mac-before-resize.json', self.files)
            row = next(r for r in report['metadata'] if r['checkpoint'] == 'mac-before-resize')
            self.assertEqual(row['presentation_binding'], 'UNKNOWN')
            self.assertEqual(row['presentation']['expected_name'], 'mac-public-metadata-mac-before-resize')
            field = row['presentation']['fields'][0]
            self.assertEqual(field['actual'], actual)
            self.assertEqual(field['utf8_bytes'], len(actual.encode()))
            self.assertEqual(field['sha256'], hashlib.sha256(actual.encode()).hexdigest())

    def test_conflicting_metadata_presentation_or_wrong_internal_checkpoint_is_rejected(self):
        def conflict(rows):
            rows[6][0]['suggestedHumanReadableName'] = 'mac-public-metadata-mac-minimum-window'
        report = self.exercise(edit=conflict)
        self.assertFalse(report['evidence_complete'])
        self.assertNotIn('sandbox-public-metadata-mac-before-resize.json', self.files)
        self.assertEqual(sum(row['receipt_retained'] for row in report['metadata']), 3)
        report = self.exercise(edit=self.mutate_receipt(lambda r: r.update(checkpoint='mac-minimum-window', sequence=2)))
        self.assertFalse(report['evidence_complete'])
        self.assertNotIn('sandbox-public-metadata-mac-before-resize.json', self.files)

    def test_duplicate_checkpoints_request_ids_and_stale_case_tokens_fail_closed(self):
        for action in [lambda rows: rows.append(copy.deepcopy(rows[6])),
                       self.mutate_receipt(lambda r: r.update(requestID=str(uuid.uuid5(uuid.NAMESPACE_URL, 'mac-before-resize')).upper()),
                                           checkpoint='mac-minimum-window'),
                       self.mutate_receipt(lambda r: (r.update(token='E996E346-3618-4B39-954E-1ABD7795010B'),
                                                     r['native'].update(token='E996E346-3618-4B39-954E-1ABD7795010B')),
                                           checkpoint='mac-minimum-window')]:
            report = self.exercise(edit=action)
            self.assertFalse(report['evidence_complete'])

    def test_manifest_count_bytes_escape_symlinks_and_hardlinks_fail_closed(self):
        for mode in ('attachment-count', 'manifest-oversize', 'attachment-path-escape',
                     'attachment-symlink', 'attachment-hardlink'):
            with self.subTest(mode=mode):
                report = self.exercise(mode=mode)
                self.assertFalse(report['evidence_complete'])
                self.assertEqual(len(self.calls), 3)

    def test_all_six_bounded_audit_checkpoint_receipts_remain_failures(self):
        def more(rows):
            for name in ('mac-minimum-long-text-en', 'mac-minimum-long-text-zh-Hans'):
                rows.append((dict(name='mac-audit-element'), ('Checkpoint: ' + name + '\nStrict audit failure').encode()))
        report = self.exercise(edit=more)
        self.assertTrue(report['evidence_complete'], report['errors'])
        self.assertEqual(report['strict_audit_callbacks'], 6)
        self.assertIs(report['auditQualified'], False)
        def excessive(rows):
            for _ in range(9):
                rows.append((dict(name='mac-audit-element'), b'Checkpoint: mac-before-resize\nStrict audit failure'))
        report = self.exercise(edit=excessive)
        self.assertFalse(report['evidence_complete'])
        self.assertTrue(any('per-checkpoint bounds' in error for error in report['errors']))

    def test_per_file_and_mac_allocation_cannot_silently_discard_emitted_frames(self):
        def large(rows):
            rows[0] = (rows[0][0], png(collector.FRAMES[0], collector.FILE_CAP + 1))
        report = self.exercise(edit=large)
        self.assertFalse(report['evidence_complete'])
        self.assertIn(collector.FRAMES[0], report['missing_frames'])
        def aggregate(rows):
            for n, (entry, data) in enumerate(rows):
                if entry.get('name') in collector.PNG_FRAMES:
                    rows[n] = (entry, png(entry['name'], collector.FILE_CAP))
        report = self.exercise(edit=aggregate)
        self.assertFalse(report['evidence_complete'])
        self.assertTrue(report['missing_frames'])
        self.assertTrue(any('allocation' in error for error in report['errors']))

    def test_missing_each_of_six_original_frames_and_four_metadata_receipts_is_explicit(self):
        for name in list(collector.FRAMES) + ['mac-public-metadata-' + c for c in collector.CHECKPOINTS]:
            report = self.exercise(edit=lambda rows: rows.__setitem__(slice(None), [r for r in rows if r[0].get('name') != name]))
            self.assertFalse(report['evidence_complete'])
            self.assertTrue(report['missing_frames'] or report['missing_metadata'])

    def test_lossless_cannot_fall_back_to_jpeg_or_expand_png_scope(self):
        for name in collector.PNG_FRAMES | {'mac-chinese-policy', 'mac-failure'}:
            def edit(rows):
                for n, (entry, _) in enumerate(rows):
                    if entry.get('name') == name:
                        rows[n] = (entry, b'\xff\xd8bad' if name in collector.PNG_FRAMES else png(name))
            report = self.exercise(edit=edit)
            self.assertFalse(report['evidence_complete'])

    def test_supporting_and_transition_numeric_booleans_and_acceptance_claims_reject(self):
        for field in ('contrast_qualified', 'reference_font_is_resolved_element_font', 'height_proxy_used_as_acceptance'):
            row = supporting('en', 'full')
            row[field] = 0
            with self.assertRaises(ValueError):
                collector.validate_supporting(encoded(row))
        for field in ('full_equality_verified', 'fixture_control_exact'):
            row = transition('en', 'copy-observed')
            row[field] = 1
            with self.assertRaises(ValueError):
                collector.validate_transition(encoded(row))
        row = transition('en', 'copy-observed')
        row['rendered_text_observation']['observations_qualify_pass'] = True
        with self.assertRaises(ValueError):
            collector.validate_transition(encoded(row))

    def test_original_command_boolean_missing_duplicate_and_changed_caps_reject(self):
        command, seconds = real_route.fixed_commands()['sandbox_test']
        start = b'BOUNDED_COMMAND_START ' + encoded(dict(command=command, seconds=seconds)) + b'\n'
        end = dict(command=command, timeout_seconds=seconds, state='completed', exit=65, cleanup_confirmed=True)
        for change in [lambda r: r.update(exit=True), lambda r: r.update(cleanup_confirmed=1),
                       lambda r: r.update(timeout_seconds=601), lambda r: r.update(command=command[:-1]),
                       lambda r: r.update(state='passed')]:
            row = copy.deepcopy(end)
            change(row)
            with self.assertRaises(ValueError):
                collector.command_outcome(start + b'BOUNDED_COMMAND_END ' + encoded(row), command, seconds)
        valid = start + b'BOUNDED_COMMAND_END ' + encoded(end) + b'\n'
        for data in (start, valid + valid):
            with self.assertRaises(ValueError):
                collector.command_outcome(data, command, seconds)

    def test_original_elapsed_boundary_and_failed_timeout_cleanup_codes_stay_actual(self):
        command, seconds = real_route.fixed_commands()['sandbox_test']
        start = b'BOUNDED_COMMAND_START ' + encoded(dict(command=command, seconds=seconds)) + b'\n'
        outcomes = [dict(command=command, timeout_seconds=seconds, state='completed', exit=65,
                         cleanup_confirmed=True, elapsed_seconds=seconds + 3),
                    dict(command=command, timeout_seconds=seconds, state='timed_out', exit=124,
                         cleanup_confirmed=True, elapsed_seconds=seconds + 3),
                    dict(command=command, timeout_seconds=seconds, state='cleanup_unconfirmed', exit=126,
                         original_exit=65, cleanup_confirmed=False, elapsed_seconds=seconds + 3)]
        for end in outcomes:
            data = start + b'BOUNDED_COMMAND_END ' + encoded(end)
            actual = collector.command_outcome(data, command, seconds)
            self.assertEqual(actual, end)
            end['elapsed_seconds'] = seconds + 3.01
            with self.assertRaises(ValueError):
                collector.command_outcome(start + b'BOUNDED_COMMAND_END ' + encoded(end), command, seconds)
        for elapsed in (-1, True, float('inf'), float('nan')):
            end = dict(outcomes[0], elapsed_seconds=elapsed)
            data = start + b'BOUNDED_COMMAND_END ' + json.dumps(end, allow_nan=True).encode()
            with self.assertRaises(ValueError):
                collector.command_outcome(data, command, seconds)
        report = self.exercise(mode='receipt-timeout')
        self.assertEqual(report['original_commands']['sandbox_test']['exit'], 124)
        self.assertEqual(report['original_commands']['sandbox_test']['state'], 'timed_out')
        self.assertFalse(report['evidence_complete'])
        self.assertEqual(report['sameState'], 'UNKNOWN')
        self.assertTrue(all(row['receipt_retained'] is False for row in report['metadata']))

    def test_existing_output_and_unknown_cli_arguments_never_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            previous = Path.cwd()
            try:
                os.chdir(temporary)
                Path(collector.OUT).mkdir(parents=True)
                Path(collector.OUT, 'old.json').write_bytes(b'{}')
                with self.assertRaises(ValueError):
                    collector.collect(runner=lambda *args, **kwargs: self.fail('Must never launch'), route=real_route)
                with self.assertRaises(ValueError):
                    collector.main(['--accept-all'])
            finally:
                os.chdir(previous)

    def test_schema_duplicate_keys_nonfinite_json_and_structural_bombs_reject(self):
        for data in (b'{"schema":1,"schema":1}', b'{"value":NaN}', b'x' * 32769):
            with self.assertRaises(ValueError):
                collector.validate_metadata(data)
        with self.assertRaises(ValueError):
            list(collector.walk({'deep': [[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[0]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]}))


if __name__ == '__main__':
    unittest.main()
