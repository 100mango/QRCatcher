#!/usr/bin/env python3
"""Closed two-case Mac diagnostic retention, never an audit pass or exemption.

Only public offline xcresulttool reads are launched, through the existing owned
process runner. A cleanup stop signal, including one in a retained command
receipt, makes this a pure-file failure collector. No app or simulator launches,
source readback commands, screenshot conversions, retries or raw bundle uploads.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time

import mac_public_metadata_schema as schema
from owned_process_barrier import blocked
from watch_process import execute

SCOPE_CAP = 3_000_000
WHOLE_CAP = 20_000_000
FILE_CAP = 800 * 1024
JSON_CAP = 128 * 1024
REPORT_RESERVE = 64 * 1024
EXPORT_SECONDS = 180
RESULT = 'MacSandboxResults.xcresult'
OUT = 'build/mac-evidence'
STAGING = 'build/mac-public-metadata-attachments'
CASES = tuple(schema.CASES)
CHECKPOINTS = tuple(c for case in CASES for c in schema.CASES[case])
FRAMES = CHECKPOINTS + ('mac-minimum-long-text-en', 'mac-minimum-long-text-zh-Hans')
PNG_FRAMES = set(FRAMES) - {'mac-chinese-policy'}
NAMES = set(FRAMES) | {'mac-failure', 'mac-audit-element',
                         'mac-supporting-text-layout', 'mac-payload-transition'}
NAMES |= {'mac-public-metadata-' + c for c in CHECKPOINTS}
UUID_PATTERN = r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}'
LOG_CAP = 18 * 1024 * 1024
LOG_TAIL = 128 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def small_string(value, limit=256):
    return (type(value) is str and 0 < len(value.encode('utf-8')) <= limit and
            all(c.isprintable() for c in value))


def read_regular(path, root, limit, tail=False):
    """No alias, symlink, hardlink, special file or moving-file evidence."""
    path = Path(path)
    require(path.absolute().is_relative_to(root) and path.resolve(strict=True) == path.absolute(),
            'Redirected evidence path: ' + path.name)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                0 < info.st_size <= limit, 'Unbounded or nonregular evidence: ' + path.name)
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            if tail:
                stream.seek(max(0, info.st_size - LOG_TAIL))
            data = stream.read(limit + 1 if not tail else LOG_TAIL)
        after = os.fstat(descriptor)
        current = path.lstat()
        signature = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink,
                               s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(signature(info) == signature(after) == signature(current) and
                len(data) == (min(info.st_size, LOG_TAIL) if tail else info.st_size),
                'Evidence changed during read: ' + path.name)
        return data
    finally:
        os.close(descriptor)


def walk(value, depth=0, counter=None):
    if counter is None:
        counter = [0]
    counter[0] += 1
    require(depth <= 32 and counter[0] <= 8192, 'Unbounded structured evidence topology')
    if type(value) is dict:
        yield value
        for child in value.values():
            yield from walk(child, depth + 1, counter)
    elif type(value) is list:
        for child in value:
            yield from walk(child, depth + 1, counter)


def attachment_records(value):
    rows = [row for row in walk(value) if 'exportedFileName' in row]
    require(len(rows) <= 128, 'Attachment count exceeds 128')
    files = set()
    for row in rows:
        name = row['exportedFileName']
        require(small_string(name) and Path(name).name == name and
                name not in {'.', '..', 'manifest.json'} and '/' not in name and '\\' not in name,
                'Unsafe exported attachment filename')
        require(name not in files, 'Duplicate exported attachment filename')
        files.add(name)
    return rows


def presentation_name(entry):
    """Exact metadata names; only already-observed screenshot decoration.

    The new metadata exporter presentation has never been attested natively.
    In particular no guessed JSON/text decoration can qualify its identity.
    """
    found = set()
    for key in ('name', 'suggestedHumanReadableName', 'exportedFileName'):
        value = entry.get(key)
        if value is None:
            continue
        require(small_string(value), 'Unbounded or unsafe attachment presentation')
        if value in NAMES:
            found.add(value)
            continue
        match = re.fullmatch('(' + '|'.join(re.escape(n) for n in sorted(set(FRAMES) | {'mac-failure'})) +
                             r')_(?:0|[1-9][0-9]*)_' + UUID_PATTERN +
                             r'\.(?:png|jpeg|jpg)', value)
        if match:
            found.add(match.group(1))
    require(len(found) <= 1, 'Conflicting recognized attachment identities')
    return next(iter(found), None)


def presentation_diagnostic(entry, expected):
    result = {'expected_name': expected, 'fields': []}
    for key in ('name', 'suggestedHumanReadableName', 'exportedFileName'):
        if key in entry:
            actual = entry[key]
            require(small_string(actual), 'Unsafe attachment presentation diagnostic')
            data = actual.encode()
            result['fields'].append({'key': key, 'actual': actual, 'utf8_bytes': len(data),
                                     'sha256': hashlib.sha256(data).hexdigest()})
    return result


def owned_prefix(entry):
    """A prefix permits validation/retention only, never identity acceptance."""
    prefixes = {'mac-public-metadata-', 'mac-audit-element',
                'mac-supporting-text-layout', 'mac-payload-transition'}
    found = set()
    for key in ('name', 'suggestedHumanReadableName'):
        value = entry.get(key)
        if value is not None:
            require(small_string(value), 'Unsafe attachment presentation')
            found.update(p for p in prefixes if value.startswith(p))
    require(len(found) <= 1, 'Conflicting owned attachment kind prefixes')
    return next(iter(found), None)


def command_outcome(data, command, seconds):
    starts, ends = [], []
    for line in data.decode('utf-8', errors='replace').splitlines():
        if line.startswith('BOUNDED_COMMAND_START '):
            starts.append(schema.decode(line[len('BOUNDED_COMMAND_START '):].encode(), 8192))
        if line.startswith('BOUNDED_COMMAND_END '):
            ends.append(schema.decode(line[len('BOUNDED_COMMAND_END '):].encode(), 8192))
    require(len(starts) == len(ends) == 1, 'Missing or ambiguous original bounded command outcome')
    start, end = starts[0], ends[0]
    require(type(start) is dict and set(start) == {'command', 'seconds'} and
            start['command'] == command and type(start['seconds']) is int and
            start['seconds'] == seconds, 'Original command START differs from fixed argv/cap')
    keys = {'command', 'timeout_seconds', 'cleanup_confirmed', 'state', 'exit',
            'output_bytes', 'elapsed_seconds', 'original_exit', 'cleanup_error'}
    require(type(end) is dict and set(end) <= keys and
            {'command', 'state', 'exit', 'cleanup_confirmed'} <= set(end),
            'Invalid original command END shape')
    require(end['command'] == command and type(end['exit']) is int and
            -128 <= end['exit'] <= 255 and type(end['cleanup_confirmed']) is bool,
            'Original command END identity or outcome differs')
    if 'timeout_seconds' in end:
        require(type(end['timeout_seconds']) is int and end['timeout_seconds'] == seconds,
                'Original command END cap differs')
    for key in ('output_bytes', 'original_exit'):
        if key in end:
            require(type(end[key]) is int and (-128 <= end[key] <= 255 if key == 'original_exit'
                                             else 0 <= end[key] <= LOG_CAP),
                    'Invalid original command numeric outcome')
    if 'elapsed_seconds' in end:
        require(schema.number(end['elapsed_seconds']) and 0 <= end['elapsed_seconds'] <= seconds + 3,
                'Invalid original command elapsed time')
    if 'cleanup_error' in end:
        require(small_string(end['cleanup_error'], 1024), 'Invalid cleanup error')
    states = {'completed', 'timed_out', 'output_limit', 'cleanup_unconfirmed',
              'blocked_owned_process_cleanup_unconfirmed'}
    require(end['state'] in states, 'Unknown original command state')
    if end['state'] == 'completed':
        require(end['cleanup_confirmed'] is True and end['exit'] not in {124, 125, 126},
                'Contradictory completed command outcome')
    elif end['state'] == 'timed_out':
        require(end['exit'] == 124 and end['cleanup_confirmed'] is True, 'Contradictory timeout')
    elif end['state'] == 'output_limit':
        require(end['exit'] == 125 and end['cleanup_confirmed'] is True, 'Contradictory output cap')
    else:
        require(end['exit'] == 126 and end['cleanup_confirmed'] is False, 'Contradictory cleanup stop')
    return end


def result_counts(value, count):
    require(type(value) is dict, 'Missing XCTest summary')
    for key in ('totalTestCount', 'passedTests', 'failedTests', 'skippedTests', 'expectedFailures'):
        require(type(value.get(key)) is int and 0 <= value[key] <= count,
                'Invalid XCTest numeric test count')
    require(value['totalTestCount'] == count and value['skippedTests'] == 0 and
            value['expectedFailures'] == 0 and value['passedTests'] + value['failedTests'] == count,
            'XCTest scope differs or required cases did not execute')
    require(value.get('result') == ('Failed' if value['failedTests'] else 'Passed'),
            'XCTest summary result/count disagreement')


def validate_summary(value, hosted=False, device=None):
    count = 26 if hosted else 2
    result_counts(value, count)
    require(value.get('title') == ('Test - QRCatcherMac' if hosted else 'Test - QRCatcherMacSandbox'),
            'Wrong XCTest target/scheme summary')
    configurations = value.get('devicesAndConfigurations')
    require(type(configurations) is list and len(configurations) == 1 and
            type(configurations[0]) is dict, 'Expected one native Mac device/configuration')
    actual = configurations[0].get('device')
    require(type(actual) is dict and actual.get('architecture') == 'arm64' and
            actual.get('platform') == 'macOS' and small_string(actual.get('deviceId'), 128),
            'Result device is not exact arm64 macOS')
    for field in ('deviceName', 'modelName', 'osBuildNumber', 'osVersion'):
        require(small_string(actual.get(field), 128), 'Missing actual native Mac device provenance')
    if device is not None:
        require(actual == device, 'Hosted/sandbox device provenance differs')
    for key in ('passedTests', 'failedTests', 'skippedTests', 'expectedFailures'):
        require(type(configurations[0].get(key)) is int and configurations[0][key] == value[key],
                'Device/configuration test counts disagree')
    require(schema.number(value.get('startTime')) and schema.number(value.get('finishTime')) and
            0 <= value['finishTime'] - value['startTime'] <= (1155 if hosted else 600),
            'Invalid or out-of-budget XCTest execution times')
    warnings = value.get('runtimeWarnings')
    require(type(warnings) is list and len(warnings) <= 128, 'Unbounded runtime warnings')
    failures = value.get('testFailures')
    require(type(failures) is list and len(failures) <= 128, 'Unbounded strict XCTest failure summary')
    if not hosted:
        for row in failures:
            require(type(row) is dict and row.get('targetName') == 'QRCatcherMacUITests',
                    'Strict failure belongs to another target')
            case = case_identity(row.get('testIdentifierString'), row.get('testIdentifierURL'))
            require(small_string(row.get('testName')) and case in CASES,
                    'Invalid failure presentation or identity')
    return actual


def validate_launch_context(data, root):
    """Original public launch receipts, not a fresh lookup or token/PID pair."""
    rows = []
    bundle = str(root / 'build/MacSandbox/Build/Products/Debug/QRCatcherMac.app')
    executable = bundle + '/Contents/MacOS/QRCatcherMac'
    for line in data.decode('utf-8', errors='replace').splitlines():
        if not line.startswith('RUNNING_APP_PROVENANCE: '):
            continue
        require(len(rows) < 32, 'Unbounded original launch provenance rows')
        row = schema.decode(line[len('RUNNING_APP_PROVENANCE: '):].encode(), 8192)
        schema.exact(row, ['code_payload_sha256', 'pid', 'actual_bundle', 'actual_executable',
                           'expected_bundle', 'executable_sha256', 'product_app_sandbox'])
        require(row['actual_bundle'] == row['expected_bundle'] == bundle and
                row['actual_executable'] == executable, 'Original launched app is not the adjacent fixed Debug product')
        require(schema.integer(row['pid'], 1, 2 ** 31 - 1) and row['product_app_sandbox'] is True,
                'Invalid original launch PID or sandbox state')
        hashes = row['code_payload_sha256']
        require(type(hashes) is dict and {'QRCatcherMac', 'QRCatcherMac.debug.dylib'} <= set(hashes) <=
                {'QRCatcherMac', 'QRCatcherMac.debug.dylib', '__preview.dylib'},
                'Original launch lacks exact executable/debug-dylib identities')
        require(all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) for value in hashes.values()) and
                row['executable_sha256'] == hashes['QRCatcherMac'], 'Invalid actual executable/debug-dylib hashes')
        require(not rows or row['code_payload_sha256'] == rows[0]['code_payload_sha256'],
                'Actual Debug code payload changed across legitimate launches')
        rows.append(row)
    return rows


def case_identity(identifier, url):
    matches = [c for c in CASES if identifier in {'QRCatcherMacUITests/' + c,
                                                'QRCatcherMacUITests/' + c + '()'}]
    require(len(matches) == 1 and url == 'test://com.apple.xcode/QRCatcher/' +
            'QRCatcherMacUITests/QRCatcherMacUITests/' + matches[0],
            'Wrong exact XCTest case identifier/qualified URL')
    return matches[0]


def validate_tests(value, summary):
    require(type(value) is dict and type(value.get('testNodes')) is list,
            'Missing test-results leaf tree')
    rows = [row for row in walk(value) if row.get('nodeType') == 'Test Case']
    require(len(rows) == 2, 'Result must contain exactly two native UI test leaves')
    seen, normalized = set(), []
    for row in rows:
        case = case_identity(row.get('nodeIdentifier'), row.get('nodeIdentifierURL'))
        require(case not in seen and small_string(row.get('name')) and
                row.get('result') in {'Passed', 'Failed'}, 'Duplicate, missing or invalid selected test leaf')
        require(not row.get('children'), 'Selected test leaf contains another test subtree')
        seen.add(case)
        normalized.append({'case': case, 'display_name': row['name'], 'result': row['result'],
                           'nodeIdentifier': row['nodeIdentifier'], 'nodeIdentifierURL': row['nodeIdentifierURL'],
                           'presentation_binding': 'OBSERVED' if row['name'] == case + '()' else 'UNKNOWN',
                           'display_name_utf8_bytes': len(row['name'].encode()),
                           'display_name_sha256': hashlib.sha256(row['name'].encode()).hexdigest()})
    require(seen == set(CASES) and sum(r['result'] == 'Passed' for r in normalized) == summary['passedTests'] and
            sum(r['result'] == 'Failed' for r in normalized) == summary['failedTests'],
            'Selected test leaves/summary results differ')
    return normalized


def validate_metadata(data):
    """Use the unchanged schema. Offline reads cannot reobserve request clocks."""
    value = schema.decode(data)
    require(type(value) is dict and value.get('case') in schema.CASES and
            value.get('checkpoint') in schema.CASES[value['case']], 'Wrong internal metadata case/checkpoint')
    native = value.get('native')
    uptime = native.get('uptime') if type(native) is dict else 0
    require(schema.number(uptime) and uptime >= 0, 'Invalid internal native receipt uptime')
    # Equality provides no new freshness claim. The native source's synchronous
    # <=5s guard remains the only observed freshness envelope in these bytes.
    return schema.validate_paired_receipt(data, token=value.get('token'), case=value['case'],
                                         checkpoint=value['checkpoint'], sequence=value.get('sequence'),
                                         request_id=value.get('requestID'), request_time=uptime, now=uptime)


def selected_display_case(value, locale):
    case = 'testChineseCriticalFlow' if locale == 'zh-Hans' else 'testNativeWindowResizeKeepsFullActionTitles'
    require(small_string(value) and case in re.split(r'[^A-Za-z0-9_]+', value) and
            sum(c in re.split(r'[^A-Za-z0-9_]+', value) for c in CASES) == 1,
            'Supporting receipt case differs from exact selected locale')


def validate_supporting(data):
    value = schema.decode(data, 4096)
    schema.exact(value, ['locale', 'phase', 'case', 'window', 'roles', 'contrast_qualified',
                         'reference_font_is_resolved_element_font', 'height_proxy_used_as_acceptance'])
    require(value['locale'] in {'en', 'zh-Hans'} and value['phase'] in {'full', 'minimum-long-content'},
            'Unknown supporting text checkpoint')
    selected_display_case(value['case'], value['locale'])
    require(value['contrast_qualified'] is False and value['reference_font_is_resolved_element_font'] is False and
            value['height_proxy_used_as_acceptance'] is False, 'Supporting reference font cannot qualify audit/layout')
    schema.frame(value['window'])
    count = 1 if value['phase'] == 'full' else 2
    texts = (['Links open only when you choose Open in Browser.', f'{count} saved on this Mac']
             if value['locale'] == 'en' else ['只有点击「在浏览器中打开」才会打开链接。', f'本机已保存 {count} 条记录'])
    require(type(value['roles']) is list and len(value['roles']) == 2, 'Missing supporting roles')
    for row, role, text in zip(value['roles'], ('link-policy', 'saved-count'), texts):
        schema.exact(row, ['role', 'text', 'frame', 'body_measurement_height', 'reference_body_font', 'reference_body_point_size'])
        require(row['role'] == role and row['text'] == text and small_string(row['reference_body_font'], 128),
                'Changed supporting text or invalid reference font presentation')
        schema.frame(row['frame'])
        require(row['frame'][2] > 0 and row['frame'][3] > 0 and schema.contained(value['window'], row['frame']) and
                schema.number(row['body_measurement_height']) and row['body_measurement_height'] >= 0 and
                schema.number(row['reference_body_point_size']) and row['reference_body_point_size'] > 0,
                'Invalid supporting numeric/geometry observation')
    return value


def validate_transition(data):
    value = schema.decode(data, 4096)
    required = {'locale', 'phase', 'wrapper_before', 'copy_before', 'wrapper_identity_refresh_scope',
                'raster_width', 'raster_height', 'clipboard_tiff_bytes', 'expected_payload_utf8_bytes',
                'expected_payload_sha256', 'clipboard_tiff_sha256', 'fixture_control_exact', 'full_equality_verified'}
    optional = {'wrapper_after', 'copy_after_sha256', 'copy_after_utf8_bytes', 'rendered_text_observation'}
    require(type(value) is dict and required <= set(value) <= required | optional, 'Unknown transition receipt keys')
    require(value['locale'] in {'en', 'zh-Hans'} and value['phase'] in {'prepared', 'copy-observed'} and
            value['wrapper_identity_refresh_scope'] == 'selectable Text only', 'Wrong payload transition checkpoint/scope')
    for field in ('full_equality_verified', 'fixture_control_exact'):
        require(type(value[field]) is bool, 'Transition outcome must be a real boolean')
    for field in ('raster_width', 'raster_height', 'clipboard_tiff_bytes', 'expected_payload_utf8_bytes'):
        require(schema.integer(value[field], 1), 'Invalid actual transition byte/raster evidence')
    for field in ('expected_payload_sha256', 'clipboard_tiff_sha256', 'copy_after_sha256'):
        if field in value:
            require(type(value[field]) is str and re.fullmatch('[0-9a-f]{64}', value[field]), 'Invalid transition SHA256')
    before = ('https://example.com/qrcatcher?source=golden' if value['locale'] == 'en' else 'QRCatcher 你好 🌈 123')
    require(value['wrapper_before'] == value['copy_before'] == before, 'Wrong original payload/Copy state')
    if value['phase'] == 'prepared':
        require(value['full_equality_verified'] is False and not (set(value) & optional), 'Preparation cannot qualify full equality')
    else:
        require({'wrapper_after', 'copy_after_sha256', 'copy_after_utf8_bytes', 'rendered_text_observation'} <= set(value),
                'Missing copy-observed transition fields')
        require(type(value['wrapper_after']) is str and len(value['wrapper_after'].encode()) <= 4096 and
                schema.integer(value['copy_after_utf8_bytes'], 0), 'Invalid transition readback')
        observed = value['rendered_text_observation']
        schema.exact(observed, ['wrapper_hittable', 'wrapper_enabled', 'direct_child_count',
                                'rendered_static_text_count', 'rendered_identifier', 'rendered_frame',
                                'wrapper_interaction_required', 'observations_qualify_pass'])
        for key in ('wrapper_hittable', 'wrapper_enabled', 'wrapper_interaction_required', 'observations_qualify_pass'):
            require(type(observed[key]) is bool, 'Invalid rendered transition boolean')
        require(observed['rendered_identifier'] == '' and observed['wrapper_interaction_required'] is False and
                observed['observations_qualify_pass'] is False, 'Rendered transition cannot qualify acceptance')
        for key in ('direct_child_count', 'rendered_static_text_count'):
            require(schema.integer(observed[key], 0, 256), 'Invalid rendered transition child count')
        schema.frame(observed['rendered_frame'])
        if value['full_equality_verified']:
            after = value['wrapper_after'].encode()
            require(value['fixture_control_exact'] is True and hashlib.sha256(after).hexdigest() == value['expected_payload_sha256'] and
                    len(after) == value['expected_payload_utf8_bytes'] == value['copy_after_utf8_bytes'] and
                    value['copy_after_sha256'] == value['expected_payload_sha256'], 'Claimed transition equality lacks actual readback')
    return value


def image_dimensions(data, name):
    if name in PNG_FRAMES:
        require(len(data) > 24 and data.startswith(b'\x89PNG\r\n\x1a\n') and data[12:16] == b'IHDR',
                'Required native lossless frame is not PNG')
        dimensions = list(struct.unpack('>II', data[16:24]))
        require(all(0 < n <= 4096 for n in dimensions), 'Invalid native image dimensions')
        return dimensions
    require(data.startswith(b'\xff\xd8'), 'Only fixed lossless frames may use PNG')
    return None


def collect(runner=None, clock=None, route=None):
    runner = execute if runner is None else runner
    clock = time.monotonic if clock is None else clock
    if route is None:
        import diagnostic_mac_public_metadata_route as route
    root = Path.cwd().resolve()
    build = root / 'build'
    require(not build.is_symlink() and (not build.exists() or build.is_dir()), 'Redirected build directory')
    build.mkdir(exist_ok=True)
    out = root / OUT
    require(not out.is_symlink() and (not out.exists() or out.is_dir() and not any(out.iterdir())),
            'Evidence destination is redirected or already populated; retries forbidden')
    out.mkdir(exist_ok=True)
    report = {'schema': 1, 'diagnostic_only': True, 'release_qualification': False,
              'auditQualified': False, 'contrastQualified': False, 'sameState': 'UNKNOWN',
              'evidence_complete': False, 'selected_cases': list(CASES), 'metadata_checkpoints': list(CHECKPOINTS),
              'required_frames': list(FRAMES), 'scope_limit_bytes': SCOPE_CAP, 'whole_run_limit_bytes': WHOLE_CAP,
              'retention_days': 1, 'files': [], 'operations': [], 'original_commands': {}, 'errors': [],
              'metadata': [{'case': case, 'checkpoint': checkpoint, 'sequence': index + 1,
                            'sameState': 'UNKNOWN', 'presentation_binding': 'UNKNOWN', 'receipt_retained': False,
                            'reason': 'missing-or-uncollected-receipt', 'auditQualified': False, 'contrastQualified': False}
                           for case in CASES for index, checkpoint in enumerate(schema.CASES[case])],
              'missing_metadata': list(CHECKPOINTS), 'missing_frames': list(FRAMES),
              'missing_supporting': [locale + '-' + phase for locale in ('en', 'zh-Hans')
                                     for phase in ('full', 'minimum-long-content')],
              'missing_transitions': [locale + '-' + phase for locale in ('en', 'zh-Hans')
                                      for phase in ('prepared', 'copy-observed')],
              'launch_context': {'state': 'UNKNOWN', 'reason': 'missing-or-uncollected-original-launch-receipts', 'rows': [],
                                 'checkpoint_pid_pairing': 'UNKNOWN: original launch rows have no per-checkpoint token/PID link'},
              'screenshots': [], 'strict_audit_callbacks': 0,
              'offline_freshness_revalidated': False,
              'freshness_limit': 'Native synchronous source guard is the observed five-second envelope; offline export cannot reobserve request time or now'}
    used, stopped, started = 0, blocked(), clock()

    def error(message):
        if len(report['errors']) < 63:
            report['errors'].append(str(message)[:512])
        elif len(report['errors']) == 63:
            report['errors'].append('Additional errors omitted at bounded report cap')

    def retain(name, data, cap=FILE_CAP):
        nonlocal used
        require(Path(name).name == name and not (out / name).exists() and not (out / name).is_symlink(),
                'Duplicate or unsafe retained filename')
        require(type(data) is bytes and 0 < len(data) <= cap and len(report['files']) < 120,
                'Evidence file/count cap exceeded')
        require(used + len(data) <= SCOPE_CAP - REPORT_RESERVE, 'Evidence exceeds Mac allocation; emitted evidence cannot be silently omitted')
        with (out / name).open('xb') as stream:
            stream.write(data)
        used += len(data)
        row = {'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        report['files'].append(row)
        return row

    def run(command, seconds):
        nonlocal stopped
        now = clock()
        require(schema.number(now) and schema.number(started) and now >= started,
                'Invalid monotonic offline export clock')
        remaining = EXPORT_SECONDS - (now - started)
        require(not stopped and not blocked(), 'Owned cleanup uncertainty forbids further process launch')
        require(remaining > 0, 'Total offline export time budget exhausted')
        actual_cap = min(seconds, remaining)
        code, output, operation = runner(command, actual_cap, output_limit=JSON_CAP,
                                         tail_limit=JSON_CAP, echo=False)
        require(type(operation) is dict, 'Invalid offline operation record type')
        if operation.get('cleanup_confirmed') is not True or code == 126 or blocked():
            stopped = True
        # Do not let an invalid operator record contaminate the durable failure
        # report with nonfinite/unbounded/private values.
        operation = schema.decode(json.dumps(operation, allow_nan=False).encode(), 8192)
        list(walk(operation))
        report['operations'].append(operation)
        require(code == 0 and operation.get('state') == 'completed' and
                operation.get('cleanup_confirmed') is True and not stopped,
                'Offline result command failed or owned cleanup is uncertain')
        require(type(operation) is dict and operation.get('command') == command and
                schema.number(operation.get('timeout_seconds')) and operation['timeout_seconds'] == actual_cap and
                type(code) is int and type(operation.get('exit')) is int and operation['exit'] == code and
                schema.integer(operation.get('output_bytes'), 0, JSON_CAP) and
                schema.number(operation.get('elapsed_seconds')) and 0 <= operation['elapsed_seconds'] <= actual_cap + 3,
                'Offline result operation identity/cap/numeric receipt differs')
        require(type(output) is str and len(output.encode()) <= JSON_CAP, 'Offline result output exceeds 128 KiB')
        return output.encode()

    try:
        initial = route.retained_initial_record(route.current_identity())
        require(initial.get('job') == 'platform' and initial.get('scope') == 'macos' and
                initial.get('diagnostic_only') is True and initial.get('release_qualification') is False and
                initial.get('selected_ui_cases') == list(CASES) and initial.get('metadata_checkpoints') == list(CHECKPOINTS),
                'Initial seal is not the fixed two-case Mac metadata route')
        report['provenance'] = initial
        retain('public-metadata-provenance.json', (json.dumps(initial, allow_nan=False, indent=2) + '\n').encode(), 8192)
        fixed = route.fixed_commands()
        for key, filename in [('sandbox_build', 'mac-sandbox-build.log'), ('sandbox_test', 'mac-sandbox-test.log')]:
            path = root / filename
            if not path.exists() and not path.is_symlink():
                error('Missing original command log: ' + filename)
                stopped = True
                continue
            data = read_regular(path, root, LOG_CAP)
            retain(filename.replace('.log', '-tail.log'), data[-LOG_TAIL:], LOG_TAIL)
            try:
                command, seconds = fixed[key]
                outcome = command_outcome(data, command, seconds)
                report['original_commands'][key] = outcome
                if outcome['cleanup_confirmed'] is not True or outcome['exit'] == 126:
                    stopped = True
                if key == 'sandbox_build' and outcome['exit'] != 0:
                    stopped = True
                    error('Original sandbox build did not complete successfully')
                if key == 'sandbox_test':
                    try:
                        rows = validate_launch_context(data, root)
                        report['launch_context'].update(rows=rows, state='OBSERVED' if rows else 'UNKNOWN',
                                                       reason='original-public-launch-receipts' if rows else 'missing-original-launch-receipts',
                                                       source_sha=initial['source_sha'], tested_tree=initial['tested_tree'],
                                                       run_id=initial['run_id'], run_attempt=initial['run_attempt'],
                                                       ref=initial['ref'], workflow_ref=initial['workflow_ref'])
                        if not rows:
                            error('Original running-app launch context is UNKNOWN: no bounded launch receipt')
                    except (ValueError, TypeError, KeyError) as failure:
                        report['launch_context']['reason'] = 'invalid-original-launch-receipts'
                        error(failure)
            except (ValueError, TypeError, KeyError) as failure:
                stopped = True
                error(failure)
        for relative, cap in [('build/owned-process-cleanup.json', 2048),
                              ('build/fixture-query-inflight.json', 2048),
                              ('build/mac-sandbox-entitlements.plist', 16384),
                              ('build/mac-sandbox-signature.txt', 16384),
                              ('build/native-release-evidence/mac-release.json', 8192),
                              ('build/icon-verification/mac-bundled-icon.png', 600 * 1024)]:
            path = root / relative
            if path.exists() or path.is_symlink():
                try:
                    data = read_regular(path, root, cap)
                    if path.suffix == '.json':
                        schema.decode(data, cap)
                    retain(path.name, data, cap)
                except (OSError, ValueError) as failure:
                    error(failure)
        native_log = root / 'mac-test.log'
        if native_log.exists() or native_log.is_symlink():
            retain('mac-test-tail.log', read_regular(native_log, root, LOG_CAP, tail=True), LOG_TAIL)
        if stopped or blocked():
            stopped = True
            error('Owned cleanup or original command outcome uncertain; pure bounded failure retention only')
        else:
            result = root / RESULT
            require(result.is_dir() and not result.is_symlink() and result.resolve(strict=True) == result,
                    'Missing or redirected fixed sandbox result bundle')
            read_regular(result / 'Info.plist', root, 64 * 1024)
            summary_data = run(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', RESULT], 30)
            summary = schema.decode(summary_data, JSON_CAP)
            device = validate_summary(summary)
            retain('sandbox-test-summary.json', summary_data, JSON_CAP)
            report['device'] = device
            report['launch_context']['result_device'] = device
            tests_data = run(['xcrun', 'xcresulttool', 'get', 'test-results', 'tests', '--path', RESULT], 30)
            report['executed_tests'] = validate_tests(schema.decode(tests_data, JSON_CAP), summary)
            retain('sandbox-test-results.json', tests_data, JSON_CAP)
            if any(row['presentation_binding'] == 'UNKNOWN' for row in report['executed_tests']):
                error('Exact test identities retained with UNKNOWN display-name presentation binding')
            test_exit = report['original_commands']['sandbox_test']['exit']
            require((summary['result'] == 'Passed' and test_exit == 0) or
                    (summary['result'] == 'Failed' and test_exit == 65),
                    'Original xcodebuild exit disagrees with actual XCTest summary')
            staging = root / STAGING
            require(not staging.exists() and not staging.is_symlink(), 'Attachment staging already exists; retries forbidden')
            run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', RESULT,
                 '--output-path', STAGING], 75)
            manifest_data = read_regular(staging / 'manifest.json', root, JSON_CAP)
            entries = attachment_records(schema.decode(manifest_data, JSON_CAP))
            # No raw result contents or arbitrary unrecognized attachments are uploaded.
            retained_frames, tokens, requests, receipt_checkpoints = set(), {}, set(), set()
            supporting, transitions, audit_counts = set(), set(), {}
            # Required frames and metadata precede optional failure images.
            def priority(entry):
                try:
                    name = presentation_name(entry)
                    return (2 if name == 'mac-failure' else 0 if name in set(FRAMES) else 1,
                            entry['exportedFileName'])
                except (ValueError, TypeError, UnicodeError):
                    # Invalid presentation remains an error in the entry loop;
                    # it must not discard other independently validated bytes.
                    return (3, entry['exportedFileName'])
            entries.sort(key=priority)
            for entry in entries:
                try:
                    name = presentation_name(entry)
                    prefix = owned_prefix(entry)
                    path = staging / entry['exportedFileName']
                    if name in set(FRAMES) | {'mac-failure'}:
                        data = read_regular(path, root, FILE_CAP)
                        dimensions = image_dimensions(data, name)
                        if name == 'mac-failure':
                            if name in retained_frames:
                                continue
                        else:
                            require(name not in retained_frames, 'Duplicate ordinary Mac frame')
                        row = retain('sandbox-' + name + ('.png' if dimensions else '.jpg'), data)
                        row = dict(row, checkpoint=name, source_bytes_preserved=True, diagnostic_failure=name == 'mac-failure')
                        if dimensions:
                            row['native_pixel_dimensions'] = dimensions
                        report['screenshots'].append(row)
                        retained_frames.add(name)
                    elif name == 'mac-audit-element' or name is None and prefix == 'mac-audit-element':
                        data = read_regular(path, root, 64 * 1024)
                        text = data.decode('utf-8')
                        require(any(text.startswith('Checkpoint: ' + c + '\n') for c in FRAMES),
                                'Strict callback belongs to a different checkpoint')
                        checkpoint = text.split('\n', 1)[0].removeprefix('Checkpoint: ')
                        require(checkpoint in FRAMES and audit_counts.get(checkpoint, 0) < 8 and
                                report['strict_audit_callbacks'] < 48,
                                'Strict callback attachment count exceeds original per-checkpoint bounds')
                        retain('sandbox-audit-' + str(report['strict_audit_callbacks'] + 1) + '.txt', data, 64 * 1024)
                        report['strict_audit_callbacks'] += 1
                        audit_counts[checkpoint] = audit_counts.get(checkpoint, 0) + 1
                    elif name == 'mac-supporting-text-layout' or name is None and prefix == 'mac-supporting-text-layout':
                        data = read_regular(path, root, 4096)
                        receipt = validate_supporting(data)
                        key = receipt['locale'] + '-' + receipt['phase']
                        require(key not in supporting and len(supporting) < 4, 'Duplicate supporting-layout receipt')
                        retain('sandbox-supporting-text-' + key + '.json', data, 4096)
                        supporting.add(key)
                    elif name == 'mac-payload-transition' or name is None and prefix == 'mac-payload-transition':
                        data = read_regular(path, root, 4096)
                        receipt = validate_transition(data)
                        key = receipt['locale'] + '-' + receipt['phase']
                        require(key not in transitions and len(transitions) < 4, 'Duplicate payload-transition receipt')
                        retain('sandbox-payload-transition-' + key + '.json', data, 4096)
                        transitions.add(key)
                    else:
                        # A bounded presentation variant may still carry safe,
                        # closed-schema diagnostic bytes. It cannot complete a pair.
                        if name is None and prefix != 'mac-public-metadata-':
                            continue
                        require(name is None or name.startswith('mac-public-metadata-'), 'Unknown attachment kind')
                        data = read_regular(path, root, 32768)
                        receipt = validate_metadata(data)
                        checkpoint, case = receipt['checkpoint'], receipt['case']
                        expected_name = 'mac-public-metadata-' + checkpoint
                        require(name is None or name == expected_name, 'Metadata presentation/internal checkpoint disagreement')
                        require(checkpoint not in receipt_checkpoints and receipt['requestID'] not in requests,
                                'Duplicate metadata checkpoint/request UUID')
                        require(case not in tokens or tokens[case] == receipt['token'], 'Stale case session token')
                        require(all(c == case or t != receipt['token'] for c, t in tokens.items()), 'Case sessions reused one token')
                        retain('sandbox-public-metadata-' + checkpoint + '.json', data, 32768)
                        slot = next(row for row in report['metadata'] if row['checkpoint'] == checkpoint)
                        slot.update(token=receipt['token'], requestID=receipt['requestID'], sameState=receipt['sameState'],
                                    presentation_binding='OBSERVED' if name else 'UNKNOWN', receipt_retained=True,
                                    reason=receipt['reason'], presentation=presentation_diagnostic(entry, expected_name))
                        receipt_checkpoints.add(checkpoint)
                        tokens[case] = receipt['token']
                        requests.add(receipt['requestID'])
                        if name is None:
                            error('Safe metadata retained with UNKNOWN attachment presentation binding: ' + checkpoint)
                except (OSError, ValueError, TypeError, KeyError, UnicodeError) as failure:
                    error(failure)
            report['missing_frames'] = sorted(set(FRAMES) - retained_frames)
            paired_names = {row['checkpoint'] for row in report['metadata'] if row['receipt_retained'] and row['presentation_binding'] == 'OBSERVED'}
            report['missing_metadata'] = sorted(set(CHECKPOINTS) - paired_names)
            report['missing_supporting'] = sorted({locale + '-' + phase for locale in ('en', 'zh-Hans')
                                                  for phase in ('full', 'minimum-long-content')} - supporting)
            report['missing_transitions'] = sorted({locale + '-' + phase for locale in ('en', 'zh-Hans')
                                                   for phase in ('prepared', 'copy-observed')} - transitions)
            for key in ('missing_frames', 'missing_metadata', 'missing_supporting', 'missing_transitions'):
                if report[key]:
                    error(key + ': ' + ', '.join(report[key]))
            # Hosted regression summary is optional; no extra UI case is selected.
            hosted = root / 'MacTestResults.xcresult'
            if hosted.exists() or hosted.is_symlink():
                require(hosted.is_dir() and hosted.resolve(strict=True) == hosted and not hosted.is_symlink(),
                        'Redirected optional hosted result')
                read_regular(hosted / 'Info.plist', root, 64 * 1024)
                data = run(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', 'MacTestResults.xcresult'], 30)
                validate_summary(schema.decode(data, JSON_CAP), hosted=True, device=device)
                retain('test-summary.json', data, JSON_CAP)
            if any('Publishing changes from within view updates' in str(w) for w in summary['runtimeWarnings']):
                error('SwiftUI re-entrant publication warning remains a release blocker')
            for name in ('mac-sandbox-test-tail.log', 'mac-test-tail.log'):
                path = out / name
                if path.exists() and b'vnode unlinked' in read_regular(path, root, LOG_TAIL):
                    error('SQLite files were unlinked while open')
            report['evidence_complete'] = not report['errors']
            if report['evidence_complete'] and report['launch_context']['state'] == 'OBSERVED' and all(r['sameState'] == 'OBSERVED' for r in report['metadata']):
                report['sameState'] = 'OBSERVED'
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as failure:
        error(failure)
    report['owned_cleanup_uncertainty_observed'] = stopped or blocked()
    if report['owned_cleanup_uncertainty_observed']:
        report['sameState'] = 'UNKNOWN'
        report['evidence_complete'] = False
        for row in report['metadata']:
            if row['receipt_retained'] is False:
                row['reason'] = 'owned-cleanup-or-original-command-uncertainty'
    report['elapsed_seconds'] = round(clock() - started, 3)
    report['retained_payload_bytes'] = used
    data = (json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()
    require(len(data) <= REPORT_RESERVE and used + len(data) <= SCOPE_CAP, 'Final diagnostic report exceeds Mac allocation')
    with (out / 'public-metadata-report.json').open('xb') as stream:
        stream.write(data)
    return report


def main(arguments):
    require(not arguments, 'This collector has one fixed route and accepts no arguments')
    report = collect()
    print(json.dumps({'evidence_complete': report['evidence_complete'], 'sameState': report['sameState'],
                      'auditQualified': False, 'contrastQualified': False, 'errors': report['errors']}), flush=True)
    return 0 if report['evidence_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
