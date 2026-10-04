"""One current-lease, non-AX failure image; never required success evidence."""
import hashlib
import os
import selectors
import subprocess
import tempfile
import time
from pathlib import Path
import stat

from atomic_json import write_json
from owned_process_barrier import blocked, mark_unconfirmed


def file_signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def bounded_bytes(path, limit, directory=None):
    options = {'dir_fd': directory} if directory is not None else {}
    name = path.name if directory is not None else path
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, **options)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= limit:
            raise ValueError('Failure image is not an independent bounded regular file')
        chunks = []; remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk: break
            chunks.append(chunk); remaining -= len(chunk)
        value = b''.join(chunks)
        after = os.fstat(descriptor); current = os.stat(name, follow_symlinks=False, **options)
        if len(value) != before.st_size or len(value) > limit or file_signature(before) != file_signature(after) or file_signature(after) != file_signature(current):
            raise ValueError('Failure image changed during bounded read')
        return value, file_signature(after)
    finally:
        os.close(descriptor)


def execute(args, seconds, output_limit=64 * 1024, tail_limit=1600, echo=False):
    """Use the collector's owned group; never create an escaping child session.

    The driver always stop_group(capture) after helper completion or its existing
    30s wait. Local timeouts kill only our direct child, record deferred group
    cleanup, and set the durable barrier before any subsequent command.
    """
    if blocked():
        return 126, '', {'state': 'blocked', 'exit': 126, 'leader_reaped': False}
    started = time.monotonic()
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=False)
    operation = {'command': args, 'timeout_seconds': seconds,
                 'collector_group_id': os.getpgrp(), 'leader_pid': process.pid,
                 'cleanup_owner': 'collector_process_group', 'cleanup_deferred_to_collector': True}
    selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
    tail = bytearray(); total = 0; forced = None
    try:
        while selector.get_map():
            if time.monotonic() - started >= seconds: forced = 124; break
            for key, _ in selector.select(timeout=min(.1, max(0, seconds - (time.monotonic() - started)))):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk: selector.unregister(key.fileobj); continue
                total += len(chunk); tail.extend(chunk)
                if len(tail) > tail_limit: del tail[:-tail_limit]
                if total > output_limit: forced = 125; break
            if forced is not None: break
        if forced is None:
            try: code = process.wait(timeout=max(.01, seconds - (time.monotonic() - started)))
            except subprocess.TimeoutExpired: forced = 124; code = 124
        else: code = forced
    except BaseException as error:
        forced = 126; code = 126; operation['error'] = str(error)[:1600]
    finally:
        if process.poll() is None:
            try: process.kill()
            except ProcessLookupError: pass
            try: process.wait(timeout=1)
            except subprocess.TimeoutExpired: pass
        selector.close(); process.stdout.close()
    reaped = process.poll() is not None
    operation.update(state='completed' if forced is None and reaped else 'cleanup_deferred',
                     exit=code, leader_reaped=reaped, output_bytes=total,
                     elapsed_seconds=round(time.monotonic() - started, 3))
    if forced is not None or not reaped:
        operation['cleanup_confirmed'] = False
        mark_unconfirmed(operation)
    return code, tail.decode(errors='replace'), operation


