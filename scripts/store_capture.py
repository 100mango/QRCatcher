#!/usr/bin/env python3
"""Two fixed Store display cases, two owned simulators, raw native PNGs only."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import plistlib
import re
import struct
import time
import uuid
import zlib

from atomic_json import write_json
from owned_process_barrier import blocked
from watch_process import execute

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = '991af41dfdc01bc1332218cb8969f4ca40198304'
BASE_TREE = 'd5357beefe435c278f7bfc793eae5059df5b0cfb'
UI_PATH = 'QRCatcherUITests/QRCatcherUITests.m'
CONTRACT_SHA = '621f69768e5c5c8ec2e4aee824a881c878053e6f4f3d50e21e3574022d079368'
DISPLAY_SHA = '40de291f2f27f0cf169b7cc63255963329465c76c165d74e04cc2c19e263c3b9'
CHANGED = {UI_PATH, 'scripts/store_capture.py', 'scripts/store_capture_source.json',
           'Tests/Harness/test_store_capture.py', 'docs/STORE_SCREENSHOTS.md',
           '.github/workflows/ios-store-screenshots.yml'}
TARGETS = (
    {'row': 'iphone-17-pro', 'model': 'iPhone 17 Pro', 'pixels': [1206, 2622]},
    {'row': 'ipad-13-m5', 'model': 'iPad Pro 13-inch (M5)', 'pixels': [2064, 2752]},
)
CASES = {'result': 'testStoreNormalResultScreenshot', 'history': 'testStoreNormalHistoryScreenshot'}
MAX_SCREENSHOT = 8_000_000
MAX_PACKET = 40_000_000
BEGIN = b'// BEGIN FIXED STORE PNG DISPLAY METHODS\n'
END = b'// END FIXED STORE PNG DISPLAY METHODS\n'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_json(raw):
    def pairs(rows):
        value = {}
        for key, item in rows:
            need(key not in value, 'Duplicate JSON field')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: need(False, 'Nonfinite JSON'))


def read_file(path, limit):
    path = Path(path)
    need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= limit,
         'Missing, unsafe, or oversized file: ' + str(path))
    return path.read_bytes()


def verify_source(root=ROOT):
    raw = read_file(root / 'scripts/store_capture_source.json', 200_000)
    need(sha(raw) == CONTRACT_SHA, 'Changed protected-source manifest')
    contract = load_json(raw)
    need(contract['base_commit'] == BASE_COMMIT and contract['base_tree'] == BASE_TREE,
         'Wrong product-source identity')
    need(len(contract['files']) == 456, 'Changed protected membership')
    for row in contract['files']:
        raw = read_file(root / row['path'], 8_000_000)
        if row['path'] == UI_PATH:
            need(raw.count(BEGIN) == raw.count(END) == 1, 'Ambiguous capture-only block')
            start, end = raw.index(BEGIN), raw.index(END) + len(END)
            need(start < end and sha(raw[start:end]) == DISPLAY_SHA, 'Changed display methods')
            raw = raw[:start] + raw[end:]
        need(len(raw) == row['bytes'] and sha(raw) == row['sha256'],
             'Changed protected input: ' + row['path'])
    return {'product_source': BASE_COMMIT, 'product_tree': BASE_TREE,
            'unchanged_files': 455, 'reversible_ui_test_file': UI_PATH,
            'original_test_methods_unchanged': True, 'locale': 'zh-Hans',
            'synthetic_demo_payloads': ['https://example.com', '周末计划\n上午逛市集，下午喝咖啡'],
            'debug_encode_decode_save': True, 'physical_camera_scan_proven': False,
            'shipping_release_qualification': False, 'visual_review': 'pending'}


def select_devices(runtimes, types, devices):
    available = [r for r in runtimes['runtimes'] if r.get('isAvailable') and
                 r.get('version') == '27.0' and r.get('buildversion') == '24A434' and
                 r.get('identifier', '').startswith('com.apple.CoreSimulator.SimRuntime.iOS-')]
    need(len(available) == 1, 'Exactly one observed iOS 27.0 / 24A434 runtime required')
    need(not any(d.get('state') == 'Booted' for rows in devices['devices'].values() for d in rows),
         'Requires an idle disposable simulator host')
    output = []
    for target in TARGETS:
        rows = [d for d in types['devicetypes'] if d.get('name') == target['model']]
        need(len(rows) == 1, 'Missing or ambiguous exact device type: ' + target['model'])
        need(rows[0]['identifier'].startswith('com.apple.CoreSimulator.SimDeviceType.'), 'Invalid device type')
        output.append({**target, 'runtime': available[0], 'device_type': rows[0]})
    return output


# Native PNG validation and flat Xcode 27 attachment traversal are reused from
# Celluloid's existing store_screenshots.py capture route, without its exporter.
def png_metadata(data):
    need(0 < len(data) <= MAX_SCREENSHOT and data.startswith(b'\x89PNG\r\n\x1a\n'), 'Invalid or oversized original PNG')
    offset = 8
    chunks = []
    compressed = []
    header = None
    while offset < len(data):
        need(offset + 12 <= len(data), 'Truncated PNG chunk')
        size = struct.unpack('>I', data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        need(end <= len(data), 'PNG chunk outside file')
        payload = data[offset + 8:offset + 8 + size]
        need(zlib.crc32(kind + payload) & 0xffffffff == struct.unpack('>I', data[end - 4:end])[0], 'PNG CRC mismatch')
        if not chunks:
            need(kind == b'IHDR' and size == 13, 'PNG missing first IHDR')
            header = struct.unpack('>IIBBBBB', payload)
        else:
            need(kind != b'IHDR', 'Duplicate PNG IHDR')
        chunks.append(kind)
        if kind == b'IDAT':
            compressed.append(payload)
        offset = end
        if kind == b'IEND':
            need(size == 0 and offset == len(data), 'Data after PNG IEND')
            break
    need(header is not None and chunks[-1] == b'IEND' and b'IDAT' in chunks, 'Incomplete PNG')
    width, height, depth, color, compression, filtering, interlace = header
    depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
    need(0 < width <= 2064 and 0 < height <= 2752 and color in depths and depth in depths[color]
         and compression == filtering == interlace == 0, 'Unsupported native PNG header')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    stride = (width * channels * depth + 7) // 8 + 1
    decoder = zlib.decompressobj()
    raster = decoder.decompress(b''.join(compressed), stride * height + 1)
    need(decoder.eof and not decoder.unused_data and len(raster) == stride * height,
         'Invalid bounded PNG raster')
    need(all(raster[offset] <= 4 for offset in range(0, len(raster), stride)), 'Invalid PNG filter')
    return {'format': 'PNG', 'width': width, 'height': height, 'bit_depth': depth, 'color_type': color,
            'has_alpha_channel_or_transparency': color in {4, 6} or b'tRNS' in chunks,
            'bytes': len(data), 'sha256': sha(data), 'resized': False, 'reencoded': False}


def attachment_records(value):
    """Xcode27's observed flat manifest: test row owns each attachment."""
    need(type(value) is list and len(value) <= 32, 'Invalid or unbounded attachment rows')
    total = 0
    for row in value:
        need(type(row) is dict, 'Invalid attachment test row')
        attachments = row.get('attachments', [])
        need(type(attachments) is list and len(attachments) <= 256, 'Invalid or unbounded row attachments')
        total += len(attachments)
        need(total <= 512, 'Unbounded total attachment records')
        for item in attachments:
            need(type(item) is dict, 'Invalid attachment item')
            yield row.get('testIdentifier'), item


