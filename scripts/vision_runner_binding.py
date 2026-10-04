"""Pre-UI public container lookup bound to one current XCTest runner lease.

There is no late discovery or fallback. Every capture revalidates the source,
device, runner, nonce, PID and directory identity established before UI work.
"""
import json
import os
from pathlib import Path
import re
import stat
import uuid

from atomic_json import write_json
from owned_process_barrier import blocked
from watch_process import execute
from vision_case_contract import case_identity

RUNNER = '100mango.QRCatcherVisionUITests.xctrunner'
APP = '100mango.QRCatcher'


def exact_uuid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)).upper() != value:
        raise ValueError('Expected an exact uppercase UUID')
    return value


def read_request(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('Lease/request must be an independent regular file')
    with path.open('rb') as stream:
        raw = stream.read(1025)
    if len(raw) > 1024:
        raise ValueError('Lease/request exceeded 1KB')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Lease/request must be an object')
    return value


class RunnerBinding:
    def __init__(self, device, runner, source_commit, case, device_root=None, lookup=None):
        self.device = exact_uuid(device)
        if runner != RUNNER or not re.fullmatch('[0-9a-f]{40}', source_commit):
            raise ValueError('Unexpected runner/source identity')
        self.runner, self.source = runner, source_commit
        self.case = case
        self.case_identity = case_identity(case, source_commit, device)
        root = Path(device_root) if device_root else Path.home() / 'Library/Developer/CoreSimulator/Devices'
        self.expected = (root / device / 'data/Containers/Data/Application').resolve(strict=True)
        self.lookup = lookup or self._lookup
        self.bound = None

    def _lookup(self, bundle):
        code, output, operation = execute(
            ['xcrun', 'simctl', 'get_app_container', self.device, bundle, 'data'],
            20, output_limit=64 * 1024, tail_limit=8192, echo=False)
        if code != 0 or operation.get('cleanup_confirmed') is not True:
            raise RuntimeError('Pre-UI container lookup failed: ' + json.dumps(operation))
        return output.strip()

    def _container(self, bundle):
        if blocked():
            raise RuntimeError('Owned cleanup barrier forbids container discovery')
        raw = Path(self.lookup(bundle))
        if raw.is_symlink():
            raise ValueError('Symlink container')
        path = raw.resolve(strict=True)
        if path.parent != self.expected or not path.is_dir():
            raise ValueError('Container is outside the exact device data root')
        exact_uuid(path.name)
        return path, self._identity(path)

    @staticmethod
    def _identity(path):
        if path.is_symlink() or not path.is_dir() or path.resolve(strict=True) != path:
            raise ValueError('Container directory changed')
        info = path.stat()
        return info.st_dev, info.st_ino

    def prime(self, lease):
        # Invalidate the previous test's binding even when this new bind fails.
        self.bound = None
        exact_uuid(lease)
        container, identity = self._container(self.runner)
        temporary = container / 'tmp'
        temporary_identity = self._identity(temporary)
        if temporary.resolve(strict=True).parent != container:
            raise ValueError('Runner temporary directory escaped its container')
        request = temporary / ('QRCatcher-runner-' + lease + '.json')
        value = read_request(request)
        if set(value) != {'id', 'runner', 'pid', 'exports', 'case'} or value['id'] != lease or value['runner'] != self.runner:
            raise ValueError('Current runner nonce/product mismatch')
        if type(value['pid']) is not int or value['pid'] <= 0 or type(value['exports']) is not bool:
            raise ValueError('Invalid runner PID or export scope')
        if value['case'] != self.case.name or value['exports'] != (self.case.scope == 'visionos_photos'):
            raise ValueError('Runner method/export scope does not match selected case')
        app = self._container(APP) if value['exports'] else None
        if read_request(request) != value or self._identity(container) != identity or self._identity(temporary) != temporary_identity:
            raise ValueError('Runner changed during binding')
        binding = {'lease': lease, 'container': container, 'identity': identity,
                   'temporary': temporary, 'temporary_identity': temporary_identity,
                   'descriptor': value, 'app': app}
        result = {**self.case_identity, 'success': True, 'device': self.device, 'runner': self.runner,
                  'source_commit': self.source, 'lease': lease, 'pid': value['pid'],
                  'exports': value['exports'], 'container_id': container.name}
        write_json(request.with_suffix('.ack'), result, limit=4096)
        self.bound = binding
        return result

    def current(self):
        if self.bound is None:
            raise ValueError('No verified current runner binding')
        b = self.bound
        if self._identity(b['container']) != b['identity'] or self._identity(b['temporary']) != b['temporary_identity']:
            raise ValueError('Bound runner directory identity changed')
        value = read_request(b['temporary'] / ('QRCatcher-runner-' + b['lease'] + '.json'))
        if value != b['descriptor']:
            raise ValueError('Runner lease/PID changed or became stale')
        return b

    def request(self, identifier, names):
        exact_uuid(identifier)
        b = self.current()
        path = b['temporary'] / ('QRCatcher-capture-' + identifier + '.json')
        value = read_request(path)
        expected = {**self.case_identity, 'id': identifier, 'runner': self.runner, 'lease': b['lease'],
                    'pid': b['descriptor']['pid'], 'source_commit': self.source, 'device': self.device}
        if any(value.get(key) != wanted for key, wanted in expected.items()) or value.get('name') not in names:
            raise ValueError('Capture does not match the current source/device/runner lease')
        if value['name'] in {'vision-exported-qr', 'vision-exported-history'} and b['app'] is None:
            raise ValueError('Export readback was not bound before UI')
        return value, path.with_suffix('.ack')

    def app_container(self):
        b = self.current()
        if b['app'] is None:
            raise ValueError('No pre-UI app container binding')
        path, identity = b['app']
        if self._identity(path) != identity:
            raise ValueError('Bound app container identity changed')
        return path

    def export_bytes(self, test_store, kind):
        """Read only independent files beneath the bound app via no-follow FDs.

        Validate the whole directory chain before opening either leaf. Directory
        file descriptors keep a later rename/symlink swap from redirecting a read.
        Recheck the chain and bound app identity before returning any evidence.
        """
        exact_uuid(test_store)
        if kind not in {'png', 'json'}:
            raise ValueError('Unexpected export kind')
        root = self.app_container()
        paths = [root]
        for component in ['Documents', 'QRCatcherExportTestReceipts', test_store]:
            paths.append(paths[-1] / component)
        identities = [self._identity(path) for path in paths]
        descriptors = []
        try:
            directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            for index, path in enumerate(paths):
                descriptor = os.open(path if index == 0 else path.name, directory_flags,
                                     **({'dir_fd': descriptors[-1]} if index else {}))
                descriptors.append(descriptor)
                info = os.fstat(descriptor)
                if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != identities[index]:
                    raise ValueError('Export directory identity changed')

            def read_leaf(name, limit):
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                     dir_fd=descriptors[-1])
                try:
                    before = os.fstat(descriptor)
                    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= limit:
                        raise ValueError('Export leaf must be an independent bounded regular file')
                    chunks = []
                    remaining = limit + 1
                    while remaining:
                        chunk = os.read(descriptor, min(65536, remaining))
                        if not chunk:
                            break
                        chunks.append(chunk); remaining -= len(chunk)
                    raw = b''.join(chunks)
                    after = os.fstat(descriptor)
                    current = os.stat(name, dir_fd=descriptors[-1], follow_symlinks=False)
                    signature = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink,
                                              item.st_size, item.st_mtime_ns, item.st_ctime_ns)
                    if len(raw) != before.st_size or len(raw) > limit or signature(before) != signature(after) or signature(after) != signature(current):
                        raise ValueError('Export leaf changed during bounded read')
                    return raw
                finally:
                    os.close(descriptor)

            receipt = read_leaf(kind + '.json', 2048)
            saved = read_leaf('saved.' + kind, 2 * 1024 * 1024)
            if self.app_container() != root or [self._identity(path) for path in paths] != identities:
                raise ValueError('Export directory chain changed during read')
            return receipt, saved
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def acknowledge(self, identifier, names, result):
        # Revalidate again before any ACK, including after a failed command.
        _, acknowledgement = self.request(identifier, names)
        write_json(acknowledgement, result, limit=16 * 1024)
