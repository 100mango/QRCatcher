#!/usr/bin/env python3
"""Local preparation: exact Apple iOS15.5 runtime on a disposable hosted VM.

This file is not an app compatibility result. It uses the same preinstalled
xcodes 2.0.3 route that installed and booted Apple's runtime in run37109442046.
It never installs a helper, accepts an agreement, changes host security policy,
erases an existing simulator or downloads an artifact to permanent storage.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import urllib.error
import urllib.request

from build_release import bounded_build, output
from run_consumer import checked_host
from runtime_gate import RUNTIME_BUILD, RUNTIME_ID, select_runtime

CATALOG = 'https://devimages-cdn.apple.com/downloads/xcode/simulators/index2.dvtdownloadableindex'
SOURCE = 'https://devimages-cdn.apple.com/downloads/xcode/simulators/com.apple.pkg.iPhoneSimulatorSDK15_5-15.5.1.1653527639.dmg'
EXPECTED_SIZE = 5_430_783_739
CATALOG_LIMIT = 2_000_000
TOOL = Path('/opt/homebrew/bin/xcodes')


def catalog_runtime(data):
    rows = data.get('downloadables')
    if not isinstance(rows, list):
        raise ValueError('Official runtime catalog is not a downloadable inventory')
    matches = [r for r in rows if isinstance(r, dict) and r.get('identifier') == 'com.apple.pkg.iPhoneSimulatorSDK15_5']
    if len(matches) != 1:
        raise ValueError('Exact runtime is missing or duplicated in Apple catalog')
    row = matches[0]
    expected = {
        'category': 'simulator', 'contentType': 'package', 'dictionaryVersion': 2,
        'fileSize': EXPECTED_SIZE, 'name': 'iOS 15.5 Simulator',
        'platform': 'com.apple.platform.iphoneos', 'source': SOURCE,
        'version': '15.5.1.1653527639',
        'simulatorVersion': {'buildUpdate': RUNTIME_BUILD, 'version': '15.5'},
        'hostRequirements': {'maxHostVersion': '26.99.0', 'maxXcodeVersion': '26.99.0'},
    }
    if any(row.get(k) != value for k, value in expected.items()):
        raise ValueError('Apple catalog differs from the verified runtime package')
    return row


def installed_runtime(data):
    """Return absent or require a complete available runtime, without repair."""
    rows = data.get('runtimes')
    if not isinstance(rows, list):
        raise ValueError('Malformed simctl runtime inventory')
    matches = [r for r in rows if isinstance(r, dict) and r.get('identifier') == RUNTIME_ID]
    if not matches:
        return None
    # select_runtime checks the version, build, availability and exact old-device
    # types. Both endpoints must be supported before six app/device rows run.
    for device in ('iPhone SE (1st generation)', 'iPad mini 4'):
        select_runtime(data, device)
    row = matches[0]
    if 'arm64' not in row.get('supportedArchitectures', []):
        raise ValueError('The installed runtime cannot execute unchanged arm64 apps')
    return {k: row[k] for k in ('identifier', 'version', 'buildversion', 'supportedArchitectures', 'isAvailable')}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'Unexpected catalog redirect', headers, fp)


def fetch_catalog():
    # Normal TLS validation remains enabled. No credentials or user data are
    # transmitted, and the endpoint is a fixed official Apple public catalog.
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(CATALOG, timeout=30) as response:
        if response.status != 200 or response.url != CATALOG:
            raise ValueError('Unexpected Apple catalog HTTP response')
        body = response.read(CATALOG_LIMIT + 1)
    if len(body) > CATALOG_LIMIT:
        raise ValueError('Apple catalog exceeds the bounded input allowance')
    return catalog_runtime(plistlib.loads(body)), hashlib.sha256(body).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checked_host()
    args.output.mkdir(parents=False, exist_ok=False)
    inventory = json.loads(output(['xcrun', 'simctl', 'list', 'runtimes', '-j']))
    installed = installed_runtime(inventory)
    if installed:
        print('EXACT_RUNTIME_ALREADY_AVAILABLE', json.dumps(installed, sort_keys=True), flush=True)
        return
    row, catalog_hash = fetch_catalog()
    if not TOOL.is_file() or output([str(TOOL), 'version']) != '2.0.3':
        raise ValueError('Expected preinstalled xcodes2.0.3 is absent; do not install a substitute')
    if shutil.disk_usage(args.output).free < 30_000_000_000:
        raise ValueError('Insufficient free disk for the official runtime; no automatic deletion')
    print('EXACT_OFFICIAL_RUNTIME', json.dumps({'package': row, 'catalog_sha256': catalog_hash}, sort_keys=True), flush=True)
    developer = '/Applications/Xcode_26.6.app/Contents/Developer'
    if os.environ.get('DEVELOPER_DIR') != developer:
        raise ValueError('Exact older Xcode must be selected before installation')
    bounded_build(['sudo', '-n', 'env', 'DEVELOPER_DIR=' + developer, str(TOOL),
                   'runtimes', 'install', 'iOS 15.5', '--no-aria2'],
                  Path(__file__).resolve().parent, args.output/'runtime-install.log', 1200)
    installed = installed_runtime(json.loads(output(['xcrun', 'simctl', 'list', 'runtimes', '-j'])))
    if not installed:
        raise ValueError('Installation did not yield the exact available official runtime')
    evidence = {'runtime': installed, 'package': row, 'catalog_sha256': catalog_hash,
                'app_test_execution': False, 'simulator_boot_execution': False}
    (args.output/'installed-runtime.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print('EXACT_RUNTIME_INSTALLED_NOT_APP_TESTED', json.dumps(installed, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