def select_png(folder, target, label):
    raw = read_file(folder / 'manifest.json', 1_000_000)
    found = []
    for test, item in attachment_records(load_json(raw)):
        human = item.get('suggestedHumanReadableName', '')
        if not re.fullmatch(r'qrcatcher-store-' + label + r'(?:_[A-Za-z0-9_-]+)?(?:\.png)?', human):
            continue
        need(test.removesuffix('()') in {'QRCatcherStoreCaptureUITests/' + CASES[label],
             'QRCatcherUITests/QRCatcherStoreCaptureUITests/' + CASES[label]}, 'Wrong screenshot test owner')
        keys = [k for k, v in item.items() if type(v) is str and v == target['udid']]
        need(keys and ('deviceId' not in item or item['deviceId'] == target['udid']),
             'Screenshot is not bound to this owned simulator')
        name = item.get('exportedFileName')
        need(type(name) is str and Path(name).name == name, 'Unsafe exported attachment path')
        data = read_file(folder / name, MAX_SCREENSHOT)
        metadata = png_metadata(data)
        need([metadata['width'], metadata['height']] == target['pixels'], 'Wrong original PNG dimensions')
        found.append((data, {**metadata, 'attachment': item, 'test_identifier': test,
                            'device_uuid_keys': keys, 'visual_approval': 'pending'}))
    need(len(found) == 1, 'Exactly one bound original PNG required for this case')
    return found[0], raw


