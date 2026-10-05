#!/usr/bin/env python3
"""One read-only Settings UI discovery on an already-owned simulator.

This diagnostic never changes text size and never satisfies the OS propagation
release gate. Its driver preserves the original failed system-size outcome.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import time
import uuid
from atomic_json import write_json
from owned_process_barrier import blocked, mark_unconfirmed
from watch_process import execute
from settings_build_provenance import verify as verify_build

CONFIG = {
    'watch': ('watchos', 'WATCH_SIMULATOR_ID', 'watchOS', 'Watch', 'QRCatcherWatchSettingsDiscovery'),
    'tv': ('tvos', 'TV_SIMULATOR_ID', 'tvOS', 'TV', 'QRCatcherTVSettingsDiscovery'),
}
AGGREGATE_SECONDS = 180
REPORT_LIMIT = 48 * 1024
UI_RECEIPT_LIMIT = 24 * 1024
CATALOG_LIMIT = 512 * 1024
UI_OUTPUT_LIMIT = 512 * 1024
TOKEN_PREFIX = 'QRCATCHER_SETTINGS_DISCOVERY '


class DiscoveryStopped(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DiscoveryStopped(message)


def validate_identity(platform, device, environment, root):
    require(platform in CONFIG, 'Unknown platform')
    scope, variable, runtime, label, case = CONFIG[platform]
    device = str(uuid.UUID(device)).upper()
    require(environment.get('GITHUB_REPOSITORY') == '100mango/QRCatcher', 'Wrong repository')
    source = environment.get('GITHUB_SHA', '')
    require(re.fullmatch('[0-9a-f]{40}', source), 'Missing exact source identity')
    require(environment.get('GITHUB_WORKFLOW_SHA') == source, 'Workflow source differs')
    require(environment.get('EVIDENCE_SCOPE') == scope, 'Discovery only on Watch 46 mm or TV scope')
    require(environment.get(variable, '').upper() == device, 'Device is not the already-selected scope device')
    workspace = environment.get('GITHUB_WORKSPACE')
    require(isinstance(workspace, str) and bool(workspace) and Path(workspace).is_absolute() and Path(workspace).resolve() == root, 'Missing or wrong canonical workspace')
    require(not any('LAYOUT_STRESS' in key or 'LAYOUT_PROBE' in key for key in environment), 'Trait overrides/probes are forbidden')
    return {'platform': platform, 'scope': scope, 'source': source, 'device': device,
            'runtime_prefix': 'com.apple.CoreSimulator.SimRuntime.' + runtime + '-',
            'test_label': label, 'test_class': case, 'nonce': str(uuid.uuid4()),
            'setting_change_attempted': False, 'system_propagation_qualified': False,
            'binary_source_binding_verified': False, 'discovery_protocol': 'bounded-settings-navigation-v1'}


def select_device(raw, identity):
    require(isinstance(raw, dict) and isinstance(raw.get('devices'), dict), 'Unknown device inventory')
    matches = [(runtime, row) for runtime, rows in raw['devices'].items() if isinstance(rows, list)
               for row in rows if isinstance(row, dict) and isinstance(row.get('udid'), str) and row['udid'].upper() == identity['device']]
    require(len(matches) == 1, 'Device identity is absent or ambiguous')
    runtime, row = matches[0]
    require(runtime.startswith(identity['runtime_prefix']), 'Device runtime is wrong')
    require(row.get('state') == 'Booted' and row.get('isAvailable') is True, 'Owned device is not booted and available')
    return runtime


def select_settings(catalog):
    """Select only explicit installed System/Settings metadata; never guess ID."""
    require(isinstance(catalog, dict), 'Installed app catalog is not a dictionary')
    candidates = []
    observed = []
    for key, value in catalog.items():
        if not isinstance(value, dict):
            continue
        record = {field: value.get(field) for field in
                  ['CFBundleIdentifier', 'CFBundleDisplayName', 'CFBundleName', 'ApplicationType']}
        if value.get('ApplicationType') == 'System':
            observed.append(record)
        names = [value.get('CFBundleDisplayName'), value.get('CFBundleName')]
        if value.get('ApplicationType') != 'System' or 'Settings' not in names:
            continue
        identifier = value.get('CFBundleIdentifier')
        require(isinstance(identifier, str) and key == identifier and
                re.fullmatch(r'com\.apple\.[A-Za-z0-9.-]{1,100}', identifier), 'Settings identity is inconsistent')
        candidates.append(record)
    require(len(observed) <= 128, 'System application catalog exceeds diagnostic limit')
    require(len(candidates) == 1, 'No unique explicitly identified native Settings app; inspect retained catalog')
    return candidates[0], observed


ROUTES = {
    'watch': ['Settings', 'Display & Brightness', 'Text Size'],
    'tv': ['Settings', 'Accessibility', 'Display', 'Text Size'],
}


def valid_rectangle(value):
    if not (isinstance(value, list) and len(value) == 4 and
            all(type(x) in {int, float} for x in value)):
        return False
    try:
        # Finite components can still produce infinite endpoints. JSON integers
        # can also overflow math.isfinite's conversion; both cases fail closed.
        endpoints = [value[0] + value[2], value[1] + value[3]]
        return (all(math.isfinite(x) for x in value + endpoints) and
                value[2] > 0 and value[3] > 0)
    except OverflowError:
        return False


def validate_navigation_row(row, bounds, label=None):
    require(isinstance(row, dict) and row.get('role') in ['button', 'cell'], 'Unknown navigation role')
    require(isinstance(row.get('label'), str) and 0 < len(row['label'].encode()) <= 128 and
            (label is None or row['label'] == label), 'Navigation label differs')
    require(isinstance(row.get('identifier'), str) and len(row['identifier'].encode()) <= 128, 'Unknown navigation identity')
    require(row.get('enabled') is True and row.get('selected') is False and
            row.get('value_empty') is True and row.get('adjustment_descendants') is False,
            'Navigation row is not read-only-safe')
    frame = row.get('frame')
    require(valid_rectangle(frame) and valid_rectangle(bounds), 'Nonfinite or invalid navigation geometry')
    require(frame[0] >= bounds[0] and frame[1] >= bounds[1] and
            frame[0] + frame[2] <= bounds[0] + bounds[2] and
            frame[1] + frame[3] <= bounds[1] + bounds[3], 'Navigation control is not wholly visible')


def validate_navigation_receipt(receipt, platform):
    route = ROUTES[platform]
    steps = receipt.get('navigation_steps')
    focus = receipt.get('focus_steps')
    require(type(receipt.get('navigation_complete')) is bool, 'Unknown navigation completion')
    require(isinstance(steps, list) and len(steps) <= len(route) - 1, 'Unbounded navigation steps')
    require(isinstance(focus, list) and len(focus) <= 8 and (platform == 'tv' or not focus), 'Unbounded/unsupported focus movement')
    for index, step in enumerate(steps):
        require(isinstance(step, dict) and step.get('from') == route[index] and step.get('to') == route[index + 1], 'Undocumented navigation route')
        require(step.get('action') == ('exact_element_tap' if platform == 'watch' else 'focused_remote_select'), 'Unsupported navigation action')
        require(step.get('state') in ['observed', 'activation_attempted', 'activation_returned', 'destination_verified'], 'Unknown navigation state')
        require(index == len(steps) - 1 or step.get('state') == 'destination_verified', 'Navigation continued without destination verification')
        validate_navigation_row(step.get('control'), step.get('pane_frame'), step['to'])
    last_focus_index = -1
    for move in focus:
        require(isinstance(move, dict) and move.get('pane') in route[:-1], 'Unknown focus pane')
        index = route.index(move['pane'])
        require(index >= last_focus_index and index < len(steps) and move.get('toward') == route[index + 1], 'Focus left the documented route')
        last_focus_index = index
        require(move.get('direction') in ['up', 'down'] and move.get('state') == 'movement_attempted', 'Unsupported focus input')
        validate_navigation_row(move.get('from'), move.get('pane_frame'))
    if receipt['navigation_complete']:
        require(len(steps) == len(route) - 1 and all(s['state'] == 'destination_verified' for s in steps), 'Unverified navigation completion')
        require(receipt.get('last_observed_pane') == route[-1], 'Missing terminal pane observation')
    if receipt.get('status') == 'settings_screen_observed':
        require(receipt['navigation_complete'] and receipt.get('screenshot_pane') == route[-1], 'Complete receipt lacks terminal pane capture')
    if receipt.get('screenshot_attached') is True:
        require(receipt.get('screenshot_pane') in route, 'Unknown screenshot pane')


def validate_receipt(receipt, identity, settings):
    require(isinstance(receipt, dict), 'Malformed Settings UI receipt')
    for key in ['source', 'device', 'nonce', 'platform']:
        require(receipt.get(key) == identity[key], 'Settings receipt identity differs: ' + key)
    require(receipt.get('settings_bundle') == settings['CFBundleIdentifier'], 'Settings app identity differs')
    require(receipt.get('setting_change_attempted') is False, 'Discovery attempted a setting change')
    require(receipt.get('system_propagation_qualified') is False, 'Discovery cannot qualify propagation')
    require(receipt.get('original_value_restorable') is False and receipt.get('setting_write_authorized') is False, 'Discovery cannot authorize restoration or setting writes')
    require(receipt.get('binary_source_binding_verified') is False and receipt.get('discovery_protocol') == 'bounded-settings-navigation-v1', 'Unknown provenance/protocol claim')
    require(receipt.get('status') in ['settings_screen_observed', 'observation_stopped'], 'Unknown UI discovery result')
    if receipt.get('status') == 'settings_screen_observed':
        require(isinstance(receipt.get('hierarchy'), str) and 0 < len(receipt['hierarchy'].encode()) <= 4096, 'Observed screen lacks bounded native hierarchy')
        require(isinstance(receipt.get('controls'), list) and 0 < len(receipt['controls']) <= 32, 'Observed screen lacks bounded native controls')
        require(receipt.get('screenshot_attached') is True, 'Observed screen lacks screenshot attachment receipt')
        for item in receipt['controls']:
            require(isinstance(item, dict) and type(item.get('type')) is int and all(isinstance(item.get(key), str) for key in ['identifier', 'label', 'value']), 'Malformed control observation')
    validate_navigation_receipt(receipt, identity['platform'])
    require(len(json.dumps(receipt).encode()) <= UI_RECEIPT_LIMIT, 'Settings receipt exceeds limit')
    return receipt


def discover(platform, device, runner=execute, clock=time.monotonic):
    require(runner is not execute, 'Standalone discovery execution is disabled; the admitted fenced entry is required')
    root = Path.cwd().resolve()
    identity = validate_identity(platform, device, os.environ, root)
    out = root / 'build' / ('settings-discovery-' + platform)
    require(out.parent.is_dir() and not out.parent.is_symlink(), 'Missing real owned build directory')
    require(not out.exists() and not out.is_symlink(), 'Settings discovery already attempted; retries forbidden')
    out.mkdir(mode=0o700)
    started = clock()
    report = dict(identity, status='starting', operations=[], settings_ui=None,
                  original_value_restorable=False, setting_write_authorized=False)
    def save():
        write_json(out / 'report.json', report, limit=REPORT_LIMIT)
    def run(label, command, cap, limit=CATALOG_LIMIT):
        require(not blocked(), 'Owned process cleanup is unconfirmed')
        remaining = AGGREGATE_SECONDS - (clock() - started) - 3
        require(remaining > 0, 'Aggregate discovery deadline reached')
        try:
            code, text, operation = runner(command, min(cap, remaining), output_limit=limit, tail_limit=limit, echo=False)
        except Exception as error:
            operation = {'command': command, 'state': 'execution_unresolved', 'cleanup_confirmed': False, 'error_type': type(error).__name__}
            report['operations'].append({'label': label, 'operation': operation})
            report['cleanup_unconfirmed'] = True
            mark_unconfirmed(operation); save()
            raise DiscoveryStopped('Discovery execution state unresolved') from error
        report['operations'].append({'label': label, 'operation': operation})
        if label == 'settings_ui':
            (out / 'ui-tail.log').write_bytes(text.encode()[-24 * 1024:])
            phases = []
            for line in text.splitlines():
                if line.startswith('QRCATCHER_SETTINGS_DISCOVERY_PHASE '):
                    try:
                        phase = json.loads(line.split(' ', 1)[1])
                        if all(phase.get(key) == identity[key] for key in ['source', 'device', 'nonce']) and phase.get('setting_change_attempted') is False:
                            phases.append(phase)
                    except (ValueError, TypeError): pass
            write_json(out / 'phases.json', phases[-8:], limit=4096)
        save()
        if code == 126 or operation.get('cleanup_confirmed') is not True:
            mark_unconfirmed(operation)
            report['cleanup_unconfirmed'] = True
            raise DiscoveryStopped('Owned discovery command cleanup is unconfirmed')
        require(code == 0, label + ' failed with exit ' + str(code))
        require(len(text.encode()) <= limit, label + ' output exceeds limit')
        return text
    save()
    try:
        require(run('source', ['git', 'rev-parse', 'HEAD'], 5, 1024).strip() == identity['source'], 'Checkout source differs')
        run('source_clean', ['git', 'diff', '--quiet', 'HEAD', '--'], 5, 1024)
        report['fresh_build_provenance'] = verify_build(platform, root)
        help_text = run('listapps_help', ['xcrun', 'simctl', 'help', 'listapps'], 5, 8192)
        (out / 'listapps-help.txt').write_text(help_text)
        require(re.search(r'Usage:\s*simctl listapps\s+<device>(?:\s|$)', help_text), 'Installed listapps syntax unrecognized')
        inventory = json.loads(run('device_inventory', ['xcrun', 'simctl', 'list', 'devices', '-j'], 10))
        report['runtime'] = select_device(inventory, identity)
        raw = run('installed_apps', ['xcrun', 'simctl', 'listapps', identity['device']], 10)
        (out / 'installed-apps.plist').write_text(raw)
        run('parse_installed_apps', ['plutil', '-convert', 'json', '-o', str(out / 'installed-apps.json'), str(out / 'installed-apps.plist')], 5, 8192)
        catalog_path = out / 'installed-apps.json'
        require(catalog_path.is_file() and not catalog_path.is_symlink() and catalog_path.stat().st_size <= CATALOG_LIMIT, 'Invalid converted catalog')
        catalog = json.loads(catalog_path.read_text())
        # Retain bounded System metadata even when no usable Settings identity exists.
        system_metadata = [{key: value.get(key) for key in ['CFBundleIdentifier', 'CFBundleDisplayName', 'CFBundleName', 'ApplicationType']}
                           for value in catalog.values() if isinstance(value, dict) and value.get('ApplicationType') == 'System'] if isinstance(catalog, dict) else []
        write_json(out / 'system-app-metadata.json', system_metadata[:128], limit=16 * 1024)
        settings, observed = select_settings(catalog)
        report['settings_app'] = settings
        report['system_app_count'] = len(observed)
        # A bounded metadata inventory survives unsupported identities; no install,
        # authentication, app seeding, permissions, preferences or private API calls.
        write_json(out / 'settings-identity.json', dict(identity, settings=settings), limit=8192)
        label = identity['test_label']
        for relative in ['QRCatcher.xcodeproj', 'build/' + label + 'Tests']:
            expected = root / relative
            require(expected.is_dir() and not expected.is_symlink() and expected.resolve().is_relative_to(root), 'Missing or redirected owned test products')
        result = root / (label + 'SettingsDiscovery.xcresult')
        require(not result.exists() and not result.is_symlink(), 'Discovery result already exists')
        token = json.dumps({**identity, 'settings_bundle': settings['CFBundleIdentifier']}, separators=(',', ':'))
        command = ['env', 'TEST_RUNNER_QRCATCHER_SETTINGS_DISCOVERY=' + token,
            'xcodebuild', 'test-without-building', '-project', str(root / 'QRCatcher.xcodeproj'),
            '-scheme', 'QRCatcher' + label, '-configuration', 'Debug', '-derivedDataPath', str(root / 'build' / (label + 'Tests')),
            '-destination', 'platform=' + ('watchOS' if platform == 'watch' else 'tvOS') + ' Simulator,id=' + identity['device'],
            '-parallel-testing-enabled', 'NO', '-maximum-concurrent-test-simulator-destinations', '1',
            '-collect-test-diagnostics', 'never', '-test-timeouts-enabled', 'YES',
            '-default-test-execution-time-allowance', '60', '-maximum-test-execution-time-allowance', '60',
            '-only-testing:QRCatcher' + label + 'UITests/' + identity['test_class'] + '/testReadOnlyTextSizeSettingsDiscovery',
            '-resultBundlePath', str(result), 'CODE_SIGNING_ALLOWED=NO']
        output = run('settings_ui', command, 90, UI_OUTPUT_LIMIT)
        (out / 'ui-tail.log').write_bytes(output.encode()[-24 * 1024:])
        receipts = [json.loads(line[len(TOKEN_PREFIX):]) for line in output.splitlines() if line.startswith(TOKEN_PREFIX)]
        require(len(receipts) == 1, 'Exactly one source/device-bound Settings receipt is required')
        report['settings_ui'] = validate_receipt(receipts[0], identity, settings)
        report['status'] = 'read_only_discovery_complete_unqualified'
    except (DiscoveryStopped, OSError, ValueError, KeyError, TypeError) as error:
        report.update(status='read_only_discovery_stopped_unqualified', error=str(error)[:1024])
    finally:
        report['elapsed_seconds'] = round(clock() - started, 3)
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=CONFIG)
    parser.add_argument('device')
    args = parser.parse_args()
    report = discover(args.platform, args.device)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    # Discovery, including success, never clears a missing real-OS acceptance gate.
    return 126 if report.get('cleanup_unconfirmed') else 2


if __name__ == '__main__':
    raise SystemExit(main())
