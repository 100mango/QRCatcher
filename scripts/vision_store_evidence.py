"""Host-only preservation and validation for one real 4K Store screenshot.

An authentic checkpoint can be retained even if its enclosing UI/run later fails.
A failed workflow is never rewritten as a passing UI test or successful upload.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from atomic_json import write_json
from export_vision_case_evidence import bounded_file, bounded_json
from vision_case_contract import ALL_CASES, case_identity, require_identity, select_case
from capture_vision_store_checkpoint import jpeg_dimensions, MAX_SOURCE_BYTES, ORIGINAL, NAME

ARTIFACT_LIMIT = 6 * 1024 * 1024
RETAINED = NAME + '.jpg'


def inspect(folder, required=True, limit=ARTIFACT_LIMIT):
    folder = Path(folder)
    if not folder.exists():
        if required: raise ValueError('Missing Store evidence folder')
        return {'bytes': 0, 'files': []}
    if folder.is_symlink() or not folder.is_dir() or folder.resolve() != folder.absolute():
        raise ValueError('Store evidence directory is aliased')
    rows = []; total = 0
    for path in sorted(folder.iterdir()):
        if path.suffix not in {'.jpg', '.json', '.log'}: raise ValueError('Unexpected Store evidence type')
        cap = MAX_SOURCE_BYTES if path.name == ORIGINAL else 450_000 if path.suffix == '.jpg' else 128 * 1024
        raw = bounded_file(path, cap)
        if path.suffix == '.json': json.loads(raw)
        total += len(raw)
        if total > limit or len(rows) >= 24: raise ValueError('Store artifact budget exceeded')
        rows.append({'path': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    if required and not rows: raise ValueError('Empty Store evidence')
    return {'bytes': total, 'files': rows}


def validate_capture(runtime, expected):
    bindings = bounded_json(runtime / 'runner-bindings.json')
    rows = bounded_json(runtime / 'checkpoint-captures.json')
    if not isinstance(bindings, list) or len(bindings) != 1 or not isinstance(rows, list) or len(rows) != 1:
        raise ValueError('Exactly one runner and one checkpoint are required')
    binding, row = bindings[0], rows[0]
    require_identity(binding, expected); require_identity(row, expected)
    if binding.get('success') is not True or binding.get('exports') is not False:
        raise ValueError('Store runner binding was unsuccessful or export-enabled')
    for key in ['lease', 'runner', 'pid']:
        if row.get(key) != binding.get(key): raise ValueError('Store frame differs from current runner')
    if row.get('runner') != '100mango.QRCatcherVisionUITests.xctrunner' or type(row.get('pid')) is not int or row['pid'] <= 0:
        raise ValueError('Store frame runner identity invalid')
    operation = row.get('screenshot_operation', {})
    if row.get('checkpoint') != NAME or row.get('file') != ORIGINAL or row.get('success') is not True or row.get('pixels_retained') is not True or row.get('screenshot_exit') != 0:
        raise ValueError('Store original checkpoint did not succeed')
    if operation.get('state') != 'completed' or operation.get('cleanup_confirmed') is not True or operation.get('exit') != 0:
        raise ValueError('Store screenshot command was not fully completed')
    raw = bounded_file(runtime / ORIGINAL, MAX_SOURCE_BYTES)
    if len(raw) != row.get('bytes') or hashlib.sha256(raw).hexdigest() != row.get('sha256') or jpeg_dimensions(raw) != [3840, 2160]:
        raise ValueError('Store original bytes/hash/dimensions do not match')
    return row


def validate_ui(runtime, expected):
    value = bounded_json(runtime / 'ui-cases.json')
    require_identity(value, expected)
    rows = value.get('cases')
    if not isinstance(rows, list) or len(rows) != 1: raise ValueError('Exactly one Store UI case was required')
    row = rows[0]; require_identity(row, expected)
    operation = row.get('operation', {})
    if row.get('state') != 'finished' or row.get('exit') != 0 or operation.get('state') != 'completed' or operation.get('cleanup_confirmed') is not True or operation.get('exit') != 0:
        raise ValueError('Store UI XCTest command did not finish successfully')
    if value.get('cleanup_unconfirmed') or value.get('capture_cleanup_confirmed') is not True or value.get('capture_process_exit') != 0:
        raise ValueError('Store capture supervision did not finish successfully')
    return value


def collect(root, scope, allow_encode=True, failure_reason=None):
    root = Path(root).resolve(strict=True)
    if scope != 'visionos_store' or os.environ.get('EVIDENCE_SCOPE') != scope:
        raise ValueError('Wrong Store collection scope')
    case = select_case(scope); runtime = root / 'build/vision-runtime'; out = root / 'build/vision-store-evidence'
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()): raise ValueError('Store evidence collection is single-shot')
    summary = {'scope': scope, 'source_commit': os.environ['GITHUB_SHA'], 'source_product_commit': '6675f0051fbb597ed7212819cd34fb0b1e42c7b5',
               'run_id': os.environ['GITHUB_RUN_ID'], 'qualified': False, 'capture_qualified': False,
               'ui_command_qualified': False, 'store_upload_qualified': False, 'pixel_review_pending': True,
               'native_original_preserved': False, 'locale': 'en-US', 'format': 'JPEG', 'dimensions': [3840, 2160],
               'apple_spec': 'https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications',
               'claim_scope': 'One authentic UI screenshot only; no repeated full functional chain, signed build or Store upload.',
               'errors': [], 'files': []}
    if failure_reason: summary['errors'].append(failure_reason)
    def retain(path, cap, tail=False):
        if not path.exists(): return
        if tail:
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1 or path.resolve() != path.absolute():
                raise ValueError('Aliased log')
            with path.open('rb') as stream:
                stream.seek(0, 2); total = stream.tell(); stream.seek(max(0, total - cap)); raw = stream.read(cap)
            summary.setdefault('log_retention', {})[path.name] = {'source_bytes': total, 'retained_bytes': len(raw), 'tail_only': total > cap}
        else: raw = bounded_file(path, cap)
        if not raw: return
        (out / path.name).write_bytes(raw)
        summary['files'].append({'name': path.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    # Original first, before optional decoding or later UI qualification. Keep it
    # byte-for-byte on success and failure; never transform this source in place.
    try:
        retain(runtime / ORIGINAL, MAX_SOURCE_BYTES)
        summary['native_original_preserved'] = (out / ORIGINAL).is_file()
    except (OSError, ValueError) as error: summary['errors'].append('Original: ' + str(error))
    for name in ['runtime.json', 'ui-cases.json', 'runner-bindings.json', 'checkpoint-captures.json',
                 'store-capture-attempt.json', 'store-runner-lookup.json', 'fenced-install.json', 'fenced-shutdown.json']:
        try: retain(runtime / name, 32 * 1024)
        except (OSError, ValueError) as error: summary['errors'].append(name + ': ' + str(error))
    for path, cap in [(root / 'vision-test-build.log', 64 * 1024), (root / 'vision-ui-test.log', 64 * 1024),
                      (runtime / 'checkpoint-capture.log', 16 * 1024), (runtime / 'store-ui-tail.log', 16 * 1024),
                      (runtime / 'boot.log', 8 * 1024), (runtime / 'bootstatus.log', 8 * 1024)]:
        try: retain(path, cap, tail=True)
        except (OSError, ValueError) as error: summary['errors'].append(path.name + ': ' + str(error))
    try:
        expected = case_identity(case, os.environ['GITHUB_SHA'], os.environ['VISION_SIMULATOR_ID']); summary.update(expected)
        if any((root / other.result).exists() for other in ALL_CASES if other != case):
            raise ValueError('Unexpected other Vision test result')
        if (root / 'VisionTestResults.xcresult').exists(): raise ValueError('Unrequested hosted suite result')
        row = validate_capture(runtime, expected); summary['capture_qualified'] = True
        # Retention can still preserve a genuine frame if a later UI/test gate is
        # red; that must remain separately visible in the final report.
        if allow_encode:
            from vision_store_image import retain_store_image
            encoding = retain_store_image(out / ORIGINAL, out / RETAINED)
            raw = bounded_file(out / RETAINED, 450_000)
            if jpeg_dimensions(raw) != [3840, 2160]: raise ValueError('Retained Store dimensions changed')
            summary['encoding'] = encoding
            summary['files'].append({'name': RETAINED, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        else: raise ValueError('Encoding skipped after failed/uncertain work; original retained')
        validate_ui(runtime, expected); summary['ui_command_qualified'] = True
        summary['qualification_basis'] = 'Exact case command and raw checkpoint receipts; no xcresult summary or full-suite pass inferred.'
    except (OSError, ValueError, KeyError) as error: summary['errors'].append(str(error))
    failure_receipt = out / 'vision-store-image-failure.json'
    if failure_receipt.exists():
        raw = bounded_file(failure_receipt, 64 * 1024)
        summary['files'].append({'name': failure_receipt.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    summary['qualified'] = not summary['errors'] and summary['capture_qualified'] and summary['ui_command_qualified']
    write_json(out / 'manifest.json', summary, limit=64 * 1024)
    inspect(out)
    return summary


if __name__ == '__main__':
    if len(sys.argv) != 2: raise ValueError('Expected exact Store scope')
    result = collect(Path.cwd(), sys.argv[1])
    print(json.dumps({'qualified': result['qualified'], 'errors': result['errors']}), flush=True)
    if not result['qualified']: raise SystemExit('Store capture evidence incomplete; originals retained')
