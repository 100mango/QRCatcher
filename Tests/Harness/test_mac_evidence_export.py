"""Exporter contract tests with command/file doubles, not app-runtime evidence."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import struct
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/export_mac_screenshots.py'
CONTROLS = ['mac-before-resize', 'mac-minimum-window', 'mac-before-export', 'mac-pasted-url']
NEW = ['mac-chinese-reopened', 'mac-minimum-long-text-en', 'mac-minimum-long-text-zh-Hans']
REQUIRED = CONTROLS + NEW
ORDINARY = ['mac-system-picker-before-selection','mac-system-picker-after-selection','mac-real-photos-import',
            'mac-sandbox-legacy-reopened','mac-chinese-policy','mac-english-policy','mac-reopened-history',
            'mac-camera-unavailable','mac-imported-unicode']
ALL = REQUIRED + ORDINARY


class MacEvidenceExportTests(unittest.TestCase):
    def export(self, names, *, same_pixels=(), allocation=3_000_000, jpeg_names=(), extra_png=(), native=(), payload_size=0, audit=False, metadata="name"):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'scripts').mkdir()
            (root / 'scripts/evidence-allocation.json').write_text(json.dumps({'scope_limits_bytes': {'macos': allocation}}))
            for result in ['MacSandboxResults.xcresult']+(['MacTestResults.xcresult'] if native else []):
                (root/result).mkdir();(root/result/'Info.plist').write_text('fixture')

            def output(command, **kwargs):
                if command == ['git', 'rev-parse', 'HEAD']: return 'a' * 40 + '\n'
                if command == ['git', 'rev-parse', 'HEAD^{tree}']: return 'b' * 40 + '\n'
                if command == ['xcodebuild', '-version']: return 'Xcode fixture\n'
                if command == ['uname', '-m']: return 'arm64\n'
                raise AssertionError(command)

            expected_payloads = {}

            def run(command, **kwargs):
                if command[1:5] == ['xcresulttool', 'get', 'test-results', 'summary']:
                    return subprocess.CompletedProcess(command, 0, json.dumps({'runtimeWarnings': []}), '')
                if command[1:4] == ['xcresulttool', 'export', 'attachments']:
                    destination = root / command[-1]
                    destination.mkdir(parents=True, exist_ok=True)
                    entries = []
                    scope=destination.name
                    for number, name in enumerate(names if scope=='sandbox' else native):
                        filename = f'{number}.bin'
                        # Synthetic bytes exercise retention only, never UI proof.
                        body = b'same' if name in same_pixels else (scope+name).encode()
                        body += b'x'*max(0,payload_size-len(body))
                        if (name in REQUIRED and name not in jpeg_names) or name in extra_png:
                            payload = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + struct.pack('>II', 1024, 768) + body
                        else: payload = b'\xff\xd8' + body
                        expected_payloads[(scope,name)] = payload
                        (destination / filename).write_bytes(payload)
                        record={'exportedFileName':filename}
                        if metadata=='name':record['name']=name
                        elif metadata=='decorated':record['suggestedHumanReadableName']=name+'_0_C17CB4FC-D16E-4FA8-9551-EDA6E400A4D2.'+('png' if payload.startswith(b'\x89PNG') else 'jpeg')
                        else:record.update(metadata(name))
                        entries.append(record)
                    if audit:
                        (destination/'audit.txt').write_text('strict audit finding')
                        entries.append({'name':'mac-audit-element','exportedFileName':'audit.txt'})
                    (destination / 'manifest.json').write_text(json.dumps(entries))
                    return subprocess.CompletedProcess(command, 0, '', '')
                raise AssertionError(command)

            previous = os.getcwd()
            try:
                os.chdir(root)
                with patch('subprocess.check_output', output), patch('subprocess.run', run), contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(str(SCRIPT), run_name='__main__')
                manifest = json.loads((root / 'build/mac-evidence/screenshots.json').read_text())
                for item in manifest:
                    self.assertEqual((root / 'build/mac-evidence' / item['name']).read_bytes(), expected_payloads[(item['scope'],item['checkpoint'])])
                size = sum(p.stat().st_size for p in (root / 'build/mac-evidence').iterdir())
                return manifest, size
            finally:
                evidence=root/'build/mac-evidence'
                self.last_files={p.name:p.read_bytes() for p in evidence.iterdir()} if evidence.exists() else {}
                self.last_manifest=json.loads(self.last_files.get('screenshots.json',b'[]'))
                self.last_coverage=json.loads(self.last_files.get('frame-coverage.json',b'{}'))
                os.chdir(previous)

    def test_all_existing_and_new_checkpoints_retained(self):
        manifest,size=self.export(ALL,audit=True)
        self.assertEqual(len(manifest),16)
        self.assertEqual({x['checkpoint'] for x in manifest},set(ALL))
        self.assertLessEqual(size,3_000_000)
        self.assertTrue(self.last_coverage['complete'])
        self.assertEqual(self.last_files['sandbox-audit-1.txt'],b'strict audit finding')

    def test_seven_exact_pngs_preserve_bytes_and_native_dimensions(self):
        manifest,_=self.export(REQUIRED)
        self.assertTrue(all(x['name'].endswith('.png') and x['source_bytes_preserved'] for x in manifest))
        self.assertTrue(all(x['native_pixel_dimensions']==[1024,768] for x in manifest))

    def test_no_lossless_frame_can_silently_fall_back_to_jpeg(self):
        for name in REQUIRED:
            with self.assertRaisesRegex(ValueError,'require native PNG'):self.export(REQUIRED,jpeg_names=[name])

    def test_unrequested_checkpoint_cannot_expand_png_scope(self):
        with self.assertRaisesRegex(ValueError,'Only exact allowlisted'):self.export(REQUIRED+['mac-failure'],extra_png=['mac-failure'])

    def test_missing_each_original_control_fails_closed(self):
        for name in CONTROLS:
            with self.assertRaisesRegex(SystemExit,name):self.export([x for x in REQUIRED if x!=name])

    def test_missing_each_new_readability_frame_fails_closed(self):
        for name in NEW:
            with self.assertRaisesRegex(SystemExit,name):self.export([x for x in REQUIRED if x!=name])
            self.assertFalse(self.last_coverage['complete'])

    def test_identical_bytes_preserve_checkpoint_alias_without_double_count(self):
        manifest,_=self.export(REQUIRED,same_pixels=['mac-before-resize','mac-minimum-window'])
        self.assertEqual(len(manifest),6)
        self.assertTrue(any('mac-before-resize' in x.get('additional_checkpoint_names',[]) for x in manifest))
        self.assertTrue(self.last_coverage['complete'])

    def test_byte_cap_cannot_silently_drop_mandatory_control(self):
        with self.assertRaisesRegex(SystemExit,'Required fixed-state Mac control evidence missing'):self.export(REQUIRED,allocation=256*1024)
        self.assertFalse(self.last_coverage['complete'])

    def test_sixteen_cap_preserves_all_ordinary_before_optional_failure(self):
        manifest,size=self.export(['mac-failure']+ALL)
        self.assertEqual(len(manifest),16)
        self.assertEqual({x['checkpoint'] for x in manifest},set(ALL))
        self.assertLessEqual(size,3_000_000)

    def test_priority_is_global_across_result_bundles(self):
        manifest,_=self.export(['mac-failure']+ORDINARY,native=REQUIRED)
        self.assertEqual(len(manifest),16)
        self.assertEqual({x['checkpoint'] for x in manifest},set(ALL))

    def test_duplicate_ordinary_checkpoint_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate Mac checkpoint'):
            self.export(ALL,native=ALL)
        with self.assertRaisesRegex(ValueError,'Duplicate Mac checkpoint'):
            self.export(REQUIRED+[REQUIRED[0]],metadata='decorated')
        manifest,_=self.export(REQUIRED+['mac-failure','mac-failure'])
        self.assertEqual(sum(x['checkpoint']=='mac-failure' for x in manifest),1)

    def test_unknown_longer_names_cannot_count_as_required(self):
        unknown='mac-minimum-long-text-en-extra'
        with self.assertRaisesRegex(ValueError,'Malformed Mac checkpoint metadata'):
            self.export([x for x in REQUIRED if x!='mac-minimum-long-text-en']+[unknown],extra_png=[unknown])
        self.assertFalse(any(x['checkpoint']==unknown for x in self.last_manifest))

    def test_observed_xcresult_decorated_suggestions_round_trip(self):
        # Decoration copied from the retained 2e7689 xcresulttool output;
        # synthetic image bytes still do not establish native rendering.
        manifest,_=self.export(ALL,metadata='decorated')
        self.assertEqual({x['checkpoint'] for x in manifest},set(ALL))
        self.assertEqual(len(manifest),16)

    def test_conflicting_explicit_and_suggested_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,'Conflicting Mac checkpoint metadata'):
            self.export(REQUIRED,metadata=lambda name:dict(name=name,suggestedHumanReadableName=('mac-before-export' if name!='mac-before-export' else 'mac-pasted-url')))

    def test_malformed_decorations_cannot_supply_required_evidence(self):
        for suffix in ['_0_not-a-uuid.png','_01_C17CB4FC-D16E-4FA8-9551-EDA6E400A4D2.png',
                       '_0_C17CB4FC-D16E-4FA8-9551-EDA6E400A4D2.png.extra','_0_C17CB4FC-D16E-4FA8-9551-EDA6E400A4D2.txt',
                       '_0_C17CB4FC-D16E-4FA8-9551-EDA6E400A4D2.png/mac-pasted-url']:
            with self.assertRaisesRegex(ValueError,'Malformed Mac checkpoint metadata'):
                self.export(REQUIRED,metadata=lambda name:dict(suggestedHumanReadableName=name+suffix))

    def test_byte_cap_prioritizes_mandatory_but_omission_stays_incomplete(self):
        with self.assertRaisesRegex(SystemExit,'Emitted ordinary Mac evidence omitted at cap'):
            self.export(['mac-failure']+ORDINARY+REQUIRED,payload_size=190000)
        self.assertTrue(set(REQUIRED)<={x['checkpoint'] for x in self.last_manifest})
        self.assertFalse(self.last_coverage['complete'])
        self.assertTrue(self.last_coverage['omitted_emitted'])


if __name__ == '__main__':unittest.main()
