#!/usr/bin/env python3
"""Narrow diagnostic collector. Canonical UI/import acceptance remains unchanged.

Only public xcresult summary/attachment export is used. No simulator mutation.
A completed failed hosted run remains failed. Uncertainty retention is process-free.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid

from atomic_json import write_json
import diagnostic_phone_hosted_route as route
from ios_import_continuation import read_regular
from owned_process_barrier import blocked
from watch_process import execute

RESULT = Path('iOSUnitResults.xcresult')
OUT = Path('build/phone-hosted-evidence')
ATTACHMENTS = Path('build/phone-hosted-attachments')
TEST = 'QRPhoneResultTests/testLargestDynamicTypeFullTextAndActionsInBoundedPublicScrollPanes'
FIXTURE = 'unattached-child-public-geometry-v1'
PREFIX = 'phone-hosted-geometry-'
RECEIPT_LIMIT = 16 * 1024
RECEIPT_COUNT = 44
GEOMETRY_LIMIT = RECEIPT_COUNT * RECEIPT_LIMIT
RESULT_LIMIT = 64 * 1024 * 1024
NOT_RUN = ['full_phone_UI', 'Files_import_and_reopen', 'Photos_import_and_reopen',
           'paired_result_history_accessibility_audits', 'SE3', 'canonical_thirteen_row_qualification']
SIZES = [(320, 568), (375, 667), (440, 956), (568, 320)]
ACTIONS = {'text': ['history.result.copy', 'history.result.cancel'],
           'website': ['history.result.open', 'history.result.copy', 'history.result.cancel']}
PAYLOADS = {'text': 'BEGIN 👩🏽\u200d💻 e\u0301 你好\n' + 'Long readable Arabic العربية Hebrew עברית 🌈\n' * 80 + '最后一行 END',
            'website': 'https://example.com/' + 'long-readable-unicode-你好/' * 80}


def require(condition, message):
    if not condition: raise ValueError(message)


def strict_json(data):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'Duplicate JSON field')
            value[key] = item
        return value
    def bad_constant(value): raise ValueError('Nonfinite JSON constant')
    return json.loads(data, object_pairs_hook=unique, parse_constant=bad_constant)


def fields(value, expected):
    require(type(value) is dict and set(value) == set(expected), 'Geometry schema fields differ')


def number(value, nonnegative=False):
    require(type(value) in {int, float} and math.isfinite(value) and abs(value) <= 1e9 and
            (not nonnegative or value >= 0), 'Invalid bounded numeric geometry')


def point(value):
    fields(value, ['x', 'y'])
    for item in value.values(): number(item)


def size(value):
    fields(value, ['width', 'height'])
    for item in value.values(): number(item, True)


def rect(value):
    fields(value, ['x', 'y', 'width', 'height', 'min_x', 'min_y', 'max_x', 'max_y'])
    for item in value.values(): number(item)
    number(value['width'], True); number(value['height'], True)
    # Numeric values are observations, not pass criteria. Preserve rounding exactly.


def insets(value):
    fields(value, ['top', 'left', 'bottom', 'right'])
    for item in value.values(): number(item)


def boolean(value): require(type(value) is bool, 'Invalid observed boolean')


def traits(value):
    fields(value, ['content_size_category', 'display_scale', 'horizontal_size_class',
                   'vertical_size_class', 'idiom', 'layout_direction'])
    require(type(value['content_size_category']) is str and 0 < len(value['content_size_category']) <= 128,
            'Invalid public trait category')
    number(value['display_scale'], True)
    for key in ['horizontal_size_class', 'vertical_size_class', 'idiom', 'layout_direction']:
        require(type(value[key]) is int and -1 <= value[key] <= 6, 'Invalid public trait enum')


def font(value):
    if value is None: return
    fields(value, ['font_name', 'point_size', 'line_height', 'ascender', 'descender', 'leading',
                   'number_of_lines', 'line_break_mode', 'adjusts_for_category'])
    require(type(value['font_name']) is str and 0 < len(value['font_name']) <= 256, 'Invalid public font name')
    for key in ['point_size', 'line_height', 'ascender', 'descender', 'leading']: number(value[key])
    for key in ['number_of_lines', 'line_break_mode']:
        require(type(value[key]) is int and 0 <= value[key] <= 100, 'Invalid label enum/count')
    boolean(value['adjusts_for_category'])


def view(value, scroll=False):
    if value is None: return
    keys = ['frame', 'bounds', 'in_root', 'safe_area_insets', 'traits', 'window_attached',
            'superview_present', 'ambiguous_layout', 'hidden', 'in_window', 'window_bounds']
    fields(value, keys + (['scroll'] if scroll else []))
    for key in ['frame', 'bounds', 'in_root']: rect(value[key])
    insets(value['safe_area_insets']); traits(value['traits'])
    for key in ['window_attached', 'superview_present', 'ambiguous_layout', 'hidden']: boolean(value[key])
    for key in ['in_window', 'window_bounds']:
        require((value[key] is not None) == value['window_attached'], 'Window geometry/attachment differs')
        if value[key] is not None: rect(value[key])
    if scroll:
        item = value['scroll']
        fields(item, ['content_size', 'content_offset', 'content_inset', 'adjusted_content_inset',
                      'indicator_inset', 'inset_adjustment_behavior', 'zoom_scale', 'scroll_enabled'])
        size(item['content_size']); point(item['content_offset'])
        for key in ['content_inset', 'adjusted_content_inset', 'indicator_inset']: insets(item[key])
        require(type(item['inset_adjustment_behavior']) is int and 0 <= item['inset_adjustment_behavior'] <= 3,
                'Invalid scroll adjustment enum')
        number(item['zoom_scale'], True); boolean(item['scroll_enabled'])


def receipt(data):
    require(0 < len(data) <= RECEIPT_LIMIT, 'Geometry receipt exceeds16KiB')
    value = strict_json(data)
    fields(value, ['version', 'observations_qualify_pass', 'fixture', 'payload_kind', 'payload_utf16_length',
                   'payload_utf8_bytes', 'viewport', 'stage', 'target', 'full_text_size_that_fits',
                   'current_action_title_size_that_fits', 'host', 'result', 'host_traits', 'result_traits',
                   'parent_is_host', 'presented', 'text', 'actions', 'body', 'title', 'body_font', 'title_font', 'buttons'])
    require(type(value['version']) is int and value['version'] == 1 and
            value['observations_qualify_pass'] is False and value['fixture'] == FIXTURE,
            'Unknown geometry diagnostic protocol')
    kind = value['payload_kind']
    require(type(kind) is str and kind in ACTIONS, 'Unknown synthetic payload kind')
    payload = PAYLOADS[kind]
    require(type(value['payload_utf16_length']) is int and value['payload_utf16_length'] == len(payload.encode('utf-16-le')) // 2 and
            type(value['payload_utf8_bytes']) is int and value['payload_utf8_bytes'] == len(payload.encode()),
            'Wrong synthetic payload length')
    size(value['viewport']); dimensions = (value['viewport']['width'], value['viewport']['height'])
    require(dimensions in SIZES, 'Wrong fixture viewport')
    require(value['stage'] in ['panes', 'beginning', 'ending'] + ACTIONS[kind], 'Unknown pre-assertion stage')
    rect(value['target']); size(value['full_text_size_that_fits']); size(value['current_action_title_size_that_fits'])
    for key in ['host', 'result', 'body', 'title']: view(value[key])
    for key in ['text', 'actions']: view(value[key], True)
    for key in ['host_traits', 'result_traits']: traits(value[key])
    for key in ['parent_is_host', 'presented']: boolean(value[key])
    for key in ['body_font', 'title_font']: font(value[key])
    require(type(value['buttons']) is list and len(value['buttons']) == len(ACTIONS[kind]), 'Wrong action inventory')
    for item, identifier in zip(value['buttons'], ACTIONS[kind]):
        fields(item, ['identifier', 'view', 'in_actions', 'title_label', 'font'])
        require(item['identifier'] == identifier, 'Wrong action identifier/order')
        view(item['view']); view(item['title_label']); font(item['font'])
        if item['in_actions'] is not None: rect(item['in_actions'])
    return (kind, *dimensions, value['stage']), value


def expected_keys():
    return {(kind, width, height, stage) for kind in ACTIONS for width, height in SIZES
            for stage in ['panes', 'beginning', 'ending'] + ACTIONS[kind]}


def expected_command(device):
    return ['xcodebuild', 'test-without-building', '-project', 'QRCatcher.xcodeproj', '-scheme', 'QRCatcher',
            '-configuration', 'Debug', '-derivedDataPath', 'build/iOS', '-destination', 'platform=iOS Simulator,id=' + device,
            '-only-testing:QRCatcherTests', '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
            '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '90',
            '-maximum-test-execution-time-allowance', '120', '-resultBundlePath', str(RESULT), 'CODE_SIGNING_ALLOWED=NO']


def finalized_command(data, device):
    require(str(uuid.UUID(device)).upper() == device, 'Invalid exact Pro simulator UUID')
    text = data.decode()
    rows = [line[len('BOUNDED_COMMAND_END '):] for line in text.splitlines() if line.startswith('BOUNDED_COMMAND_END ')]
    # The unchanged hosted stage logs boot and bootstatus separately to stdout; ios-unit.log owns only the test invocation.
    require(len(rows) == 1 and text.rstrip().splitlines()[-1] == 'BOUNDED_COMMAND_END ' + rows[0], 'Missing finalized hosted command')
    value = strict_json(rows[0])
    require(value.get('command') == expected_command(device) and value.get('timeout_seconds') == 855 and
            value.get('state') == 'completed' and value.get('exit') in [0, 65] and
            type(value.get('exit')) is int and value.get('cleanup_confirmed') is True,
            'Hosted invocation is not exact completed cleanup-confirmed0/65')
    number(value.get('elapsed_seconds'), True)
    require(0 < value['elapsed_seconds'] <= 860, 'Hosted elapsed time exceeds unchanged cap')
    return value


def validate_summary(value, operation, device, now=None):
    now = time.time() if now is None else now
    keys = ['totalTestCount', 'passedTests', 'failedTests', 'skippedTests', 'expectedFailures']
    require(all(type(value.get(key)) is int and value[key] >= 0 for key in keys), 'Invalid hosted result counts')
    require(value['totalTestCount'] == 30 and value['passedTests'] + value['failedTests'] == 30 and
            value['skippedTests'] == value['expectedFailures'] == 0, 'Incomplete complete30-case hosted stage')
    expected = 'Passed' if operation['exit'] == 0 else 'Failed'
    require(value.get('result') == expected and (value['failedTests'] == 0) == (operation['exit'] == 0), 'Hosted result/exit differs')
    configurations = value.get('devicesAndConfigurations')
    require(type(configurations) is list and len(configurations) == 1 and
            configurations[0].get('device', {}).get('deviceId') == device and
            configurations[0]['device'].get('platform') == 'iOS Simulator', 'Wrong hosted result device')
    start, finish = value.get('startTime'), value.get('finishTime')
    require(all(type(item) in {int, float} and math.isfinite(item) and 0 < item < 1e10 for item in [start, finish]), 'Invalid hosted timestamps')
    require(now - operation['elapsed_seconds'] - 180 <= start < finish <= now + 5 and finish >= now - 180,
            'Stale/incomplete hosted result outside same-job invocation')
    return value


def checked(command, seconds, limit):
    require(not blocked(), 'Hosted collection blocked by cleanup uncertainty')
    code, output, operation = execute(command, seconds, output_limit=limit, tail_limit=limit, echo=False)
    require(code == 0 and operation.get('state') == 'completed' and operation.get('cleanup_confirmed') is True and not blocked(),
            'Bounded public xcresult collection did not complete cleanly')
    return output, operation


def result_fingerprint():
    require(RESULT.is_dir() and not RESULT.is_symlink() and RESULT.resolve() == Path.cwd() / RESULT,
            'Result is outside exact hosted path')
    rows = []; total = 0
    for path in sorted(RESULT.rglob('*')):
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode), 'Hosted result symlink rejected')
        if stat.S_ISDIR(info.st_mode): continue
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'Hosted result must contain independent regular files')
        total += info.st_size
        require(total <= RESULT_LIMIT and len(rows) < 2048, 'Hosted result fingerprint exceeds bounded allocation')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(64 * 1024): digest.update(chunk)
        require(path.stat().st_size == info.st_size, 'Hosted result changed while fingerprinting')
        rows.append({'path': path.relative_to(RESULT).as_posix(), 'bytes': info.st_size, 'sha256': digest.hexdigest()})
    require(any(row['path'] == 'Info.plist' for row in rows), 'Missing hosted result Info.plist')
    return {'files': len(rows), 'bytes': total, 'inventory_sha256': route.sha256(json.dumps(rows, sort_keys=True).encode())}


def collect_entries(manifest):
    require(type(manifest) is list and 0 < len(manifest) <= 128, 'Unknown bounded public attachment manifest')
    selected = []; seen_files = set(); geometry_owners = 0
    for test in manifest:
        require(type(test) is dict and type(test.get('attachments')) is list and len(test['attachments']) <= 128,
                'Unknown public per-test attachment manifest')
        owner = test.get('testIdentifier')
        owned = owner in [TEST, TEST + '()']
        found = False
        for entry in test['attachments']:
            require(type(entry) is dict, 'Invalid public attachment entry')
            name = entry.get('suggestedHumanReadableName', '')
            filename = entry.get('exportedFileName', '')
            if not (isinstance(name, str) and name.startswith(PREFIX)): continue
            require(owned, 'Geometry receipt came from wrong hosted test')
            found = True
            require(type(filename) is str and 0 < len(filename) <= 256 and Path(filename).name == filename and filename not in seen_files,
                    'Duplicate/escaping geometry attachment filename')
            seen_files.add(filename)
            data = read_regular(ATTACHMENTS / filename, RECEIPT_LIMIT)
            key, value = receipt(data)
            expected_name = PREFIX + key[0] + '-' + str(int(key[1])) + 'x' + str(int(key[2])) + '-' + key[3]
            # Xcode may suffix exported filenames, but the public human-readable attachment name is exact.
            require(re.fullmatch(re.escape(expected_name) + r'(?:\.json|_(?:0|[1-9][0-9]*)_[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\.json)?', name) is not None, 'Attachment name/geometry identity differs')
            selected.append((key, data, value, filename))
        if found: geometry_owners += 1
    require(geometry_owners == 1 and len(selected) == RECEIPT_COUNT and
            len({row[0] for row in selected}) == RECEIPT_COUNT and {row[0] for row in selected} == expected_keys(),
            'Missing, wrong or duplicate geometry combination/stage')
    require(sum(len(row[1]) for row in selected) <= GEOMETRY_LIMIT, 'Hosted geometry evidence budget exceeded')
    return selected


def retain_exact_bytes(path, data):
    """Keep validated native numeric serialization byte-for-byte, atomically."""
    require(0 < len(data) <= RECEIPT_LIMIT and not path.exists() and not path.is_symlink(), 'Invalid bounded receipt destination')
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    root = Path.cwd()
    require(not OUT.exists() and not OUT.is_symlink(), 'Hosted diagnostic output must be new')
    OUT.mkdir(parents=True)
    record = {'version': 1, 'diagnostic_only': True, 'release_qualification': False,
              'phases': {name: 'NOT RUN' for name in NOT_RUN}, 'geometry_observations_qualify_pass': False,
              'hosted_result': str(RESULT), 'required_test': TEST, 'receipts': []}
    try:
        identity = route.current_identity()
        require(identity['job'] == 'platform' and identity['scope'] == 'iphone_pro', 'Wrong hosted collection job/scope')
        initial = route.retained_initial_record(identity)
        record['initial_source_proof'] = initial
        record['owned_cleanup_uncertainty_observed'] = blocked()
        if blocked():
            record.update(collection='NOT RUN: cleanup uncertainty', hosted_outcome='UNKNOWN', acceptance=False)
            write_json(OUT / 'manifest.json', record, limit=64 * 1024)
            return 0
        device = os.environ.get('SIMULATOR_ID', '')
        log = read_regular(Path('ios-unit.log'), 17 * 1024 * 1024)
        operation = finalized_command(log, device)
        before = result_fingerprint()
        summary_raw, summary_operation = checked(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(RESULT)], 15, 128 * 1024)
        summary = validate_summary(strict_json(summary_raw), operation, device)
        require(not ATTACHMENTS.exists() and not ATTACHMENTS.is_symlink(), 'Attachment export path is stale/aliased')
        _, export_operation = checked(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', str(RESULT), '--output-path', str(ATTACHMENTS)], 90, 64 * 1024)
        manifest_data = read_regular(ATTACHMENTS / 'manifest.json', 128 * 1024)
        selected = collect_entries(strict_json(manifest_data))
        require(result_fingerprint() == before, 'Hosted xcresult changed during public collection')
        require(route.retained_initial_record(identity) == initial, 'Initial source receipt changed during collection')
        record.update(collection='COMPLETE', hosted_outcome=summary['result'], acceptance=False,
                      source_sha=identity['source_sha'], source_tree=initial['tested_tree'],
                      run_id=identity['run_id'], run_attempt=identity['run_attempt'], device=device,
                      hosted_operation=operation, summary=summary, result_fingerprint=before,
                      public_collection_operations=[summary_operation, export_operation],
                      attachment_manifest_sha256=route.sha256(manifest_data),
                      fresh_source_readback_performed=False,
                      provenance_limit='Same-job sealed initial source and exact finalized hosted invocation/result; no compiled-binary attestation or release qualification')
        # Validate the whole set before copying any geometry receipt; no partial invalid proof.
        for key, data, value, original in sorted(selected):
            name = PREFIX + key[0] + '-' + str(int(key[1])) + 'x' + str(int(key[2])) + '-' + key[3] + '.json'
            retain_exact_bytes(OUT / name, data)
            retained = read_regular(OUT / name, RECEIPT_LIMIT)
            record['receipts'].append({'name': name, 'key': list(key), 'source_attachment': original,
                                       'source_sha256': route.sha256(data), 'retained_sha256': route.sha256(retained),
                                       'bytes': len(retained), 'observations_qualify_pass': False})
        write_json(OUT / 'hosted-summary.json', summary, limit=128 * 1024)
        (OUT / 'ios-unit.log').write_bytes(log[-64 * 1024:])
        write_json(OUT / 'manifest.json', record, limit=64 * 1024)
        return 0
    except Exception as error:
        record.update(collection='REJECTED', acceptance=False, error=str(error)[:1800],
                      owned_cleanup_uncertainty_observed=blocked())
        write_json(OUT / 'manifest.json', record, limit=64 * 1024)
        print('HOSTED_GEOMETRY_REJECTED ' + str(error), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
