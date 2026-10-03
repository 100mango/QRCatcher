"""Validate the older XCTest runner's actual arm64 simulator link floors.

This verifies only test infrastructure. The app products have independent
SDK27 provenance and remain byte-identical across producer and consumer.
"""
from pathlib import Path
import re

from build_release import output

MACHO_MAGIC = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', value):
        raise ValueError('Unexpected Mach-O OS version')
    return tuple(int(v) for v in value.split('.')) + (0,) * (3-len(value.split('.')))


def parse_arm64_simulator_load_commands(text):
    platforms = re.findall(r'^\s*platform\s+(\S+)\s*$', text, re.MULTILINE)
    floors = re.findall(r'^\s*minos\s+(\S+)\s*$', text, re.MULTILINE)
    sdks = re.findall(r'^\s*sdk\s+(\S+)\s*$', text, re.MULTILINE)
    if platforms != ['IOSSIMULATOR'] or len(floors) != 1 or len(sdks) != 1:
        raise ValueError('Runner image lacks a single explicit iOS-simulator platform')
    if version_tuple(floors[0]) > version_tuple('15.5'):
        raise ValueError('Older XCTest runner/framework requires a newer OS than the target runtime')
    # These are the test binaries built/bundled by exact Xcode26.6, not app
    # binaries. Do not let accidental use of Xcode27 become a hidden fallback.
    if version_tuple(sdks[0]) > version_tuple('26.5'):
        raise ValueError('XCTest runner SDK exceeds the selected older toolchain')
    return {'platform': platforms[0], 'minimum': floors[0], 'sdk': sdks[0]}


def verify_runner_products(products):
    if products.is_symlink() or not products.is_dir():
        raise ValueError('Missing older test products')
    records=[]
    for path in sorted(products.rglob('*')):
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            magic=stream.read(4)
        if magic not in MACHO_MAGIC:
            continue
        architectures=output(['xcrun','lipo','-archs',str(path)]).split()
        if 'arm64' not in architectures:
            raise ValueError('Older runner contains an executable without arm64')
        commands=output(['xcrun','vtool','-arch','arm64','-show-build',str(path)])
        records.append({'member':path.relative_to(products).as_posix(),
                        **parse_arm64_simulator_load_commands(commands)})
    names=[r['member'] for r in records]
    if not any(n.endswith('CompatibilityHarnessHost.app/CompatibilityHarnessHost') for n in names):
        raise ValueError('Actual test host binary was not checked')
    if not any(n.endswith('LegacyRuntimeTests.xctest/LegacyRuntimeTests') for n in names):
        raise ValueError('Actual black-box XCTest binary was not checked')
    return records
