"""Full-resolution JPEG retention outside the held XCTest checkpoint.

Adapted from TouchColor checkpoint_image.py at 398257d / run37555751961:
5 MB source, 450 KB candidate, quality65/45/30, identical dimensions and hashes.
Unlike that original helper, this module always keeps an independent original,
even on failure. Capture, cropping, resizing and product modification are absent.
At most seven sips commands use 50 command seconds plus bounded owned cleanup.
The whole helper has an 80s ceiling inside the caller's 90s collection phase.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from owned_process_barrier import blocked, mark_unconfirmed
from watch_process import execute

MAX_SOURCE_BYTES = 5_000_000
MAX_RETAINED_BYTES = 450_000
DIMENSIONS = (3840, 2160)
QUALITIES = (65, 45, 30)
ORIGINAL_NAME = 'vision-store-result.original.jpg'
RETAINED_NAME = 'vision-store-result.jpg'
FAILURE_NAME = 'vision-store-image-failure.json'
FAILURE_LIMIT = 64 * 1024
OPERATION_LIMIT = 8192
MATURE_SOURCE = '100mango/ColorPicker@398257d30bc465079a73943204ea5c30eca131f1:scripts/checkpoint_image.py'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _canonical(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts,
            'Evidence paths must be absolute and canonical')
    require(path.parent.resolve(strict=True) == path.parent and path.parent.is_dir(),
            'Evidence parent must be a canonical directory without symlinks')
    return path


def _read(path, limit=MAX_SOURCE_BYTES):
    path = _canonical(path)
    require(not path.is_symlink(), 'Evidence must not be a symlink')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= limit,
                'Evidence must be an independent bounded regular file')
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b''.join(chunks)
        after = os.fstat(fd)
        current = path.stat(follow_symlinks=False)
        require(len(data) == before.st_size and len(data) <= limit and
                _signature(before) == _signature(after) == _signature(current),
                'Evidence changed during bounded read')
        return data, _signature(before)
    finally:
        os.close(fd)


def _verify_original(path, original, signature):
    current, identity = _read(path)
    require(identity == signature and current == original,
            'Original screenshot changed; no candidate may qualify')


def _tail(text, limit):
    if limit <= 0: return ''
    return text.encode('utf-8', errors='replace')[-limit:].decode('utf-8', errors='ignore')


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')


def _command(args):
    require(isinstance(args, (list, tuple)) and all(isinstance(arg, str) for arg in args)
            and len(_json_bytes(list(args))) <= 2048, 'Command identity exceeds receipt bound')
    return list(args)


def _record_output(row, text, operation):
    # Keep exact command/exit identities and bound text independently. Trim the
    # output tail further only when JSON escaping would exceed the row cap.
    if isinstance(operation, dict):
        for key in ('state', 'exit', 'original_exit', 'cleanup_confirmed', 'output_bytes', 'elapsed_seconds'):
            value = operation.get(key)
            if value is None or type(value) in (bool, int) or (type(value) is float and math.isfinite(value)):
                if key in operation: row[key] = value
            elif isinstance(value, str): row[key] = _tail(value, 256)
        if 'command' in operation:
            command = _command(operation['command'])
            if command != row['command']: row['executed_command'] = command
        if operation.get('cleanup_error'):
            row['cleanup_error'] = _tail(str(operation['cleanup_error']), 512)
    raw = text if isinstance(text, str) else '<non-text command output>'
    row['returned_output_bytes'] = len(raw.encode('utf-8', errors='replace'))
    row['output_tail'] = _tail(raw, 4096)
    while len(_json_bytes(row)) > OPERATION_LIMIT and row['output_tail']:
        row['output_tail'] = _tail(row['output_tail'], len(row['output_tail'].encode('utf-8')) // 2)
    row['output_tail_truncated'] = len(row['output_tail'].encode('utf-8')) < row['returned_output_bytes']
    require(len(_json_bytes(row)) <= OPERATION_LIMIT, 'Command receipt exceeded its bound')


def _run(args, seconds, runner, context, deadline):
    quality = int(args[6]) if '-s' in args else None
    row = {'command': _command(args), 'timeout_seconds': seconds, 'stage': context['stage'],
           'quality': quality, 'state': 'not_started', 'exit': None, 'output_tail': ''}
    require(len(context['operations']) < 7, 'Image command count exceeds seven')
    context['operations'].append(row)
    require(time.monotonic() + seconds + 3 <= deadline,
            'Image phase cannot admit command plus bounded cleanup')
    require(not blocked(args), 'Owned cleanup barrier forbids image command')
    row['state'] = 'started'
    if quality is not None: context['attempted_qualities'].append(quality)
    try:
        code, text, operation = runner(args, seconds, output_limit=65536, tail_limit=8192, echo=False)
    except BaseException as error:
        # A runner can throw after launching its child or during cleanup. The
        # caller's collection phase is host-only, so latch here before any
        # diagnostic handling can permit a later simulator shutdown command.
        uncertainty = {'state': 'vision_store_image_runner_exception', 'exit': 126,
                       'cleanup_confirmed': False}
        try:
            mark_unconfirmed(uncertainty)
        except BaseException as latch_error:
            if hasattr(error, 'add_note'):
                error.add_note('Store image uncertainty latch persistence failed: ' + _tail(str(latch_error), 512))
        row.update(state='runner_exception', cleanup_confirmed=False, uncertainty_barrier=uncertainty,
                   error_type=type(error).__name__, error=_tail(str(error), 1024))
        # No actual command exit is invented without a completed receipt; 126
        # above is the conservative barrier status, separately identified.
        raise
    _record_output(row, text, operation)
    row['returned_exit'] = code if type(code) is int else None
    require(type(code) is int and isinstance(operation, dict), 'Invalid image command receipt')
    if (code in (124, 125, 126) or operation.get('cleanup_confirmed') is not True
            or operation.get('state') != 'completed' or time.monotonic() >= deadline):
        mark_unconfirmed({'state': 'vision_store_image_command_unconfirmed', 'exit': code,
                          'cleanup_confirmed': operation.get('cleanup_confirmed') is True})
        raise ValueError('Image command timed out, exceeded output, or has unconfirmed cleanup')
    require(code == 0 and operation.get('exit') == 0, 'Image command failed; never retry a failed encoder')
    require(isinstance(text, str) and len(text.encode('utf-8')) <= 65536,
            'Image metadata exceeds its bound')
    return text


def _write_failure(folder, context, error):
    """Best effort, atomic and no-overwrite; never replace the original error."""
    temporary = None
    try:
        destination = _canonical(folder / FAILURE_NAME)
        require(not destination.exists() and not destination.is_symlink(), 'Failure receipt already exists')
        value = {'schema': 1, 'success': False, 'stage': context['stage'],
                 'source_file': ORIGINAL_NAME, 'source_sha256': context.get('source_sha256'),
                 'source_bytes': context.get('source_bytes'), 'attempted_qualities': context['attempted_qualities'],
                 'operations': context['operations'], 'error_type': type(error).__name__,
                 'error': _tail(str(error), 1024), 'cleanup_errors': context.get('cleanup_errors', [])}
        data = _json_bytes(value)
        require(len(data) <= FAILURE_LIMIT, 'Failure receipt exceeds 64 KiB')
        fd, name = tempfile.mkstemp(prefix='.vision-store-receipt-', dir=folder)
        temporary = Path(name)
        with os.fdopen(fd, 'wb') as output:
            output.write(data); output.flush(); os.fsync(output.fileno())
        os.link(temporary, destination, follow_symlinks=False)
        temporary.unlink(); temporary = None
        # Persist the directory entry as well as the complete file contents.
        directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
    except BaseException as receipt_error:
        # Receipt failure must not hide the failure that made these diagnostics
        # necessary. add_note remains visible in the propagated traceback.
        if hasattr(error, 'add_note'):
            error.add_note('Store image failure receipt was not fully persisted: ' + _tail(str(receipt_error), 512))
    finally:
        if temporary is not None:
            try: temporary.unlink(missing_ok=True)
            except BaseException as cleanup_error:
                if hasattr(error, 'add_note'):
                    error.add_note('Store image receipt temporary cleanup failed: ' + _tail(str(cleanup_error), 512))


def _cleanup(work, destination=None, published=None):
    errors = []
    if published is not None:
        try:
            current = destination.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino) == (published.st_dev, published.st_ino): destination.unlink()
        except FileNotFoundError: pass
        except Exception as error: errors.append(_tail(str(error), 512))
    if work is not None:
        for path in (work / 'source.jpg', work / 'candidate.jpg'):
            try: path.unlink(missing_ok=True)
            except Exception as error: errors.append(_tail(str(error), 512))
        try: work.rmdir()
        except Exception as error: errors.append(_tail(str(error), 512))
    return errors


def _metadata(path, runner, context, deadline):
    text = _run(['/usr/bin/sips', '-g', 'format', '-g', 'pixelWidth', '-g', 'pixelHeight',
                 '-g', 'hasAlpha', str(path)], 5, runner, context, deadline)
    fields = {}
    for key in ('format', 'pixelWidth', 'pixelHeight', 'hasAlpha'):
        values = re.findall(r'^\s*' + key + r':\s*(\S+)\s*$', text, re.MULTILINE)
        require(len(values) == 1, 'Missing or ambiguous image metadata: ' + key)
        fields[key] = values[0]
    require(fields['format'].lower() == 'jpeg', 'Store screenshot must decode as JPEG')
    require(fields['hasAlpha'].lower() == 'no', 'Store screenshot must have no alpha')
    require(fields['pixelWidth'].isdigit() and fields['pixelHeight'].isdigit(), 'Invalid image dimensions')
    dimensions = (int(fields['pixelWidth']), int(fields['pixelHeight']))
    require(dimensions == DIMENSIONS, 'Store screenshot dimensions must remain 3840x2160')
    return {'format': 'jpeg', 'dimensions': list(dimensions), 'has_alpha': False}


def _jpeg(data):
    require(data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9'),
            'Screenshot must contain a complete JPEG envelope')


def retain_store_image(original, destination, command_runner=None, *, deadline=None):
    """Return source/retained proof; failure preserves the raw and a receipt.

    Inputs are canonical absolute sibling paths with the fixed names above;
    destination must not exist. command_runner matches watch_process.execute
    for explicit portable doubles. deadline may shorten, never extend, 80s.
    """
    context = {'stage': 'paths', 'operations': [], 'attempted_qualities': []}
    folder = work = published = None
    try:
        original, destination = _canonical(original), _canonical(destination)
        require(original.name == ORIGINAL_NAME and destination.name == RETAINED_NAME,
                'Unexpected Store screenshot filename')
        require(original.parent == destination.parent and original != destination,
                'Original and candidate must be distinct siblings')
        folder = original.parent
        require(not destination.exists() and not destination.is_symlink(), 'Candidate filename collision')
        context['stage'] = 'deadline'
        started = time.monotonic()
        if deadline is None: deadline = started + 80
        require(type(deadline) in (int, float) and math.isfinite(deadline) and
                started < deadline <= started + 80, 'Invalid image phase deadline')
        context['stage'] = 'source_read'
        source, signature = _read(original)
        source_hash = hashlib.sha256(source).hexdigest()
        context.update(source_sha256=source_hash, source_bytes=len(source))
        _jpeg(source)
        runner = command_runner or execute
        context['stage'] = 'source_metadata'
        metadata = _metadata(original, runner, context, deadline)
        _verify_original(original, source, signature)
        context['stage'] = 'disposable_copy'
        work = Path(tempfile.mkdtemp(prefix='.vision-store-image-', dir=folder))
        copy = work / 'source.jpg'; encoded = work / 'candidate.jpg'
        with copy.open('xb') as stream:
            stream.write(source); stream.flush(); os.fsync(stream.fileno())
        chosen = None; candidate = source
        if len(source) <= MAX_RETAINED_BYTES:
            retained = copy
        else:
            retained = encoded
            for quality in QUALITIES:
                context['stage'] = 'encode_quality_' + str(quality)
                encoded.unlink(missing_ok=True)
                _run(['/usr/bin/sips', '-s', 'format', 'jpeg', '-s', 'formatOptions',
                      str(quality), str(copy), '--out', str(encoded)], 10, runner, context, deadline)
                _verify_original(original, source, signature)
                unchanged, _ = _read(copy)
                require(unchanged == source, 'Disposable source copy changed during encoding')
                context['stage'] = 'encoded_read_quality_' + str(quality)
                candidate, _ = _read(encoded)
                _jpeg(candidate)
                context['stage'] = 'encoded_metadata_quality_' + str(quality)
                require(_metadata(encoded, runner, context, deadline) == metadata,
                        'Evidence encoder changed image properties')
                _verify_original(original, source, signature)
                current, _ = _read(encoded)
                require(current == candidate, 'Encoded image changed during metadata inspection')
                if len(candidate) <= MAX_RETAINED_BYTES:
                    chosen = quality
                    break
            else:
                raise ValueError('Full-resolution JPEG could not fit the candidate evidence cap')
        context['stage'] = 'candidate_publication'
        _verify_original(original, source, signature)
        current, _ = _read(retained)
        require(current == candidate, 'Candidate changed before publication')
        require(time.monotonic() < deadline, 'Image phase expired before publication')
        os.link(retained, destination, follow_symlinks=False)
        published = destination.stat(follow_symlinks=False)
        retained.unlink()
        final, _ = _read(destination, MAX_RETAINED_BYTES)
        require(final == candidate, 'Published candidate bytes changed')
        _verify_original(original, source, signature)
        proof = {
            'source_file': original.name, 'source_sha256': source_hash, 'source_bytes': len(source),
            'retained_file': destination.name, 'retained_sha256': hashlib.sha256(candidate).hexdigest(),
            'retained_bytes': len(candidate), **metadata,
            'encoding': 'original JPEG bytes' if chosen is None else 'sips JPEG', 'quality': chosen,
            'resized': False, 'cropped': False, 'source_retained': True,
            'mature_retention_source': MATURE_SOURCE, 'operations': context['operations'],
        }
        context['stage'] = 'temporary_cleanup'
        context['cleanup_errors'] = _cleanup(work)
        require(not context['cleanup_errors'], 'Image temporary cleanup failed')
        work = None
        return proof
    except BaseException as error:
        context.setdefault('cleanup_errors', []).extend(_cleanup(work, destination, published))
        if folder is not None: _write_failure(folder, context, error)
        raise
