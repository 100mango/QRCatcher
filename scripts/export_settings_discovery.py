"""Retain one whole Settings frame and bounded diagnostic metadata, never a pass."""
import hashlib
import json
import os
from pathlib import Path
import stat
import time
from owned_process_barrier import blocked
from watch_process import execute

DIAGNOSTIC_CAP = 300_000
IMAGE_CAP = 150_000
FILES = {'report.json': 48*1024, 'phases.json': 4*1024,
         'system-app-metadata.json': 16*1024, 'ui-tail.log': 24*1024,
         'listapps-help.txt': 8*1024}


def attachment_records(value):
    if isinstance(value, dict):
        if 'exportedFileName' in value:
            yield value
        for child in value.values():
            yield from attachment_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from attachment_records(child)


def read_regular(path, root, limit):
    if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
        raise ValueError('Redirected Settings evidence')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError('Oversized Settings evidence')
    data = path.read_bytes()
    if len(data) != info.st_size:
        raise ValueError('Settings evidence changed during read')
    return data


def export_settings(scope, out, available, export_started, clock=time.monotonic, runner=execute):
    if scope not in {'watchos', 'tvos'}:
        return None
    platform, label = ('watch', 'Watch') if scope == 'watchos' else ('tv', 'TV')
    root = Path.cwd().resolve()
    build = root / 'build'
    source = build / ('settings-discovery-' + platform)
    fence = build / ('settings-discovery-' + platform + '-fence.json')
    latch = build / 'settings-discovery-inflight.json'
    if not any(path.exists() or path.is_symlink() for path in [source, fence, latch]):
        return {'status': 'not_attempted', 'system_propagation_qualified': False}
    summary = {'status': 'metadata_only', 'system_propagation_qualified': False,
               'setting_change_attempted': False, 'files': [], 'operations': []}
    limit = min(DIAGNOSTIC_CAP, max(0, available))
    used = 0

    def retain(path, cap, name):
        nonlocal used
        data = read_regular(path, root, cap)
        if used + len(data) > limit:
            raise ValueError('Settings evidence cannot fit without displacing ordinary proof')
        target = out / ('settings-' + platform + '-' + name)
        if target.exists() or target.is_symlink():
            raise ValueError('Settings output already exists; no overwrite/retry')
        target.write_bytes(data)
        used += len(data)
        summary['files'].append({'name': target.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})

    def run(command, cap):
        remaining = min(45 - (clock() - started), 180 - (clock() - export_started) - 5)
        if blocked() or remaining <= 0:
            raise ValueError('No safe remaining export budget or owned cleanup unresolved')
        code, text, operation = runner(command, min(cap, remaining), output_limit=8192, tail_limit=8192, echo=False)
        summary['operations'].append(operation)
        if code != 0 or operation.get('cleanup_confirmed') is not True:
            raise ValueError('Settings offline evidence command did not complete')
        return text

    started = clock()
    try:
        for name, cap in FILES.items():
            path = source / name
            if path.exists() or path.is_symlink():
                retain(path, cap, name)
        for path, cap in [(fence, 24*1024), (build / ('settings-discovery-' + platform + '-progress.json'), 12*1024), (latch, 2048)]:
            if path.exists() or path.is_symlink():
                retain(path, cap, path.name)
        if blocked():
            summary['status'] = 'metadata_only_cleanup_unconfirmed'
            return summary
        report_path = source / 'report.json'
        if not report_path.exists():
            summary['status'] = 'metadata_only_no_ui_report'
            return summary
        report = json.loads(read_regular(report_path, root, 48*1024))
        ui = report.get('settings_ui')
        if not isinstance(ui, dict) or ui.get('screenshot_attached') is not True:
            summary['status'] = 'metadata_only_no_verified_screenshot_receipt'
            return summary
        if ui.get('setting_change_attempted') is not False or ui.get('system_propagation_qualified') is not False:
            raise ValueError('Unexpected Settings qualification or mutation claim')
        result = root / (label + 'SettingsDiscovery.xcresult')
        if not (result / 'Info.plist').is_file() or result.resolve(strict=True) != result:
            raise ValueError('Settings result is absent or redirected')
        folder = build / ('settings-discovery-export-' + platform)
        if folder.exists() or folder.is_symlink():
            raise ValueError('Settings attachments already exported; retries forbidden')
        run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', str(result), '--output-path', str(folder)], 20)
        manifest = json.loads(read_regular(folder / 'manifest.json', root, 64*1024))
        records = list(attachment_records(manifest))
        if len(records) > 32:
            raise ValueError('Unbounded Settings attachment inventory')
        selected = [entry for entry in records if platform + '-settings-discovery' in ' '.join(v for v in entry.values() if isinstance(v, str))]
        if len(selected) != 1:
            raise ValueError('Missing or ambiguous latest-safe Settings frame')
        path = folder / selected[0]['exportedFileName']
        if not path.resolve(strict=True).is_relative_to(folder.resolve(strict=True)):
            raise ValueError('Settings image escaped attachment folder')
        data = read_regular(path, root, 16*1024*1024)
        if not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8')):
            raise ValueError('Unknown Settings image encoding')
        converted = folder / 'latest-safe-whole-frame.jpg'
        run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '55', '-Z', '1440', str(path), '--out', str(converted)], 10)
        converted_data = read_regular(converted, root, IMAGE_CAP)
        if not converted_data.startswith(b'\xff\xd8'):
            raise ValueError('Invalid bounded Settings image')
        retain(converted, IMAGE_CAP, 'latest-safe-whole-frame.jpg')
        summary.update(status='read_only_evidence_retained_unqualified', screenshot_pane=ui.get('screenshot_pane'),
                       navigation_complete=ui.get('navigation_complete'), original_attachment_bytes=len(data),
                       image_is_whole_frame=True)
    except (OSError, ValueError, KeyError, TypeError) as error:
        summary.update(status='read_only_evidence_incomplete_unqualified', error=str(error)[:512])
    finally:
        summary['bytes'] = used
        summary['elapsed_seconds'] = round(clock() - started, 3)
    return summary