def product_manifest(app):
    app = Path(app).resolve(strict=True)
    info = plistlib.loads(read_file(app / 'Info.plist', 64_000))
    need(info.get('CFBundleIdentifier') == '100mango.QRCatcher' and
         info.get('CFBundleShortVersionString') == '1.1' and info.get('CFBundleVersion') == '2' and
         info.get('DTPlatformName') == 'iphonesimulator' and info.get('UIDeviceFamily') == [1, 2],
         'Unexpected actual app identity')
    rows, total = [], 0
    for path in sorted(app.rglob('*')):
        need(not path.is_symlink(), 'Unexpected simulator app symlink')
        if path.is_file():
            data = read_file(path, 100_000_000) if path.stat().st_size else b''
            total += len(data)
            need(total <= 200_000_000 and len(rows) < 4096, 'Unbounded product inventory')
            rows.append([str(path.relative_to(app)), len(data), sha(data)])
    need(rows, 'Empty app')
    return {'fingerprint': sha(json.dumps(rows, separators=(',', ':')).encode()), 'files': rows,
            'bundle_id': info['CFBundleIdentifier'], 'version': '1.1', 'build': '2'}


def verify_summary(summary, target, start, finish):
    need(summary.get('result') == 'Passed' and type(summary.get('totalTestCount')) is int and
         summary['totalTestCount'] == 1 and type(summary.get('passedTests')) is int and summary['passedTests'] == 1 and
         all(type(summary.get(k)) is int and summary[k] == 0 for k in ('failedTests', 'skippedTests', 'expectedFailures'))
         and summary.get('testFailures') == [] and summary.get('runtimeWarnings') == [], 'Display case did not pass cleanly')
    rows = summary.get('devicesAndConfigurations', [])
    need(len(rows) == 1, 'Ambiguous test destination')
    device = rows[0].get('device', {})
    need(device.get('deviceId') == target['udid'] and device.get('modelName') == target['model'] and
         device.get('osVersion') == '27.0' and device.get('osBuildNumber') == '24A434' and
         device.get('architecture') == 'arm64' and device.get('platform') == 'iOS Simulator',
         'Actual XCTest destination differs from owned capture target')
    a, b = summary.get('startTime'), summary.get('finishTime')
    need(type(a) in (int, float) and type(b) in (int, float) and math.isfinite(a) and math.isfinite(b)
         and start <= a < b <= finish, 'Stale/unfinalized test summary')


