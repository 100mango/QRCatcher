#!/usr/bin/env python3
"""Exact oldest-runtime selection and immutable simulator app provenance checks.

Pure validation functions are tested on Linux; no runtime success is implied.
This module does not install a runtime or authenticate to any service.
"""
import hashlib
import json
from pathlib import Path
import plistlib
import re
import stat

from build_release import ALLOWED
from bundle_archive import checked_name, digest

RUNTIME_ID = 'com.apple.CoreSimulator.SimRuntime.iOS-15-5'
RUNTIME_BUILD = '19F70'
DEVICES = {'iPhone SE (1st generation)', 'iPad mini 4'}


def select_runtime(data, device_name):
    if device_name not in DEVICES:
        raise ValueError('Unexpected device row; no silent size substitution')
    rows = [r for r in data.get('runtimes', []) if r.get('identifier') == RUNTIME_ID]
    if len(rows) != 1:
        raise ValueError('Exact iOS15.5 runtime is missing or duplicated')
    runtime = rows[0]
    if runtime.get('version') != '15.5' or runtime.get('buildversion') != RUNTIME_BUILD or runtime.get('isAvailable') is not True:
        raise ValueError('Runtime version/build/availability mismatch')
    matches = [d for d in runtime.get('supportedDeviceTypes', []) if d.get('name') == device_name]
    if len(matches) != 1 or not re.fullmatch(r'com\.apple\.CoreSimulator\.SimDeviceType\.[A-Za-z0-9-]+', matches[0].get('identifier', '')):
        raise ValueError('Requested smallest-device type is unavailable')
    return runtime['identifier'], matches[0]['identifier']


def validate_provenance(manifest, source_rows):
    rows = manifest.get('provenance')
    if not isinstance(rows, list) or len(rows) != len(ALLOWED):
        raise ValueError('Complete three-app provenance is required')
    expected = {r['name']: r for r in source_rows}
    if len(expected) != len(ALLOWED) or set(expected) != set(ALLOWED):
        raise ValueError('Source identity inventory differs')
    seen = set()
    for row in rows:
        name = row.get('name')
        if name in seen or name not in expected:
            raise ValueError('Unexpected or duplicate provenance identity')
        seen.add(name)
        for key in ('repository', 'project', 'scheme', 'bundle', 'commit', 'tree'):
            if row.get(key) != expected[name][key]:
                raise ValueError('Transferred build differs from pinned source: ' + key)
        required = {'configuration': 'Release', 'arch': 'arm64', 'sdk': '27.0', 'minimum': '15.0', 'xcode': '27.0 (27A266a)'}
        if any(row.get(key) != value for key, value in required.items()):
            raise ValueError('Transferred build differs from exact SDK27 Release gate')
        if not isinstance(row.get('version'), str) or not row['version'] or not isinstance(row.get('build'), str) or not row['build']:
            raise ValueError('App release version and build must be recorded')
    roots = {checked_name(name).parts[0] for name in manifest['files']}
    if roots != {name + '.app' for name in ALLOWED}:
        raise ValueError('Transferred app bundle inventory differs')
    return {row['name']: row for row in rows}


def verify_installed_app(app_root, app_name, manifest, provenance):
    """Require the simulator-installed product to have identical app member bytes.

    App data lives in a separate simulator data container and is deliberately not
    read here. A simulator rewriting the app product is a failed gate, not an
    excuse to weaken the source/binary equivalence claim.
    """
    if app_name not in ALLOWED or app_root.is_symlink() or not app_root.is_dir():
        raise ValueError('Unexpected installed app')
    prefix = app_name + '.app/'
    records = {name[len(prefix):]: value for name, value in manifest['files'].items() if name.startswith(prefix)}
    if not records:
        raise ValueError('No producer records for installed app')
    files = {}
    for path in app_root.rglob('*'):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ValueError('Installed product has non-regular members')
        if stat.S_ISREG(mode):
            files[path.relative_to(app_root).as_posix()] = path
    if set(files) != set(records):
        raise ValueError('Installed product member inventory differs')
    for name, record in records.items():
        path = files[name]
        if path.stat().st_size != record['size'] or digest(path) != record['sha256'] or bool(path.stat().st_mode & 0o111) != record['executable']:
            raise ValueError('Installed product bytes or executable mode differ')
    info = plistlib.loads(files['Info.plist'].read_bytes())
    expected = {'CFBundleIdentifier': ALLOWED[app_name][3], 'MinimumOSVersion': '15.0', 'DTXcodeBuild': '27A266a', 'DTSDKName': 'iphonesimulator27.0', 'CFBundleShortVersionString': provenance['version'], 'CFBundleVersion': provenance['build']}
    if any(info.get(key) != value for key, value in expected.items()):
        raise ValueError('Installed product metadata differs from producer')
    return {'app': app_name, 'verified_files': len(records), 'bundle': info['CFBundleIdentifier'], 'version': info['CFBundleShortVersionString'], 'build': info['CFBundleVersion']}