class FailureDiagnostic:
    def __init__(self, binding, output):
        self.binding = binding
        self.output = Path(output).absolute()
        if self.output.resolve(strict=True) != self.output or not self.output.is_dir():
            raise ValueError('Diagnostic output must be a canonical owned directory')
        info = self.output.stat(); self.output_identity = (info.st_dev, info.st_ino)
        self.attempted = False
        self.row = None

    def observe(self, text):
        # Exact existing XCTest producer format. Unknown methods and ordinary
        # progress text cannot trigger a diagnostic simulator command.
        marker = 'error: -[QRCatcherVisionUITests.QRCatcherVisionUITests ' + self.binding.case.name + '] :'
        if not self.attempted and marker in text:
            self.capture('matching XCTest failure')

    def capture(self, reason):
        if self.attempted:
            return self.row
        self.attempted = True
        row = {**self.binding.case_identity, 'diagnostic_only': True, 'success': False,
               'capture_success': False, 'pixels_retained': False, 'reason': reason}
        self.row = row
        final = self.output / 'vision-host-failure.jpg'
        raw = None; jpeg = None; temporary = None; created = {}
        output_fd = None; attempt_fd = None
        try:
            b = self.binding.current()
            row.update(lease=b['lease'], runner=self.binding.runner, pid=b['descriptor']['pid'])
            if blocked():
                raise RuntimeError('Owned cleanup barrier forbids failure image')
            info = self.output.stat()
            if self.output.resolve(strict=True) != self.output or (info.st_dev, info.st_ino) != self.output_identity:
                raise ValueError('Diagnostic output directory changed')
            if final.exists() or final.is_symlink():
                raise ValueError('Failure diagnostic output already exists')
            output_fd = os.open(self.output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            root_info = os.fstat(output_fd)
            if (root_info.st_dev, root_info.st_ino) != self.output_identity:
                raise ValueError('Diagnostic directory descriptor identity changed')
            temporary = Path(tempfile.mkdtemp(prefix='vision-failure-', dir=self.output))
            if stat.S_IMODE(temporary.stat().st_mode) != 0o700:
                raise ValueError('Diagnostic attempt directory must remain private')
            attempt_identity = (temporary.stat().st_dev, temporary.stat().st_ino)
            attempt_fd = os.open(temporary.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=output_fd)
            def verify_attempt():
                info = os.fstat(attempt_fd); current = temporary.lstat()
                if temporary.resolve(strict=True) != temporary or (info.st_dev, info.st_ino) != attempt_identity or (current.st_dev, current.st_ino) != attempt_identity or stat.S_IMODE(info.st_mode) != 0o700:
                    raise ValueError('Private diagnostic directory identity changed')
            verify_attempt()
            raw = temporary / 'raw.png'; jpeg = temporary / 'frame.jpg'
            code, _, operation = execute(
                ['xcrun', 'simctl', 'io', self.binding.device, 'screenshot', str(raw)],
                20, output_limit=64 * 1024, tail_limit=1600, echo=False)
            row['screenshot'] = operation
            self.binding.current()
            if operation.get('state') != 'completed' or operation.get('leader_reaped') is not True or blocked():
                raise RuntimeError('Failure screenshot cleanup is unresolved')
            verify_attempt()
            raw_bytes, raw_signature = bounded_bytes(raw, 32 * 1024 * 1024, attempt_fd)
            created[raw] = raw_signature
            converted, _, conversion = execute(
                ['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '40', '-Z', '960', str(raw), '--out', str(jpeg)],
                12, output_limit=64 * 1024, tail_limit=1600, echo=False)
            row['conversion'] = conversion
            self.binding.current()
            if converted != 0 or conversion.get('state') != 'completed' or conversion.get('leader_reaped') is not True or blocked():
                raise RuntimeError('Failure image conversion did not finish cleanly')
            verify_attempt()
            data, jpeg_signature = bounded_bytes(jpeg, 160 * 1024, attempt_fd)
            created[jpeg] = jpeg_signature
            checked_raw, checked_signature = bounded_bytes(raw, 32 * 1024 * 1024, attempt_fd)
            if checked_raw != raw_bytes or checked_signature != raw_signature:
                raise ValueError('Exact screenshot bytes changed during conversion')
            info = self.output.stat()
            if self.output.resolve(strict=True) != self.output or (info.st_dev, info.st_ino) != self.output_identity:
                raise ValueError('Diagnostic output directory changed before publication')
            if not data.startswith(b'\xff\xd8'):
                raise ValueError('Failure image is not a JPEG')
            # Exclusive publication cannot overwrite an earlier frame. The
            # bytes came from bounded no-follow reads in this private attempt.
            descriptor = os.open(final.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=output_fd)
            with os.fdopen(descriptor, 'wb') as stream: stream.write(data)
            row.update(capture_success=code == 0, pixels_retained=True, file=final.name,
                       bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        except Exception as error:
            row['error'] = str(error)[:1600]
        finally:
            # Only entries created and verified by this attempt are removed.
            # Unknown/changed partial output stays private and is not exported.
            for path, signature in created.items():
                try:
                    if file_signature(os.stat(path.name, dir_fd=attempt_fd, follow_symlinks=False)) == signature:
                        os.unlink(path.name, dir_fd=attempt_fd)
                except FileNotFoundError: pass
            if attempt_fd is not None: os.close(attempt_fd)
            if output_fd is not None: os.close(output_fd)
            # Private attempt directories and any unverifiable partial files
            # are left for disposable VM teardown, never enumerated/exported.
            write_json(self.output / 'host-failure-capture.json', row, limit=16 * 1024)
        return row
