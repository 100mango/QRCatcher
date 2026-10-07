"""One shell-created, FD-bound Vision command latch; never clear unknown work."""
import json
import math
import os
from pathlib import Path
import re
import stat
import uuid

NAME = 'vision-command-inflight.json'
_ACTIVE = None


def active_claim_exists():
    return _ACTIVE is not None


def signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def active_claim_is_current(command):
    if _ACTIVE is None:
        return False
    try:
        _ACTIVE.current()
        return not _ACTIVE.uncertain and command == _ACTIVE.command()
    except (OSError, ValueError):
        return False


class VisionCommandFence:
    def __init__(self, action, nonce):
        self.directory = None; self.descriptor = None
        self.uncertain = False; self.observed = False
        if action not in {'install', 'shutdown', 'inventory', 'boot', 'bootstatus'} or not re.fullmatch(r'[0-9]{1,5}-[0-9]{1,5}-[0-9]+', nonce):
            raise ValueError('Expected one explicit Vision operation and shell nonce')
        root = Path(os.environ['GITHUB_WORKSPACE'])
        if not root.is_absolute() or root.resolve(strict=True) != root or Path.cwd() != root:
            raise ValueError('Fence requires the canonical current workflow checkout')
        if os.environ.get('GITHUB_REPOSITORY') != '100mango/QRCatcher':
            raise ValueError('Unexpected repository')
        source, scope = (os.environ[key] for key in ['GITHUB_SHA', 'EVIDENCE_SCOPE'])
        device = None if action == 'inventory' else os.environ['VISION_SIMULATOR_ID']
        if not re.fullmatch('[0-9a-f]{40}', source) or (action != 'inventory' and str(uuid.UUID(device)).upper() != device) or scope not in {'visionos_photos', 'visionos_files', 'visionos_chinese', 'visionos_largest', 'visionos_privacy'}:
            raise ValueError('Unexpected source/device/scope')
        self.expected = {'version': 1, 'source': source, 'device': device, 'scope': scope,
                         'action': action, 'owner_pid': os.getppid(), 'nonce': nonce}
        self.owner_process = os.getpid()
        self.parent = root / 'build'
        if self.parent.resolve(strict=True) != self.parent:
            raise ValueError('Fence directory must not be aliased')
        try:
            self.directory = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(self.directory)
            self.parent_identity = (info.st_dev, info.st_ino)
            self.descriptor = os.open(NAME, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory)
            before = os.fstat(self.descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600 or not 0 < before.st_size <= 1024:
                raise ValueError('Fence must be an independent bounded owner-only regular file')
            self.initial_signature = signature(before)
            self.raw = os.read(self.descriptor, 1025)
            value = json.loads(self.raw)
            if value != self.expected or type(value.get('version')) is not int or type(value.get('owner_pid')) is not int:
                raise ValueError('Fence does not belong to this source/device/action/parent shell')
            self.current()
        except BaseException:
            self.close()
            raise

    def current(self):
        if os.getpid() != self.owner_process or os.getppid() != self.expected['owner_pid']:
            raise ValueError('Fence command or parent shell lifetime changed')
        if self.parent.resolve(strict=True) != self.parent:
            raise ValueError('Fence directory path changed')
        now = self.parent.stat()
        if (now.st_dev, now.st_ino) != self.parent_identity:
            raise ValueError('Fence directory identity changed')
        os.lseek(self.descriptor, 0, os.SEEK_SET)
        raw = os.read(self.descriptor, 1025)
        info = os.fstat(self.descriptor)
        current = os.stat(NAME, dir_fd=self.directory, follow_symlinks=False)
        if raw != self.raw or signature(info) != self.initial_signature or signature(current) != self.initial_signature:
            raise ValueError('Fence identity or bytes changed')
        return True

    def seconds(self):
        return {'install': 90, 'shutdown': 45, 'inventory': 30, 'boot': 180, 'bootstatus': 420}[self.expected['action']]

    def command(self):
        if self.expected['action'] == 'inventory':
            return ['xcrun', 'simctl', 'list', 'devices', 'available', '-j']
        command = ['xcrun', 'simctl', self.expected['action'], self.expected['device']]
        if self.expected['action'] == 'install':
            command += ['build/VisionTests/Build/Products/Debug-xrsimulator/QRCatcherVision.app']
        if self.expected['action'] == 'bootstatus': command.append('-b')
        return command

    def _write_claimed(self, expected):
        self.current()
        # Consume the shell grant before dispatch. A fresh controller, even in
        # the same shell with the same nonce, cannot reclaim an issued command.
        # Partial writes remain a blocking latch; no child starts before fsync.
        raw = (json.dumps({**expected, 'state': 'claimed',
                           'controller_pid': self.owner_process}) + '\n').encode()
        os.lseek(self.descriptor, 0, os.SEEK_SET)
        written = 0
        while written < len(raw):
            count = os.write(self.descriptor, raw[written:])
            if count <= 0: raise OSError('Incomplete fence claim write')
            written += count
        os.ftruncate(self.descriptor, len(raw))
        os.fsync(self.descriptor)
        claimed_signature = signature(os.fstat(self.descriptor))
        if claimed_signature[:5] != self.initial_signature[:5]:
            raise ValueError('Fence ownership changed during claim')
        self.raw = raw; self.initial_signature = claimed_signature
        self.expected = expected
        self.current()

    def activate(self):
        global _ACTIVE
        if _ACTIVE is not None:
            raise ValueError('Another fence is already active')
        self._write_claimed(self.expected); _ACTIVE = self

    def advance_probe(self, action, device):
        # One bootstrap owner retains its latch until final readiness. There is
        # no clear/recreate gap between inventory, accepted boot and bootstatus.
        current = self.expected['action']
        if (not self.observed or self.uncertain or
                (current, action) not in {('inventory', 'boot'), ('boot', 'bootstatus')}):
            self.uncertain = True
            raise ValueError('Invalid or uncertain bootstrap transition')
        self.uncertain = True
        if str(uuid.UUID(device)).upper() != device or (current == 'boot' and device != self.expected['device']):
            raise ValueError('Bootstrap transition changed device identity')
        self._write_claimed({**self.expected, 'action': action, 'device': device})
        self.observed = False; self.uncertain = False

    def observe(self, operation, code):
        # Host process-group cleanup proves no daemon/device completion. Once
        # uncertain, late completion and subsequent observations cannot reset it.
        was_uncertain = self.uncertain
        self.uncertain = True; self.observed = True
        seconds = self.seconds()
        elapsed = operation.get('elapsed_seconds')
        confirmed = (operation.get('cleanup_confirmed') is True and
                     operation.get('command') == self.command() and
                     operation.get('timeout_seconds') == seconds and
                     type(code) is int and code >= 0 and operation.get('exit') == code and
                     type(operation.get('exit')) is int and code not in {124, 125, 126} and
                     operation.get('state') == 'completed' and
                     type(elapsed) in {int, float} and math.isfinite(elapsed) and 0 <= elapsed <= seconds)
        self.uncertain = was_uncertain or not confirmed
        return not self.uncertain

    def clear_confirmed(self, operation):
        if self.expected['action'] in {'inventory', 'boot'}:
            self.uncertain = True
            raise ValueError('Incomplete bootstrap cannot clear its owner latch')
        if not self.observed or not self.observe(operation, operation.get('exit')):
            raise ValueError('Device command completion is uncertain; retain latch until VM disposal')
        self.current()
        os.unlink(NAME, dir_fd=self.directory)

    def close(self):
        global _ACTIVE
        if _ACTIVE is self: _ACTIVE = None
        for name in ['descriptor', 'directory']:
            value = getattr(self, name, None)
            if value is not None:
                os.close(value); setattr(self, name, None)
