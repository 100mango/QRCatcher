#!/usr/bin/env python3
"""One held real UI capture. Preserve original JPEG on every failure; never retry.

Encoding and final Store verification happen after XCTest in a host-only phase.
No export, screenshot resizing, synthesized UI, late app lookup, or extra capture.
"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import struct
import sys
import time

from atomic_json import write_json
from owned_process_barrier import blocked, mark_unconfirmed
from watch_process import execute
from vision_runner_binding import RunnerBinding, exact_uuid, RUNNER
from run_vision_ui_cases import native_operation_unconfirmed
from vision_case_contract import select_case
from export_vision_case_evidence import bounded_file

NAME = 'vision-store-result'
ORIGINAL = NAME + '.original.jpg'
MAX_SOURCE_BYTES = 5_000_000


def jpeg_dimensions(data):
    """Read only JPEG marker structure, never guess format from an extension."""
    if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise ValueError('Incomplete original JPEG')
    offset = 2
    while offset < len(data):
        if data[offset] != 255:
            raise ValueError('Invalid JPEG segment marker')
        while offset < len(data) and data[offset] == 255:
            offset += 1
        if offset >= len(data): break
        marker = data[offset]; offset += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7: continue
        if marker == 0xDA: break
        if offset + 2 > len(data): raise ValueError('Truncated JPEG length')
        length = struct.unpack('>H', data[offset:offset + 2])[0]
        if length < 2 or offset + length > len(data): raise ValueError('Truncated JPEG segment')
        if marker in (0xC0, 0xC1, 0xC2):
            if length < 8: raise ValueError('Truncated JPEG frame')
            precision, height, width, channels = struct.unpack('>BHHB', data[offset + 2:offset + 8])
            if precision != 8 or channels != 3 or length != 8 + 3 * channels:
                raise ValueError('Expected 8-bit three-channel JPEG')
            return [width, height]
        offset += length
    raise ValueError('JPEG has no supported complete frame')


def lookup_runner(out, device, bundle, runner=execute):
    if bundle != RUNNER or blocked(): raise ValueError('Store binding forbids unexpected container lookup')
    receipt = out / 'store-runner-lookup.json'
    if receipt.exists() or receipt.is_symlink(): raise ValueError('Store lookup cannot run twice')
    row = {'device': device, 'bundle': bundle, 'state': 'starting'}
    write_json(receipt, row)
    try:
        code, output, operation = runner(['xcrun', 'simctl', 'get_app_container', device, bundle, 'data'],
                                         20, output_limit=64 * 1024, tail_limit=8192, echo=False)
        unknown = native_operation_unconfirmed(code, operation)
        if unknown:
            # Latch before any receipt write can fail. File I/O cannot turn an
            # uncertain device command into an ordinary completed failure.
            mark_unconfirmed(dict(operation, state='store_runner_lookup_uncertain', exit=126))
        row.update(exit=code, operation=operation, output=output, state='finished')
        write_json(receipt, row)
        if unknown:
            raise ValueError('Store runner container lookup completion is uncertain')
        if code != 0: raise ValueError('Store runner container lookup failed')
        return output.strip()
    except BaseException as error:
        if row['state'] == 'starting':
            mark_unconfirmed({'state': 'store_runner_lookup_interrupted', 'exit': 126, 'cleanup_confirmed': False})
        row.update(error=str(error)[:1600], state='failed')
        write_json(receipt, row)
        raise


def capture_original(out, device, row, runner=execute):
    if blocked(): raise ValueError('Unresolved operation forbids Store capture')
    original = out / ORIGINAL
    if original.exists() or original.is_symlink(): raise ValueError('Original capture already exists; no retry')
    # This attempt marker is durable before the sole native screenshot call.
    attempt = out / 'store-capture-attempt.json'
    with attempt.open('x') as stream: json.dump({'device': device, 'request': row['id']}, stream)
    try:
        code, output, operation = runner(['xcrun', 'simctl', 'io', device, 'screenshot', '--type=jpeg', str(original)],
                                         20, output_limit=64 * 1024, tail_limit=8192, echo=False)
    except BaseException:
        mark_unconfirmed({'state': 'store_screenshot_interrupted', 'exit': 126, 'cleanup_confirmed': False})
        raise
    row.update(screenshot_exit=code, screenshot_operation=operation, screenshot_log=output,
               original_file=ORIGINAL)
    if code in (124, 125, 126) or type(code) is not int or code < 0 or operation.get('cleanup_confirmed') is not True or operation.get('state') != 'completed':
        mark_unconfirmed(dict(operation, state='store_screenshot_operation_uncertain', exit=126))
        raise ValueError('Screenshot completion is uncertain; original file is preserved')
    if code != 0: raise ValueError('Screenshot command failed; original file is preserved')
    data = bounded_file(original, MAX_SOURCE_BYTES)
    dimensions = jpeg_dimensions(data)
    if dimensions != [3840, 2160]: raise ValueError('Original Store screenshot must be 3840x2160')
    row.update(success=True, pixels_retained=True, file=ORIGINAL, bytes=len(data),
               sha256=hashlib.sha256(data).hexdigest(), dimensions=dimensions,
               format='JPEG', alpha=False, native_original_unchanged=True)


def main():
    if len(sys.argv) != 4: raise ValueError('Expected exact device, log and scope')
    device, log, scope = sys.argv[1:]
    if scope != 'visionos_store' or os.environ.get('EVIDENCE_SCOPE') != scope:
        raise ValueError('Only the fixed Store screenshot scope is allowed')
    case = select_case(scope); exact_uuid(device)
    log = Path(log); out = Path('build/vision-runtime'); out.mkdir(parents=True, exist_ok=True)
    if out.is_symlink() or out.resolve() != out.absolute(): raise ValueError('Aliased runtime directory')
    runner_path = Path('build/VisionTests/Build/Products/Debug-xrsimulator/QRCatcherVisionUITests-Runner.app/Info.plist')
    runner_id = plistlib.loads(runner_path.read_bytes())['CFBundleIdentifier']
    binding = RunnerBinding(device, runner_id, os.environ['GITHUB_SHA'], case,
                            lookup=lambda bundle: lookup_runner(out, device, bundle))
    seen = set(); bindings = []; rows = []; failure = False
    deadline = time.monotonic() + 470
    while time.monotonic() < deadline:
        if blocked(): raise ValueError('Unresolved command prevents another native Store action')
        text = log.read_text(errors='replace') if log.exists() else ''
        if len(text.encode()) > 16 * 1024 * 1024: raise ValueError('UI log exceeded bounded input')
        for event, identifier in re.findall(r'QRCATCHER_VISION_(RUNNER_READY|CAPTURE_REQUEST):([A-F0-9-]{36})', text):
            if (event, identifier) in seen: continue
            if len(seen) >= 2: raise ValueError('Only one runner and one capture request are allowed')
            exact_uuid(identifier); seen.add((event, identifier))
            if event == 'RUNNER_READY':
                try:
                    if bindings: raise ValueError('Second runner lease is forbidden')
                    row = binding.prime(identifier)
                except Exception as error:
                    row = {**binding.case_identity, 'lease': identifier, 'success': False, 'error': str(error)[:1600]}
                    failure = True
                bindings.append(row); write_json(out / 'runner-bindings.json', bindings)
                print('VISION_RUNNER_BINDING ' + json.dumps(row), flush=True)
                continue
            row = {**binding.case_identity, 'id': identifier, 'source': 'public simctl screenshot at held XCTest checkpoint',
                   'checkpoint': NAME, 'success': False}
            ack = None
            try:
                descriptor, ack = binding.request(identifier, {NAME})
                for key in ['lease', 'source_commit', 'device', 'runner', 'pid']: row[key] = descriptor[key]
                capture_original(out, device, row)
            except Exception as error:
                row['error'] = str(error)[:1600]; failure = True
            finally:
                # File-only acknowledgement and evidence remain allowed after an
                # uncertain native command. Neither raw pixels nor logs are erased.
                if ack:
                    try: binding.acknowledge(identifier, {NAME}, row)
                    except Exception as error:
                        row.update(success=False, acknowledgement_error=str(error)[:1600]); failure = True
                rows.append(row); write_json(out / 'checkpoint-captures.json', rows)
                print(json.dumps(row), flush=True)
        if (out / 'ui-completed.marker').exists(): break
        time.sleep(.25)
    if failure or len(bindings) != 1 or len(rows) != 1 or not rows[0].get('success'):
        raise SystemExit('Store capture incomplete; original evidence preserved; no retry')


if __name__ == '__main__': main()
