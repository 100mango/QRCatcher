"""Synthetic package/command doubles verify the gate; no Apple build proof."""
import contextlib, io, json, os, plistlib, runpy, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

class EmbeddedWatchGateTests(unittest.TestCase):
    def check(self, kind='device', defect=None):
        config, phone_sdk, watch_sdk = ('Release', 'iphoneos', 'watchos') if kind == 'device' else ('Debug', 'iphonesimulator', 'watchsimulator')
        with tempfile.TemporaryDirectory() as directory:
            old = Path.cwd()
            try:
                os.chdir(directory)
                products = Path('build/iOS/Build/Products')
                parent = products / (config + '-' + phone_sdk) / 'QRCatcher.app'
                producer = products / (config + '-' + watch_sdk) / 'QRCatcherWatch.app'
                producer.mkdir(parents=True)
                parent.mkdir(parents=True)
                base = {'CFBundleShortVersionString': '1.1', 'CFBundleVersion': '2'}
                (parent / 'Info.plist').write_bytes(plistlib.dumps(dict(base, CFBundleIdentifier='100mango.QRCatcher')))
                info = dict(base, CFBundleIdentifier='100mango.QRCatcher.watchkitapp', CFBundleExecutable='QRCatcherWatch',
                            WKCompanionAppBundleIdentifier='100mango.QRCatcher', WKApplication=True, WKRunsIndependentlyOfCompanionApp=True,
                            MinimumOSVersion='9.0', UIDeviceFamily=[4], CFBundleIconName='AppIcon', CFBundleSupportedPlatforms=['WatchOS' if kind == 'device' else 'WatchSimulator'])
                (producer / 'Info.plist').write_bytes(plistlib.dumps(info))
                (producer / 'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps({'NSPrivacyAccessedAPITypes': [], 'NSPrivacyCollectedDataTypes': [], 'NSPrivacyTracking': False}))
                for name in ['QRCatcherWatch', 'Assets.car']:
                    (producer / name).write_bytes(b'synthetic package marker, not executable')
                notices = Path('ThirdParty/ZXingCpp/ThirdPartyNotices.txt')
                notices.parent.mkdir(parents=True)
                notices.write_bytes((ROOT / notices).read_bytes())
                shutil.copyfile(notices, producer / notices.name)
                nested = parent / 'Watch/QRCatcherWatch.app'
                nested.parent.mkdir()
                shutil.copytree(producer, nested)
                if defect == 'bytes': (nested / 'Assets.car').write_bytes(b'mismatched nested asset')

                def command(args, **kwargs):
                    if args[:3] == ['xcrun', 'lipo', '-archs']:
                        return 'arm64\n' if kind == 'simulator' or defect == 'missing_slice' else 'arm64 arm64_32\n'
                    if args[:3] == ['xcrun', 'otool', '-arch']:
                        arch = args[3]
                        minimum = '26.0' if arch == 'arm64' and kind == 'device' else '9.0'
                        if defect == 'minimum': minimum = '27.0'
                        platform = '4' if kind == 'device' else '9'
                        if defect == 'platform': platform = '2'
                        return f'Load command 1\n cmd LC_BUILD_VERSION\n platform {platform}\n minos {minimum}\n sdk 27.0\n'
                    if args[:3] == ['xcrun', 'otool', '-L']: return '/usr/lib/libc++.1.dylib\n'
                    if args[0] == 'strings': return 'ordinary release payload\n'
                    self.fail('Unexpected package inspection command: ' + str(args))

                with patch.object(sys, 'argv', ['verify_embedded_watch.py', kind]), \
                     patch('subprocess.check_output', side_effect=command), contextlib.redirect_stdout(io.StringIO()):
                    if defect:
                        with self.assertRaises(AssertionError):
                            runpy.run_path(str(ROOT / 'scripts/verify_embedded_watch.py'), run_name='__main__')
                    else:
                        runpy.run_path(str(ROOT / 'scripts/verify_embedded_watch.py'), run_name='__main__')
                        report = json.loads(Path('build/native-release-evidence/ios-embedded-watch-' + kind + '.json').read_text())
                        self.assertTrue(report['producer_bundle_bytes_match'])
                        self.assertEqual(report['kind'], kind)
            finally:
                os.chdir(old)

    def test_device_dual_slice_and_exact_nested_bytes(self): self.check()
    def test_simulator_product_is_watchsimulator(self): self.check('simulator')
    def test_stripped_older_watch_slice_rejected(self): self.check(defect='missing_slice')
    def test_wrong_binary_platform_rejected(self): self.check(defect='platform')
    def test_raised_watch_floor_rejected(self): self.check(defect='minimum')
    def test_changed_nested_bytes_rejected(self): self.check(defect='bytes')

if __name__ == '__main__': unittest.main()
