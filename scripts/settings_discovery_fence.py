"""FD-bound read-only discovery fence plus unchanged parent-step budget.

Integrated with fixture/Vision pending guards. This fence proves only its
owned host-command lifecycle, never a Settings mutation or release acceptance.
"""
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import uuid
from atomic_json import write_json
import owned_process_barrier as barrier
from watch_process import execute

NAME = 'settings-discovery-inflight.json'
VERSION = 1
PARENT_LIMITS = {'watch': 22 * 60, 'tv': 18 * 60}
DISCOVERY_LIMIT = 180
CLEANUP_RESERVE = 30
_ACTIVE = None


def signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def active_claim_exists():
    return _ACTIVE is not None


def active_claim_is_current(command):
    if _ACTIVE is None:
        return False
    try:
        _ACTIVE.current()
        # Generic prechecks are admitted only while this same controller is idle.
        # Every actual spawn requires the exact command prepared by run().
        return command == _ACTIVE.active_command
    except (OSError, ValueError):
        return False


class SettingsDiscoveryFence:
    def __init__(self, platform, device, nonce, parent_start, clock=time.monotonic):
        self.directory = self.descriptor = None
        self.active_command = None
        self.operations = []
        self.clock = clock
        self.platform, self.device = platform, device
        if platform not in PARENT_LIMITS or str(uuid.UUID(device)).upper() != device:
            raise ValueError('Wrong discovery platform or canonical device')
        if not re.fullmatch(r'[0-9]{1,5}-[0-9]{1,5}-[0-9]+', nonce):
            raise ValueError('Wrong shell nonce')
        if not re.fullmatch(r'[0-9]{1,12}(?:[.][0-9]{1,9})?', parent_start):
            raise ValueError('Missing original parent-step clock')
        self.parent_start = float(parent_start)
        now = clock()
        if not math.isfinite(now) or not 0 < self.parent_start <= now:
            raise ValueError('Invalid or future parent-step origin')
        self.deadline = self.parent_start + PARENT_LIMITS[platform]
        self.discovery_started = now
        self.root = Path(os.environ['GITHUB_WORKSPACE'])
        if not self.root.is_absolute() or self.root.resolve(strict=True) != self.root or Path.cwd() != self.root:
            raise ValueError('Canonical checkout required')
        self.scope = 'watchos' if platform == 'watch' else 'tvos'
        variable = 'WATCH_SIMULATOR_ID' if platform == 'watch' else 'TV_SIMULATOR_ID'
        source = os.environ.get('GITHUB_SHA', '')
        if (not re.fullmatch('[0-9a-f]{40}', source) or os.environ.get('GITHUB_WORKFLOW_SHA') != source or
                os.environ.get('GITHUB_REPOSITORY') != '100mango/QRCatcher' or
                os.environ.get('EVIDENCE_SCOPE') != self.scope or os.environ.get(variable) != device):
            raise ValueError('Wrong source/device/scope')
        self.expected = dict(version=VERSION, source=source, device=device, scope=self.scope,
                             platform=platform, owner_pid=os.getppid(), nonce=nonce,
                             parent_started_monotonic=parent_start)
        self.owner_process = os.getpid()
        self.parent = self.root / 'build'
        try:
            if self.parent.resolve(strict=True) != self.parent:
                raise ValueError('Aliased build directory')
            self.directory = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(self.directory)
            self.parent_identity = (info.st_dev, info.st_ino)
            self.descriptor = os.open(NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory)
            info = os.fstat(self.descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or
                    stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= 2048):
                raise ValueError('Not an independent bounded owner-only latch')
            self.initial_signature = signature(info)
            self.raw = os.read(self.descriptor, 2049)
            value = json.loads(self.raw)
            if value != self.expected or type(value.get('owner_pid')) is not int or type(value.get('version')) is not int:
                raise ValueError('Latch is not owned by this exact controller/parent')
            self.current()
        except BaseException:
            self.close()
            raise

    def current(self):
        if os.getpid() != self.owner_process or os.getppid() != self.expected['owner_pid']:
            raise ValueError('Controller or parent lifetime changed')
        if self.parent.resolve(strict=True) != self.parent:
            raise ValueError('Build path changed')
        info = self.parent.stat()
        if (info.st_dev, info.st_ino) != self.parent_identity:
            raise ValueError('Build directory replaced')
        os.lseek(self.descriptor, 0, os.SEEK_SET)
        if (os.read(self.descriptor, 2049) != self.raw or
                signature(os.fstat(self.descriptor)) != self.initial_signature or
                signature(os.stat(NAME, dir_fd=self.directory, follow_symlinks=False)) != self.initial_signature):
            raise ValueError('Latch changed or disappeared')

    def activate(self):
        global _ACTIVE
        if getattr(barrier, 'SETTINGS_DISCOVERY_FENCE_VERSION', None) != VERSION:
            raise ValueError('Global discovery barrier proposal is not installed')
        if _ACTIVE is not None:
            raise ValueError('Another discovery controller is active')
        self.current()
        _ACTIVE = self
        if barrier.blocked():
            raise ValueError('Another owned cleanup barrier is active')

    def admitted(self):
        self.current()
        return self.deadline - self.clock() >= DISCOVERY_LIMIT + CLEANUP_RESERVE

    def plan(self, command):
        folder = self.parent / ('settings-discovery-' + self.platform)
        fixed = [(['git', 'rev-parse', 'HEAD'], 5, 1024),
                 (['git', 'diff', '--quiet', 'HEAD', '--'], 5, 1024),
                 (['xcrun', 'simctl', 'help', 'listapps'], 5, 8192),
                 (['xcrun', 'simctl', 'list', 'devices', '-j'], 10, 512 * 1024),
                 (['xcrun', 'simctl', 'listapps', self.device], 10, 512 * 1024),
                 (['plutil', '-convert', 'json', '-o', str(folder / 'installed-apps.json'), str(folder / 'installed-apps.plist')], 5, 8192)]
        index = len(self.operations)
        if index < len(fixed):
            expected, cap, limit = fixed[index]
        elif index == len(fixed):
            if len(command) < 2 or command[0] != 'env' or not command[1].startswith('TEST_RUNNER_QRCATCHER_SETTINGS_DISCOVERY='):
                raise ValueError('Unexpected UI invocation')
            raw = command[1].split('=', 1)[1]
            if len(raw.encode()) > 4096:
                raise ValueError('UI contract exceeds cap')
            token = json.loads(raw)
            label = 'Watch' if self.platform == 'watch' else 'TV'
            runtime = 'watchOS' if self.platform == 'watch' else 'tvOS'
            expected_token = dict(platform=self.platform, scope=self.scope, source=self.expected['source'], device=self.device,
                runtime_prefix='com.apple.CoreSimulator.SimRuntime.' + runtime + '-', test_label=label,
                test_class='QRCatcher' + label + 'SettingsDiscovery', nonce=token.get('nonce'),
                setting_change_attempted=False, system_propagation_qualified=False, binary_source_binding_verified=False,
                discovery_protocol='bounded-settings-watch-root-scroll-v1' if self.platform == 'watch' else 'bounded-settings-navigation-v1', settings_bundle=token.get('settings_bundle'))
            if (token != expected_token or any(token.get(key) is not False for key in
                    ['setting_change_attempted', 'system_propagation_qualified', 'binary_source_binding_verified']) or
                    not isinstance(token.get('nonce'), str) or str(uuid.UUID(token['nonce'])) != token['nonce'] or
                    not isinstance(token.get('settings_bundle'), str) or
                    not re.fullmatch(r'com\.apple\.[A-Za-z0-9.-]{1,100}', token['settings_bundle'])):
                raise ValueError('UI contract differs from bounded read-only Settings navigation')
            expected = ['env', command[1], 'xcodebuild', 'test-without-building', '-project', str(self.root / 'QRCatcher.xcodeproj'),
                '-scheme', 'QRCatcher' + label, '-configuration', 'Debug', '-derivedDataPath', str(self.parent / (label + 'Tests')),
                '-destination', 'platform=' + runtime + ' Simulator,id=' + self.device, '-parallel-testing-enabled', 'NO',
                '-maximum-concurrent-test-simulator-destinations', '1', '-collect-test-diagnostics', 'never',
                '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '60',
                '-maximum-test-execution-time-allowance', '60',
                '-only-testing:QRCatcher' + label + 'UITests/QRCatcher' + label + 'SettingsDiscovery/testReadOnlyTextSizeSettingsDiscovery',
                '-resultBundlePath', str(self.root / (label + 'SettingsDiscovery.xcresult')), 'CODE_SIGNING_ALLOWED=NO']
            cap, limit = 90, 512 * 1024
        else:
            raise ValueError('Discovery command repetition is forbidden')
        if command != expected:
            raise ValueError('Command differs from the single ordered discovery plan')
        return cap, limit

    def run(self, command, seconds, **options):
        self.current()
        if self.active_command is not None:
            raise ValueError('Concurrent discovery command')
        cap, limit = self.plan(command)
        if (type(seconds) not in {int, float} or not math.isfinite(seconds) or not 0 < seconds <= cap or
                options != dict(output_limit=limit, tail_limit=limit, echo=False)):
            raise ValueError('Unexpected discovery command budget/options')
        available = min(self.deadline - self.clock() - CLEANUP_RESERVE,
                        DISCOVERY_LIMIT - (self.clock() - self.discovery_started) - 3)
        if available <= 0:
            raise ValueError('Existing parent/discovery deadline exhausted')
        allotted = min(seconds, available)
        self.active_command = list(command)
        # The immutable shell latch already protects a kill at every point here.
        write_json(self.parent / ('settings-discovery-' + self.platform + '-progress.json'),
                   dict(self.expected, command=command, index=len(self.operations), phase='before_command',
                        timeout_seconds=allotted, parent_deadline_monotonic=self.deadline), limit=12 * 1024)
        code, text, operation = execute(command, allotted, **options)
        self.operations.append(operation)
        if (operation.get('command') != command or operation.get('timeout_seconds') != allotted or
                operation.get('cleanup_confirmed') is not True or operation.get('state') != 'completed' or
                operation.get('exit') != code or type(code) is not int or
                'QRCATCHER_UNEXPECTED_INTERRUPTION_ABORT_BEFORE_UI_ACTION' in text):
            raise ValueError('Discovery command completion/cleanup is unresolved')
        self.current()
        self.active_command = None
        return code, text, operation

    def finish_without_commands(self, reason):
        if self.operations or self.active_command is not None:
            raise ValueError('Commands already started')
        self.finish(dict(source=self.expected['source'], device=self.device, platform=self.platform,
                         setting_change_attempted=False, system_propagation_qualified=False,
                         status='read_only_discovery_stopped_unqualified', operations=[], error=reason))

    def finish(self, report):
        self.current()
        if self.active_command is not None or barrier.blocked():
            raise ValueError('Unresolved owned discovery command')
        if (report.get('source') != self.expected['source'] or report.get('device') != self.device or
                report.get('platform') != self.platform or report.get('setting_change_attempted') is not False or
                report.get('system_propagation_qualified') is not False or report.get('cleanup_unconfirmed') or
                report.get('status') not in {'read_only_discovery_complete_unqualified', 'read_only_discovery_stopped_unqualified'} or
                [row.get('operation') for row in report.get('operations', [])] != self.operations):
            raise ValueError('Missing matching terminal diagnostic report')
        receipt = dict(self.expected, operations=self.operations, status=report['status'],
                       cleanup_confirmed=True, system_propagation_qualified=False,
                       parent_deadline_monotonic=self.deadline, finished_monotonic=self.clock(),
                       required_admission_seconds=DISCOVERY_LIMIT + CLEANUP_RESERVE,
                       remaining_parent_seconds=round(self.deadline - self.clock(), 3),
                       reason=str(report.get('error', ''))[:512])
        raw = (json.dumps(receipt, allow_nan=False, indent=2) + '\n').encode()
        if len(raw) > 24 * 1024:
            raise ValueError('Fence receipt exceeds cap')
        descriptor = os.open('settings-discovery-' + self.platform + '-fence.json',
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.directory)
        with os.fdopen(descriptor, 'wb') as output:
            output.write(raw); output.flush(); os.fsync(output.fileno())
        self.current()
        os.unlink(NAME, dir_fd=self.directory)
        print('SETTINGS_FENCE_CLEARED_CONFIRMED_UNQUALIFIED', flush=True)

    def close(self):
        global _ACTIVE
        if _ACTIVE is self:
            _ACTIVE = None
        for name in ['descriptor', 'directory']:
            descriptor = getattr(self, name, None)
            if descriptor is not None:
                os.close(descriptor); setattr(self, name, None)

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()
