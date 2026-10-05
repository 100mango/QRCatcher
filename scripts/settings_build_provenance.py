#!/usr/bin/env python3
"""Same-job fresh-build provenance, not embedded binary/source attestation."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import sys
from atomic_json import write_json
from watch_process import execute

CONFIG = {'watch': ('Watch', 'watchos'), 'tv': ('TV', 'tvos')}
CAP = 16 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def regular(root, path, limit):
    require(path.resolve(strict=True).is_relative_to(root), 'Build input escaped checkout')
    require(not path.is_symlink(), 'Aliased provenance file')
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= limit, 'Unbounded provenance file')
    data = path.read_bytes()
    require(len(data) == info.st_size, 'Provenance file changed while reading')
    return data


def identity(platform, root):
    require(platform in CONFIG, 'Unsupported discovery build platform')
    label, scope = CONFIG[platform]
    require(os.environ.get('EVIDENCE_SCOPE') == scope, 'Discovery is only for primary Watch/TV rows')
    require(os.environ.get('GITHUB_REPOSITORY') == '100mango/QRCatcher', 'Wrong repository')
    require(os.environ.get('GITHUB_WORKSPACE') == str(root), 'Wrong canonical workspace')
    source = os.environ.get('GITHUB_SHA', '')
    require(re.fullmatch('[0-9a-f]{40}', source) and os.environ.get('GITHUB_WORKFLOW_SHA') == source, 'Wrong source identity')
    result = {'platform': platform, 'source': source, 'scope': scope}
    for name in ['GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB', 'RUNNER_NAME']:
        value = os.environ.get(name, '')
        require(isinstance(value, str) and 0 < len(value.encode()) <= 256, 'Missing same-job identity: ' + name)
        result[name] = value
    return result


def source_files(platform, root):
    label = CONFIG[platform][0]
    names = ['QRCatcher.xcodeproj/project.pbxproj',
             'QRCatcher.xcodeproj/xcshareddata/xcschemes/QRCatcher' + label + '.xcscheme',
             'QRCatcher' + label + 'UITests/QRCatcher' + label + 'UITests.swift']
    return {name: hashlib.sha256(regular(root, root / name, 2 * 1024 * 1024)).hexdigest() for name in names}


def source_clean(source):
    for command in [['git', 'rev-parse', 'HEAD'], ['git', 'diff', '--quiet', 'HEAD', '--']]:
        code, output, op = execute(command, 5, output_limit=1024, tail_limit=1024, echo=False)
        require(code == 0 and op.get('cleanup_confirmed') is True, 'Source query did not complete cleanly')
        if command[1] == 'rev-parse':
            require(output.strip() == source, 'Checkout source differs')


def products(platform, root):
    label = CONFIG[platform][0]
    base = root / 'build' / (label + 'Tests') / 'Build' / 'Products'
    require(base.is_dir() and base.resolve(strict=True) == base, 'Aliased or missing fresh products')
    bundles = list(base.rglob('QRCatcher' + label + 'UITests.xctest'))
    require(len(bundles) == 1 and bundles[0].is_dir() and bundles[0].resolve(strict=True) == bundles[0], 'Missing or ambiguous native UI test bundle')
    bundle = bundles[0]
    info_path = bundle / 'Info.plist'
    info = plistlib.loads(regular(root, info_path, 64 * 1024))
    executable = info.get('CFBundleExecutable')
    require(executable == 'QRCatcher' + label + 'UITests', 'Unexpected native UI executable')
    runs = list(base.glob('*.xctestrun'))
    require(len(runs) == 1, 'Missing or ambiguous fresh test run descriptor')
    paths = [info_path, bundle / executable, runs[0]]
    result = []
    for path in paths:
        data = regular(root, path, 64 * 1024 * 1024)
        result.append({'path': str(path.relative_to(root)), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    require(result[1]['bytes'] > 0, 'Empty compiled test executable')
    return result


def state_path(platform, root):
    return root / 'build' / ('settings-build-' + platform + '.json')


def read_state(platform, root):
    return json.loads(regular(root, state_path(platform, root), CAP))


def begin(platform):
    root = Path.cwd().resolve()
    expected = identity(platform, root)
    source_clean(expected['source'])
    derived = root / 'build' / (CONFIG[platform][0] + 'Tests')
    require(not derived.exists() and not derived.is_symlink(), 'Derived data is not fresh; no removal or reuse allowed')
    path = state_path(platform, root)
    require(not path.exists() and not path.is_symlink(), 'Build provenance already exists')
    require(path.parent.is_dir() and path.parent.resolve(strict=True) == path.parent, 'Missing owned build directory')
    write_json(path, dict(expected, state='before_fresh_build', source_files=source_files(platform, root),
                         derived_data_was_absent=True, binary_source_binding_verified=False), limit=CAP)


def finish(platform):
    root = Path.cwd().resolve()
    expected = identity(platform, root)
    value = read_state(platform, root)
    require(all(value.get(key) == item for key, item in expected.items()) and value.get('state') == 'before_fresh_build', 'Wrong or repeated build provenance')
    source_clean(expected['source'])
    require(value.get('source_files') == source_files(platform, root), 'Discovery source changed during build')
    value.update(state='fresh_build_completed', products=products(platform, root), same_job_fresh_build_verified=True)
    write_json(state_path(platform, root), value, limit=CAP)


def verify(platform, root):
    """No process or simulator calls; the discovery owner already checks git."""
    value = read_state(platform, root)
    expected = identity(platform, root)
    require(all(value.get(key) == item for key, item in expected.items()), 'Build provenance belongs to another job/source')
    require(value.get('state') == 'fresh_build_completed' and value.get('derived_data_was_absent') is True and
            value.get('same_job_fresh_build_verified') is True and value.get('binary_source_binding_verified') is False,
            'Fresh build was not established')
    require(value.get('source_files') == source_files(platform, root), 'Discovery source changed after build')
    require(value.get('products') == products(platform, root), 'Compiled UI test products changed after build')
    return value


def observed_unsupported(platform, device):
    """Admit only this device's completed read-only unsupported result."""
    relative = {'watch': 'build/watch-runtime/system-content-size.json',
                'tv': 'build/native-release-evidence/tv-system-content-size.json'}
    try:
        root = Path.cwd().resolve()
        value = json.loads(regular(root, root / relative[platform], 48 * 1024))
        rows = value.get('operations', [])
        if not (value.get('device') == device and value.get('status') == 'original_value_not_recognized' and
                value.get('original_raw') == 'unsupported' and value.get('requested_largest') is None and
                value.get('observed_original') is None and value.get('ui_executed') is False and
                not value.get('cleanup_unconfirmed') and isinstance(rows, list) and
                [row.get('label') for row in rows] == ['help', 'device_inventory', 'read_original']):
            return False
        last = rows[-1]
        operation = last.get('operation', {})
        return (last.get('output', '').strip() == 'unsupported' and
                operation.get('command') == ['xcrun', 'simctl', 'ui', device, 'content_size'] and
                type(operation.get('exit')) is int and operation['exit'] == 0 and
                operation.get('state') == 'completed' and operation.get('cleanup_confirmed') is True)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'unsupported':
        raise SystemExit(0 if observed_unsupported(sys.argv[2], sys.argv[3]) else 2)
    require(len(sys.argv) == 3 and sys.argv[1] in ['begin', 'finish'], 'Expected begin|finish watch|tv')
    {'begin': begin, 'finish': finish}[sys.argv[1]](sys.argv[2])