class Capture:
    def __init__(self):
        self.clock = load_json(read_file(Path(os.environ['RUNNER_TEMP']) / 'qrcatcher-store-clock.json', 4096))
        for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
            need(self.clock.get(key) == os.environ.get(key), 'Wrong source/run clock binding')
        need(type(self.clock.get('started')) in (int, float) and
             math.isfinite(self.clock['started']) and 0 <= time.monotonic() - self.clock['started'] < 180,
             'Stale capture clock')
        need(Path.cwd() == ROOT and os.environ.get('GITHUB_REPOSITORY') == '100mango/QRCatcher' and
             os.environ.get('GITHUB_REF') == 'refs/heads/codex/store-screenshots' and
             os.environ.get('GITHUB_WORKFLOW_REF') == '100mango/QRCatcher/.github/workflows/ios-store-screenshots.yml@refs/heads/codex/store-screenshots' and
             os.environ.get('GITHUB_EVENT_NAME') == 'push' and os.environ.get('GITHUB_JOB') == 'capture' and
             os.environ.get('GITHUB_WORKFLOW_SHA') == os.environ.get('GITHUB_SHA'), 'Wrong capture route')
        need(re.fullmatch('[0-9a-f]{40}', os.environ['GITHUB_SHA']) and
             all(re.fullmatch('[1-9][0-9]{0,19}', os.environ[k]) for k in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')),
             'Invalid source/run identity')
        self.packet = Path(os.environ['RUNNER_TEMP']) / 'qrcatcher-store-evidence'
        self.packet.mkdir(exist_ok=False)
        self.work = ROOT / 'build/store-capture'
        self.work.mkdir(parents=True, exist_ok=False)
        self.source = verify_source()
        self.source.update(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                           attempt=os.environ['GITHUB_RUN_ATTEMPT'])
        self.captures = []
        self.retain_json('progress.json', {'status': 'started', 'source': self.source})

    def retain(self, name, data):
        need(name == Path(name).name and not (self.packet / name).is_symlink(), 'Unsafe retained filename')
        limit = MAX_SCREENSHOT if name.endswith('.png') else 1_000_000
        need(len(data) <= limit, 'Evidence file exceeds limit')
        total = sum(p.stat().st_size for p in self.packet.iterdir() if p.name != name)
        need(total + len(data) <= MAX_PACKET, 'Packet cap reached; prior captures stay retained')
        with (self.packet / name).open('xb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())

    def retain_json(self, name, value):
        data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode() + b'\n'
        if (self.packet / name).exists():
            need(not (self.packet / name).is_symlink() and len(data) <= 1_000_000 and
                 sum(p.stat().st_size for p in self.packet.iterdir() if p.name != name) + len(data) <= MAX_PACKET,
                 'Oversized or unsafe retained receipt')
            write_json(self.packet / name, value, limit=1_000_000)
        else:
            self.retain(name, data)

    def command(self, label, args, cap, tail=False, accept=(0,), output=1_000_000):
        need(not blocked(), 'Owned process uncertainty forbids further native commands')
        endpoint = self.clock['started'] + (2940 if tail else 2700)
        need(time.monotonic() + cap + 20 < endpoint, 'Full command allowance plus cleanup does not fit')
        code, text, operation = execute(args, cap, output_limit=max(output, 2_000_000), tail_limit=output, echo=False)
        self.retain_json(label + '-command.json', operation)
        self.retain(label + '.log', text.encode()[-64000:])
        need(operation.get('cleanup_confirmed') is True and operation.get('state') == 'completed' and
             operation.get('elapsed_seconds', cap + 2) < cap + 2 and code in accept,
             'Command failed/unknown: ' + label)
        need(operation['output_bytes'] <= output or output == 16_000_000, 'Truncated required readback: ' + label)
        return code, text

    def json_command(self, label, args, cap=30, tail=False):
        _, raw = self.command(label, args, cap, tail)
        data = raw.encode()
        self.retain(label + '.json', data)
        return load_json(raw)

    def installed(self, target, label):
        _, raw = self.command(label, ['xcrun', 'simctl', 'get_app_container', target['udid'],
                                     '100mango.QRCatcher', 'app'], 60)
        path = Path(raw.strip())
        expected = Path.home() / 'Library/Developer/CoreSimulator/Devices' / target['udid'] / 'data/Containers/Bundle/Application'
        need(path.is_absolute() and path.resolve().is_relative_to(expected.resolve()) and
             path.name == 'QRCatcher.app', 'Wrong owned installed product path')
        need(product_manifest(path) == self.product, 'Installed app differs from built product')

    def run(self):
        _, head = self.command('source-head', ['git', 'rev-parse', 'HEAD'], 15)
        need(head.strip() == self.source['source_sha'], 'Wrong actual source commit')
        _, parent = self.command('source-parent', ['git', 'show', '-s', '--format=%P', 'HEAD'], 15)
        need(parent.strip() == BASE_COMMIT, 'Exact sole base parent required')
        _, tree = self.command('source-tree', ['git', 'rev-parse', 'HEAD^{tree}', 'HEAD^1^{tree}'], 15)
        trees = tree.splitlines()
        need(len(trees) == 2 and trees[1] == BASE_TREE, 'Wrong base tree')
        self.source['source_tree'] = trees[0]
        _, changed = self.command('source-delta', ['git', 'diff', '--name-only', BASE_COMMIT, 'HEAD'], 15)
        need(set(changed.splitlines()) == CHANGED, 'Unreviewed changed path inventory')
        self.command('source-clean', ['git', 'diff', '--exit-code', 'HEAD', '--'], 15)
        _, xcode = self.command('xcode', ['xcodebuild', '-version'], 30)
        need('Xcode 27.0' in xcode and '27A266a' in xcode, 'Wrong stable toolchain')
        runtime = self.json_command('runtimes', ['xcrun', 'simctl', 'list', 'runtimes', '-j'])
        types = self.json_command('device-types', ['xcrun', 'simctl', 'list', 'devicetypes', '-j'])
        devices = self.json_command('devices-before', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'])
        targets = select_devices(runtime, types, devices)
        existing = {d['udid'] for rows in devices['devices'].values() for d in rows}
        self.retain_json('source.json', self.source)
        self.command('fixtures', ['python3', 'scripts/materialize_qr_fixtures.py'], 30)
        self.command('ipad-icons', ['python3', 'scripts/materialize_ipad_icons.py'], 60)
        self.command('build', ['xcodebuild', 'build-for-testing', '-project', 'QRCatcher-iOS-Only.xcodeproj',
            '-scheme', 'QRCatcher', '-configuration', 'Debug', '-derivedDataPath', 'build/store-capture/DerivedData',
            '-destination', 'generic/platform=iOS Simulator', '-jobs', '2', 'ARCHS=arm64',
            'CODE_SIGNING_ALLOWED=NO'], 600, output=16_000_000)
        app = self.work / 'DerivedData/Build/Products/Debug-iphonesimulator/QRCatcher.app'
        self.product = product_manifest(app)
        self.retain_json('built-product.json', self.product)
        os.environ['TEST_RUNNER_QRCATCHER_STORE_CAPTURE'] = '1'
        for target in targets:
            row = target['row']
            name = 'QRCatcher-Store-' + self.source['run_id'] + '-' + self.source['attempt'] + '-' + row
            _, raw = self.command(row + '-create', ['xcrun', 'simctl', 'create', name,
                target['device_type']['identifier'], target['runtime']['identifier']], 60)
            udid = raw.strip()
            need(str(uuid.UUID(udid)).upper() == udid and udid not in existing, 'Unproven fresh simulator identity')
            target.update(udid=udid, owned_name=name)
            observed = self.json_command(row + '-readback', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'])
            matches = [(r, d) for r, rows in observed['devices'].items() for d in rows if d['udid'] == udid]
            need(len(matches) == 1 and matches[0][0] == target['runtime']['identifier'] and
                 matches[0][1].get('deviceTypeIdentifier') == target['device_type']['identifier'] and
                 matches[0][1].get('name') == name and matches[0][1].get('isAvailable') is True and
                 matches[0][1].get('state') == 'Shutdown' and
                 not any(d.get('state') == 'Booted' for rows in observed['devices'].values() for d in rows),
                 'Owned simulator readback failed')
            self.retain_json(row + '-device.json', target)
            self.command(row + '-boot', ['xcrun', 'simctl', 'boot', udid], 60)
            self.command(row + '-bootstatus', ['xcrun', 'simctl', 'bootstatus', udid, '-b'], 240)
            self.command(row + '-install', ['xcrun', 'simctl', 'install', udid, str(app)], 600)
            self.installed(target, row + '-installed-before')
            self.command(row + '-light', ['xcrun', 'simctl', 'ui', udid, 'appearance', 'light'], 60)
            for label, method in CASES.items():
                stem = row + '-' + label
                result = self.work / (stem + '.xcresult')
                started = time.time()
                code, _ = self.command(stem + '-test', ['xcodebuild', 'test-without-building',
                    '-project', 'QRCatcher-iOS-Only.xcodeproj', '-scheme', 'QRCatcher', '-configuration', 'Debug',
                    '-derivedDataPath', 'build/store-capture/DerivedData', '-destination', 'platform=iOS Simulator,id=' + udid,
                    '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
                    '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '180',
                    '-maximum-test-execution-time-allowance', '240', '-only-testing:QRCatcherUITests/QRCatcherStoreCaptureUITests/' + method,
                    '-resultBundlePath', str(result), 'CODE_SIGNING_ALLOWED=NO'],
                    600 if label == 'result' else 420, accept=(0, 65), output=16_000_000)
                folder = self.work / (stem + '-attachments')
                self.command(stem + '-export', ['xcrun', 'xcresulttool', 'export', 'attachments',
                    '--path', str(result), '--output-path', str(folder)], 45, tail=True)
                (data, metadata), raw_manifest = select_png(folder, target, label)
                # Retain immediately, before summary, postflight, the next case/device,
                # or cleanup. Later failures never remove these already retained bytes.
                self.retain(stem + '.png', data)
                receipt = {**metadata, 'source': self.source, 'device': target,
                           'product_fingerprint': self.product['fingerprint'], 'case_passed': False}
                self.retain_json(stem + '-receipt.json', receipt)
                self.retain(stem + '-attachments.json', raw_manifest)
                self.captures.append(stem)
                self.retain_json('progress.json', {'status': 'partial', 'retained': self.captures})
                summary = self.json_command(stem + '-summary', ['xcrun', 'xcresulttool', 'get',
                    'test-results', 'summary', '--path', str(result)], 30, tail=True)
                verify_summary(summary, target, started, time.time())
                need(code == 0, 'Native display case returned failure')
                need(not metadata['has_alpha_channel_or_transparency'], 'Raw PNG has alpha; retain but do not transform')
                receipt['case_passed'] = True
                self.retain_json(stem + '-receipt.json', receipt)
            self.installed(target, row + '-installed-after')
            need(product_manifest(app) == self.product, 'Built product changed')
            verify_source()
            self.command(row + '-shutdown', ['xcrun', 'simctl', 'shutdown', udid], 45, tail=True)
            observed = self.json_command(row + '-shutdown-readback', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 30, tail=True)
            rows = [d for ds in observed['devices'].values() for d in ds if d['udid'] == udid]
            need(len(rows) == 1 and rows[0]['state'] == 'Shutdown', 'Owned simulator shutdown unconfirmed')
            self.command(row + '-delete', ['xcrun', 'simctl', 'delete', udid], 45, tail=True)
            observed = self.json_command(row + '-delete-readback', ['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], 30, tail=True)
            need(not any(d['udid'] == udid for ds in observed['devices'].values() for d in ds), 'Owned simulator deletion unconfirmed')
            existing.add(udid)
        self.command('source-final', ['git', 'diff', '--exit-code', 'HEAD', '--'], 15, tail=True)
        self.retain_json('progress.json', {'status': 'captured_pending_visual_review', 'retained': self.captures,
            'original_pixels_unmodified': True, 'store_upload_performed': False})


def upload_admission():
    packet = Path(os.environ['RUNNER_TEMP']) / 'qrcatcher-store-evidence'
    need(packet.is_dir() and not packet.is_symlink(), 'Missing retained evidence')
    files = sorted(packet.iterdir())
    need(files and len(files) <= 256, 'Unbounded evidence membership')
    names = {t['row'] + '-' + label + '.png': t['pixels'] for t in TARGETS for label in CASES}
    total = 0
    for path in files:
        # A successful command may have no stdout. Keep that real empty log;
        # read_file stays strict for JSON, PNG, and every other evidence file.
        if path.suffix == '.log' and path.is_file() and not path.is_symlink() and path.stat().st_size == 0:
            data = b''
        else:
            data = read_file(path, MAX_SCREENSHOT if path.suffix == '.png' else 1_000_000)
        total += len(data)
        if path.suffix == '.png':
            need(path.name in names, 'Unexpected retained PNG')
            value = png_metadata(data)
            need([value['width'], value['height']] == names[path.name], 'Wrong retained PNG dimensions')
    need(total <= MAX_PACKET, 'Bounded upload cap exceeded')
    print(json.dumps({'files': len(files), 'bytes': total, 'pngs': [p.name for p in files if p.suffix == '.png']}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['verify-source', 'run', 'upload-admission'])
    action = parser.parse_args().action
    if action == 'verify-source':
        print(json.dumps(verify_source(), ensure_ascii=False, indent=2))
    elif action == 'upload-admission':
        upload_admission()  # File-only, also valid after an uncertain native command.
    else:
        capture = Capture()
        try:
            capture.run()
        except Exception as error:
            capture.retain_json('failure.json', {'error': str(error), 'retained': capture.captures,
                'no_native_retry_or_cleanup_on_failure': True, 'store_upload_performed': False})
            raise


if __name__ == '__main__':
    main()
