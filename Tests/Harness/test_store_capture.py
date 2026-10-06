"""Focused local checks only. No Xcode, simulator, network, or publication."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import store_capture as capture


def png(width=2, height=3, color=2):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    channels = 4 if color == 6 else 3
    raster = (b'\0' + b'\0' * (width * channels)) * height
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, color, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raster)) + chunk(b'IEND', b''))


def fixtures():
    runtime = {'identifier': 'com.apple.CoreSimulator.SimRuntime.iOS-27-0', 'isAvailable': True,
               'version': '27.0', 'buildversion': '24A434'}
    types = [{'name': t['model'], 'identifier': 'com.apple.CoreSimulator.SimDeviceType.' + t['row']}
             for t in capture.TARGETS]
    return {'runtimes': [runtime]}, {'devicetypes': types}, {'devices': {runtime['identifier']: []}}


class StoreCaptureTests(unittest.TestCase):
    def test_source_is_exactly_reversible(self):
        result = capture.verify_source()
        self.assertEqual(result['unchanged_files'], 455)
        self.assertFalse(result['physical_camera_scan_proven'])
        self.assertFalse(result['shipping_release_qualification'])
        self.assertEqual(capture.PUBLIC_PARENT, '57fd7e32a499cc5237a091e30f04d99edf9e7705')
        self.assertEqual(capture.PUBLIC_PARENT_TREE, '001e0aa8b33ea53039d6c47a59a84465aef9f139')
        self.assertEqual(capture.CHANGED, {capture.UI_PATH, 'scripts/store_capture.py',
            'Tests/Harness/test_store_capture.py', 'docs/STORE_SCREENSHOTS.md'})

    def test_original_methods_and_projects_unchanged(self):
        contract = json.loads((ROOT / 'scripts/store_capture_source.json').read_text())
        raw = (ROOT / capture.UI_PATH).read_bytes()
        block = raw[raw.index(capture.BEGIN):raw.index(capture.END) + len(capture.END)]
        self.assertEqual(re.findall(rb'- \(void\)(test\w+)', block),
                         [b'testStoreNormalResultScreenshot', b'testStoreNormalHistoryScreenshot'])
        self.assertIn(b'@implementation QRCatcherStoreCaptureUITests', block)
        self.assertTrue(raw.endswith(block))
        self.assertNotIn(b'testStoreNormal', raw[:-len(block)])
        self.assertIn(b'XCUIScreen.mainScreen.screenshot.PNGRepresentation', block)
        self.assertNotIn(b'UIImageJPEGRepresentation', block)
        self.assertNotIn(b'UIImagePNGRepresentation', block)
        self.assertIn(b'@"(zh-Hans)"', block)
        self.assertIn(b'@"-fixture-payload"', block)
        self.assertIn('周末计划：上午逛市集，下午喝咖啡'.encode(), block)
        self.assertNotIn('周末计划\\n上午逛市集，下午喝咖啡'.encode(), block)
        self.assertIn(b'XCTAssertEqualObjects(self.app.staticTexts[@"scan.result"].label, payload);', block)
        self.assertEqual(len(contract['files']), 456)

    def test_fixed_owned_models_and_dimensions(self):
        selected = capture.select_devices(*fixtures())
        self.assertEqual([t['model'] for t in selected], ['iPhone 17 Pro', 'iPad Pro 13-inch (M5)'])
        self.assertEqual([t['pixels'] for t in selected], [[1206, 2622], [2064, 2752]])
        self.assertEqual([t['capture_labels'] for t in selected], [['history'], ['result', 'history']])
        self.assertEqual(sum(len(t['capture_labels']) for t in selected), 3)

    def test_missing_model_or_ambiguous_runtime_fails(self):
        r, t, d = fixtures()
        t['devicetypes'].pop()
        with self.assertRaises(ValueError): capture.select_devices(r, t, d)
        r, t, d = fixtures()
        r['runtimes'].append(dict(r['runtimes'][0]))
        with self.assertRaises(ValueError): capture.select_devices(r, t, d)

    def test_wrong_runtime_or_busy_host_fails(self):
        r, t, d = fixtures()
        r['runtimes'][0]['buildversion'] = 'unknown'
        with self.assertRaises(ValueError): capture.select_devices(r, t, d)
        r, t, d = fixtures()
        next(iter(d['devices'].values())).append({'state': 'Booted'})
        with self.assertRaises(ValueError): capture.select_devices(r, t, d)

    def test_png_original_rgb_and_alpha_reported(self):
        metadata = capture.png_metadata(png())
        self.assertFalse(metadata['has_alpha_channel_or_transparency'])
        self.assertFalse(metadata['resized'])
        self.assertFalse(metadata['reencoded'])
        self.assertTrue(capture.png_metadata(png(color=6))['has_alpha_channel_or_transparency'])

    def test_png_crc_truncation_trailing_data_fail(self):
        data = png()
        broken = bytearray(data); broken[40] ^= 1
        for value in (bytes(broken), data[:-3], data + b'bad', b'JPEG'):
            with self.subTest(value=value[:8]), self.assertRaises(ValueError): capture.png_metadata(value)

    def attachment(self, directory, target, owner=None, duplicate=False):
        data = png(*target['pixels'])
        (directory / 'raw.png').write_bytes(data)
        item = {'suggestedHumanReadableName': 'qrcatcher-store-result', 'exportedFileName': 'raw.png',
                'deviceId': target['udid']}
        row = {'testIdentifier': owner or 'QRCatcherStoreCaptureUITests/testStoreNormalResultScreenshot()',
               'attachments': [item, item] if duplicate else [item]}
        (directory / 'manifest.json').write_text(json.dumps([row]))
        return data

    def test_exact_attachment_raw_bytes_and_owner(self):
        target = {**capture.TARGETS[0], 'udid': '11111111-1111-1111-1111-111111111111'}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); data = self.attachment(folder, target)
            (selected, metadata), _ = capture.select_png(folder, target, 'result')
            self.assertEqual(selected, data)
            self.assertEqual(metadata['sha256'], capture.sha(data))
            self.attachment(folder, target, owner='QRCatcherUITests/testScannedTextPersistsAcrossRelaunchAndBackground()')
            with self.assertRaises(ValueError): capture.select_png(folder, target, 'result')

    def test_attachment_duplicate_foreign_device_path_and_dimensions_reject(self):
        target = {**capture.TARGETS[0], 'udid': '11111111-1111-1111-1111-111111111111'}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.attachment(folder, target, duplicate=True)
            with self.assertRaises(ValueError): capture.select_png(folder, target, 'result')
            self.attachment(folder, target)
            with self.assertRaises(ValueError): capture.select_png(folder, {**target, 'udid': 'foreign'}, 'result')
            with self.assertRaises(ValueError): capture.select_png(folder, {**target, 'pixels': [1179, 2556]}, 'result')
            value = json.loads((folder / 'manifest.json').read_text())
            value[0]['attachments'][0]['exportedFileName'] = '../raw.png'
            (folder / 'manifest.json').write_text(json.dumps(value))
            with self.assertRaises(ValueError): capture.select_png(folder, target, 'result')

    def test_strict_json_duplicate_nonfinite_reject(self):
        for raw in ('{"x": 1, "x": 2}', '{"x": NaN}'):
            with self.assertRaises(ValueError): capture.load_json(raw)

    def test_prior_png_survives_later_failure_and_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = capture.Capture.__new__(capture.Capture); runner.packet = Path(tmp)
            data = png(); runner.retain('iphone-17-pro-result.png', data)
            runner.retain_json('failure.json', {'error': 'later stage failed'})
            with self.assertRaises(FileExistsError): runner.retain('iphone-17-pro-result.png', b'replacement')
            with patch.object(capture, 'MAX_PACKET', len(data)):
                with self.assertRaises(ValueError): runner.retain('later.log', b'new')
            self.assertEqual((runner.packet / 'iphone-17-pro-result.png').read_bytes(), data)

    def test_upload_accepts_real_retained_empty_command_log_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = capture.Capture.__new__(capture.Capture)
            runner.packet = Path(tmp) / 'qrcatcher-store-evidence'
            runner.packet.mkdir()
            runner.retain('source-clean.log', b'')
            runner.retain_json('source-clean-command.json', {'state': 'completed', 'exit': 0, 'output_bytes': 0})
            self.assertEqual((runner.packet / 'source-clean.log').stat().st_size, 0)
            with patch.dict(capture.os.environ, {'RUNNER_TEMP': tmp}):
                capture.upload_admission()
                for name in ('empty.json', 'manifest.json', 'iphone-17-pro-result.png'):
                    with self.subTest(name=name):
                        runner.retain(name, b'')
                        with self.assertRaises(ValueError): capture.upload_admission()
                        (runner.packet / name).unlink()
                (runner.packet / 'unsafe.log').symlink_to(runner.packet / 'source-clean.log')
                with self.assertRaises(ValueError): capture.upload_admission()

    def test_full_allowance_and_uncertainty_prevent_dispatch(self):
        runner = capture.Capture.__new__(capture.Capture); runner.clock = {'started': 1}
        with patch.object(capture, 'blocked', return_value=False), patch.object(capture.time, 'monotonic', return_value=2690), patch.object(capture, 'execute') as execute:
            with self.assertRaises(ValueError): runner.command('denied', ['xcrun'], 30)
            execute.assert_not_called()
        with patch.object(capture, 'blocked', return_value=True), patch.object(capture, 'execute') as execute:
            with self.assertRaises(ValueError): runner.command('denied', ['xcrun'], 30)
            execute.assert_not_called()

    def test_summary_is_one_case_exact_device_and_window(self):
        target = {**capture.TARGETS[0], 'udid': '11111111-1111-1111-1111-111111111111'}
        value = {'result': 'Passed', 'totalTestCount': 1, 'passedTests': 1, 'failedTests': 0,
                 'skippedTests': 0, 'expectedFailures': 0, 'testFailures': [], 'runtimeWarnings': [],
                 'startTime': 10.1, 'finishTime': 11.1, 'devicesAndConfigurations': [{'device': {
                    'deviceId': target['udid'], 'modelName': target['model'], 'osVersion': '27.0',
                    'osBuildNumber': '24A434', 'architecture': 'arm64', 'platform': 'iOS Simulator'}}]}
        capture.verify_summary(value, target, 10, 12)
        for key, bad in [('totalTestCount', True), ('passedTests', 2), ('startTime', 9), ('finishTime', float('nan'))]:
            other = copy.deepcopy(value); other[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError): capture.verify_summary(other, target, 10, 12)

    def test_workflow_one_mac_job_and_no_store_operation(self):
        import yaml
        value = yaml.safe_load((ROOT / '.github/workflows/ios-store-screenshots.yml').read_text())
        self.assertEqual(list(value['jobs']), ['capture'])
        job = value['jobs']['capture']
        self.assertEqual(job['runs-on'], 'xcode-27')
        self.assertNotIn('strategy', job)
        self.assertEqual(value['permissions'], {'contents': 'read'})
        text = (ROOT / 'scripts/store_capture.py').read_text()
        self.assertNotIn('sips', text)
        self.assertNotIn('altool', text)
        self.assertNotIn('notarytool', text)
        self.assertNotIn('git push', text)
        self.assertIn("600 if index == 0 else 420", text)
        self.assertIn("['git', 'diff', '--name-only', PUBLIC_PARENT, 'HEAD']", text)
        self.assertIn("(2940 if tail else 2700)", text)
        self.assertIn("time.monotonic() + cap + 20 < endpoint", text)
        self.assertIn("'-maximum-test-execution-time-allowance', '240'", text)
        ui = (ROOT / capture.UI_PATH).read_text()
        result_body = ui.split('- (void)testStoreNormalResultScreenshot {', 1)[1].split('\n}', 1)[0]
        self.assertIn('self.executionTimeAllowance = 180;', result_body)
        self.assertEqual(job['timeout-minutes'], 60)


if __name__ == '__main__':
    unittest.main()
