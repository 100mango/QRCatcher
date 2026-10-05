"""One shell-created, FD-bound Vision command latch; never clear unknown work."""
import json
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
        return command == _ACTIVE.command()
    except (OSError, ValueError):
        return False


class VisionCommandFence:
    def __init__(self, action, nonce):
        self.directory = None; self.descriptor = None
        if action not in {'install', 'shutdown'} or not re.fullmatch(r'[0-9]{1,5}-[0-9]{1,5}-[0-9]+', nonce):
            raise ValueError('Expected one explicit Vision operation and shell nonce')
        root = Path(os.environ['GITHUB_WORKSPACE'])
        if not root.is_absolute() or root.resolve(strict=True) != root or Path.cwd() != root:
            raise ValueError('Fence requires the canonical current workflow checkout')
        if os.environ.get('GITHUB_REPOSITORY') != '100mango/QRCatcher':
            raise ValueError('Unexpected repository')
        source, device, scope = (os.environ[key] for key in ['GITHUB_SHA', 'VISION_SIMULATOR_ID', 'EVIDENCE_SCOPE'])
        if not re.fullmatch('[0-9a-f]{40}', source) or str(uuid.UUID(device)).upper() != device or scope not in {'visionos_photos', 'visionos_files', 'visionos_chinese', 'visionos_largest'}:
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
            self.descriptor = os.open(NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory)
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

    def command(self):
        command = ['xcrun', 'simctl', self.expected['action'], self.expected['device']]
        if self.expected['action'] == 'install':
            command += ['build/VisionTests/Build/Products/Debug-xrsimulator/QRCatcherVision.app']
        return command

    def activate(self):
        global _ACTIVE
        if _ACTIVE is not None:
            raise ValueError('Another fence is already active')
        self.current(); _ACTIVE = self

    def clear_confirmed(self, operation):
        seconds = 90 if self.expected['action'] == 'install' else 45
        if (operation.get('cleanup_confirmed') is not True or operation.get('command') != self.command() or
                operation.get('timeout_seconds') != seconds or type(operation.get('exit')) is not int or
                operation.get('state') not in {'completed', 'timed_out', 'output_limit'}):
            raise ValueError('Owned group cleanup was not confirmed')
        self.current()
        os.unlink(NAME, dir_fd=self.directory)

    def close(self):
        global _ACTIVE
        if _ACTIVE is self: _ACTIVE = None
        for name in ['descriptor', 'directory']:
            value = getattr(self, name, None)
            if value is not None:
                os.close(value); setattr(self, name, None)
